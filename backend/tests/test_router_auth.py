"""Tests de integración del router `auth` + `app.core.deps` (tarea backend-routers-core-05).

Cliente HTTP real (`httpx.ASGITransport`) contra `create_app()`, con `get_db_session`/`get_settings`
sobreescritos para apuntar a `syntax_test` (Postgres real, `superuser_engine`) y a un `jwt_secret` de
test. 1:1 con los 16 escenarios Gherkin de la tarea: login en 2 pasos, select/switch-tenant, refresh,
logout, `me`, password, y la decisión de ámbito por-capacidad de `require_capability`.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest_asyncio
from app.core.config import Settings, get_settings
from app.core.deps import get_db_session, require_capability
from app.core.security import (
    JWT_ALGORITHM,
    create_access_token,
    hash_password,
    hash_token,
    new_opaque_token,
)
from app.domain.entities.enums import AuthTokenKind, RoleKind, TenantStatus, UserStatus
from app.domain.entities.identity import AuthToken, Role, Tenant, User, UserTenantMembership
from app.infra.db.repositories import (
    SqlAlchemyAuthTokenRepository,
    SqlAlchemyRoleRepository,
    SqlAlchemyTenantRepository,
    SqlAlchemyUserRepository,
    SqlAlchemyUserTenantMembershipRepository,
)
from app.main import create_app
from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

_JWT_SECRET = "x" * 32
_TTL = 900


def _settings() -> Settings:
    return Settings(_env_file=None, jwt_secret=_JWT_SECRET, app_env="production", cors_origins=[])


def _development_settings() -> Settings:
    return Settings(_env_file=None, jwt_secret=_JWT_SECRET, app_env="development", cors_origins=[])


_TRUNCATE_IDENTITY_TABLES = (
    "TRUNCATE user_tenant, refresh_session, auth_token, user_role, role_capability, "
    'capability, "user", role, tenant RESTART IDENTITY CASCADE'
)


@pytest_asyncio.fixture(autouse=True)
async def _clean_identity_tables(superuser_engine: AsyncEngine) -> AsyncIterator[None]:
    """Trunca antes y DESPUÉS de cada test — el truncate posterior evita contaminar OTRAS suites
    (p.ej. `test_migration.py`, que asume `user` vacía) si esta fuera la última en tocar estas
    tablas dentro de una ejecución completa de `pytest`."""
    async with superuser_engine.begin() as conn:
        await conn.execute(text(_TRUNCATE_IDENTITY_TABLES))
    yield
    async with superuser_engine.begin() as conn:
        await conn.execute(text(_TRUNCATE_IDENTITY_TABLES))


@pytest_asyncio.fixture
async def db(superuser_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Sesión para SEMBRAR datos de test — separada de las que usará la propia app por request."""
    async with async_sessionmaker(superuser_engine, expire_on_commit=False)() as s:
        yield s


@pytest_asyncio.fixture
async def app(superuser_engine: AsyncEngine) -> AsyncIterator[FastAPI]:
    test_app = create_app(_settings())

    async def _override_session() -> AsyncIterator[AsyncSession]:
        """Mismo commit-on-success/rollback-on-exception que `app.infra.db.session.get_session`."""
        async with async_sessionmaker(superuser_engine, expire_on_commit=False)() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    test_app.dependency_overrides[get_db_session] = _override_session
    test_app.dependency_overrides[get_settings] = _settings
    yield test_app
    test_app.dependency_overrides.clear()


def _client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _make_tenant(*, status: TenantStatus = TenantStatus.active) -> Tenant:
    return Tenant(id=uuid.uuid4(), slug=f"t-{uuid.uuid4()}", name="Tenant", status=status)


async def _seed_user_with_membership(
    db: AsyncSession,
    *,
    password: str = "correct-password",  # noqa: S107 — fixture de test, no un secreto
    tenant_status: TenantStatus = TenantStatus.active,
    membership_status: UserStatus = UserStatus.active,
) -> tuple[User, Tenant]:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant(status=tenant_status))
    user = await SqlAlchemyUserRepository(db).add(
        User(
            id=uuid.uuid4(),
            email=f"u-{uuid.uuid4()}@example.com",
            password_hash=hash_password(password),
        )
    )
    await SqlAlchemyUserTenantMembershipRepository(db).add(
        UserTenantMembership(user_id=user.id, tenant_id=tenant.id, status=membership_status)
    )
    await db.commit()
    return user, tenant


async def _grant_capability(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID | None,
    capability: str,
    scope: str,
) -> None:
    """Siembra rol+capability+asignación directamente en SQL (sin puerto de creación de asignaciones,
    fuera del alcance de esta tarea) para poblar `effective_capabilities`. `capability.name` es
    único global — reusa la fila del catálogo si ya existe (p.ej. conceder la MISMA capacidad vía
    dos roles/ámbitos distintos al mismo test)."""
    kind = RoleKind.system if tenant_id is None else RoleKind.tenant
    role = await SqlAlchemyRoleRepository(db).add(
        Role(id=uuid.uuid4(), name=f"role-{uuid.uuid4()}", kind=kind, tenant_id=tenant_id)
    )
    existing_capability_id = (
        await db.execute(text("SELECT id FROM capability WHERE name = :name"), {"name": capability})
    ).scalar_one_or_none()
    if existing_capability_id is None:
        capability_id = uuid.uuid4()
        await db.execute(
            text("INSERT INTO capability (id, name, scope) VALUES (:id, :name, :scope)"),
            {"id": capability_id, "name": capability, "scope": scope},
        )
    else:
        capability_id = existing_capability_id
    await db.execute(
        text("INSERT INTO role_capability (role_id, capability_id) VALUES (:r, :c)"),
        {"r": role.id, "c": capability_id},
    )
    await db.execute(
        text("INSERT INTO user_role (user_id, role_id, tenant_id) VALUES (:u, :r, :t)"),
        {"u": user_id, "r": role.id, "t": tenant_id},
    )
    await db.commit()


def _access_token(
    user_id: uuid.UUID, tenant_id: uuid.UUID | None, *, purpose: str = "access"
) -> str:
    return create_access_token(
        str(user_id),
        str(tenant_id) if tenant_id is not None else None,
        secret=_JWT_SECRET,
        algorithm=JWT_ALGORITHM,
        ttl=_TTL,
        now=datetime.now(UTC),
        purpose=purpose,
    )


# ── Login / select-tenant ──


async def test_login_with_one_tenant_issues_token_and_refresh_cookie(
    app: FastAPI, db: AsyncSession
) -> None:
    user, _tenant = await _seed_user_with_membership(db)
    async with _client(app) as c:
        r = await c.post(
            "/api/v1/auth/login", json={"email": user.email, "password": "correct-password"}
        )

    assert r.status_code == 200
    assert r.json()["access_token"]
    assert "refresh_token=" in r.headers.get("set-cookie", "")


async def test_login_with_two_tenants_returns_identity_selection_without_cookie(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant_repo = SqlAlchemyTenantRepository(db)
    user_repo = SqlAlchemyUserRepository(db)
    membership_repo = SqlAlchemyUserTenantMembershipRepository(db)
    user = await user_repo.add(
        User(
            id=uuid.uuid4(),
            email=f"u-{uuid.uuid4()}@example.com",
            password_hash=hash_password("pw"),
        )
    )
    for _ in range(2):
        tenant = await tenant_repo.add(_make_tenant())
        await membership_repo.add(
            UserTenantMembership(user_id=user.id, tenant_id=tenant.id, status=UserStatus.active)
        )
    await db.commit()

    async with _client(app) as c:
        r = await c.post("/api/v1/auth/login", json={"email": user.email, "password": "pw"})

    assert r.status_code == 200
    body = r.json()
    assert body["identity_token"]
    assert len(body["tenants"]) == 2
    assert "set-cookie" not in r.headers


async def test_select_tenant_with_valid_identity_token_issues_real_tokens(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant_repo = SqlAlchemyTenantRepository(db)
    user_repo = SqlAlchemyUserRepository(db)
    membership_repo = SqlAlchemyUserTenantMembershipRepository(db)
    user = await user_repo.add(
        User(
            id=uuid.uuid4(),
            email=f"u-{uuid.uuid4()}@example.com",
            password_hash=hash_password("pw"),
        )
    )
    tenants = []
    for _ in range(2):
        tenant = await tenant_repo.add(_make_tenant())
        await membership_repo.add(
            UserTenantMembership(user_id=user.id, tenant_id=tenant.id, status=UserStatus.active)
        )
        tenants.append(tenant)
    await db.commit()

    async with _client(app) as c:
        login = await c.post("/api/v1/auth/login", json={"email": user.email, "password": "pw"})
        identity_token = login.json()["identity_token"]
        r = await c.post(
            "/api/v1/auth/select-tenant",
            json={"identity_token": identity_token, "tenant_id": str(tenants[0].id)},
        )

    assert r.status_code == 200
    assert r.json()["access_token"]
    assert "refresh_token=" in r.headers.get("set-cookie", "")


async def test_login_in_a_disabled_tenant_is_rejected(app: FastAPI, db: AsyncSession) -> None:
    user, _tenant = await _seed_user_with_membership(db, tenant_status=TenantStatus.disabled)
    async with _client(app) as c:
        r = await c.post(
            "/api/v1/auth/login", json={"email": user.email, "password": "correct-password"}
        )

    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/problem+json")


# ── atributos de la cookie de refresh (`_cookie_kwargs`) ──


async def test_refresh_cookie_is_httponly_and_secure_outside_development(
    app: FastAPI, db: AsyncSession
) -> None:
    user, _tenant = await _seed_user_with_membership(db)
    async with _client(app) as c:
        r = await c.post(
            "/api/v1/auth/login", json={"email": user.email, "password": "correct-password"}
        )

    cookie_header = r.headers.get("set-cookie", "").lower()
    assert "httponly" in cookie_header
    assert "secure" in cookie_header


async def test_refresh_cookie_is_not_secure_in_development(app: FastAPI, db: AsyncSession) -> None:
    app.dependency_overrides[get_settings] = _development_settings
    user, _tenant = await _seed_user_with_membership(db)
    async with _client(app) as c:
        r = await c.post(
            "/api/v1/auth/login", json={"email": user.email, "password": "correct-password"}
        )

    cookie_header = r.headers.get("set-cookie", "").lower()
    assert "httponly" in cookie_header
    assert "secure" not in cookie_header


async def test_refresh_cookie_is_secure_for_any_app_env_below_development_alphabetically(
    app: FastAPI, db: AsyncSession
) -> None:
    """`app_env="ci"` (< "development" alfabéticamente) — distingue `!=` de `>`/`>=` mal mutados,
    que darían `secure=False` aquí igual que en producción."""

    def _ci_settings() -> Settings:
        return Settings(_env_file=None, jwt_secret=_JWT_SECRET, app_env="ci", cors_origins=[])

    app.dependency_overrides[get_settings] = _ci_settings
    user, _tenant = await _seed_user_with_membership(db)
    async with _client(app) as c:
        r = await c.post(
            "/api/v1/auth/login", json={"email": user.email, "password": "correct-password"}
        )

    assert "secure" in r.headers.get("set-cookie", "").lower()


async def test_refresh_cookie_uses_value_equality_not_identity_for_development(
    app: FastAPI, db: AsyncSession
) -> None:
    """`app_env` igual a "development" por VALOR pero construido en runtime (no el literal interned
    del módulo) — distingue `!=` (valor) de `is not` (identidad) mal mutados."""
    non_interned_development = "".join(c for c in "development")

    def _settings_with_non_interned_development() -> Settings:
        return Settings(
            _env_file=None,
            jwt_secret=_JWT_SECRET,
            app_env=non_interned_development,
            cors_origins=[],
        )

    app.dependency_overrides[get_settings] = _settings_with_non_interned_development
    user, _tenant = await _seed_user_with_membership(db)
    async with _client(app) as c:
        r = await c.post(
            "/api/v1/auth/login", json={"email": user.email, "password": "correct-password"}
        )

    assert "secure" not in r.headers.get("set-cookie", "").lower()


# ── GET /auth/me ──


async def test_me_without_token_is_rejected(app: FastAPI) -> None:
    async with _client(app) as c:
        r = await c.get("/api/v1/auth/me")

    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/problem+json")


async def test_me_with_valid_token_returns_subject_and_capabilities(
    app: FastAPI, db: AsyncSession
) -> None:
    user, tenant = await _seed_user_with_membership(db)
    await _grant_capability(
        db, user_id=user.id, tenant_id=tenant.id, capability="ticket.reply", scope="tenant"
    )
    token = _access_token(user.id, tenant.id)

    async with _client(app) as c:
        r = await c.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert r.status_code == 200
    body = r.json()
    assert body["user"]["email"] == user.email
    assert {"capability": "ticket.reply", "scope": "tenant"} in body["capabilities"]


async def test_identity_token_used_as_bearer_is_rejected(app: FastAPI, db: AsyncSession) -> None:
    user, tenant = await _seed_user_with_membership(db)
    identity_token = _access_token(user.id, None, purpose="tenant_selection")

    async with _client(app) as c:
        r = await c.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {identity_token}"})

    assert r.status_code == 401


async def test_token_with_invalid_signature_is_rejected(app: FastAPI, db: AsyncSession) -> None:
    user, tenant = await _seed_user_with_membership(db)
    forged = create_access_token(
        str(user.id),
        str(tenant.id),
        secret="a-completely-different-secret" * 2,
        algorithm=JWT_ALGORITHM,
        ttl=_TTL,
        now=datetime.now(UTC),
    )

    async with _client(app) as c:
        r = await c.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"})

    assert r.status_code == 401


async def test_me_when_the_membership_is_missing_is_not_found(
    app: FastAPI, db: AsyncSession
) -> None:
    """El `user` existe (identidad global) pero no tiene `UserTenantMembership` en ese tenant —
    p.ej. se borró entre emitir el token y esta request. Un token válido no garantiza la membership,
    solo que el tenant existe y no está `disabled` (`get_current_subject` no la comprueba)."""
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    user = await SqlAlchemyUserRepository(db).add(
        User(
            id=uuid.uuid4(),
            email=f"u-{uuid.uuid4()}@example.com",
            password_hash=hash_password("pw"),
        )
    )
    await db.commit()
    token = _access_token(user.id, tenant.id)

    async with _client(app) as c:
        r = await c.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")


async def test_me_returns_the_active_tenant_id(app: FastAPI, db: AsyncSession) -> None:
    """`Me.active_tenant_id` (contrato, `api-contract.yaml:1117-1123`) es el único campo donde el
    front puede leer el tenant de la sesión actual — sin él, `TenantProvider` no puede resolverlo."""
    user, tenant = await _seed_user_with_membership(db)
    token = _access_token(user.id, tenant.id)

    async with _client(app) as c:
        r = await c.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert r.status_code == 200
    assert r.json()["active_tenant_id"] == str(tenant.id)


async def test_me_returns_available_tenants_with_a_single_membership(
    app: FastAPI, db: AsyncSession
) -> None:
    """Con una sola membership `active`, `available_tenants` trae ESE tenant (incluye siempre el
    de la sesión activa)."""
    user, tenant = await _seed_user_with_membership(db)
    token = _access_token(user.id, tenant.id)

    async with _client(app) as c:
        r = await c.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    body = r.json()
    assert body["available_tenants"] == [
        {"id": str(tenant.id), "slug": tenant.slug, "name": tenant.name}
    ]


async def test_me_available_tenants_lists_every_active_membership(
    app: FastAPI, db: AsyncSession
) -> None:
    """Un usuario con 2+ membresías `active` ve TODAS en `available_tenants` — es lo que habilita el
    switcher de tenant en el front, no solo el de la sesión actual."""
    user, tenant_a = await _seed_user_with_membership(db)
    tenant_b = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await SqlAlchemyUserTenantMembershipRepository(db).add(
        UserTenantMembership(user_id=user.id, tenant_id=tenant_b.id, status=UserStatus.active)
    )
    await db.commit()
    token = _access_token(user.id, tenant_a.id)

    async with _client(app) as c:
        r = await c.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    ids = {t["id"] for t in r.json()["available_tenants"]}
    assert ids == {str(tenant_a.id), str(tenant_b.id)}


async def test_me_available_tenants_excludes_a_disabled_membership(
    app: FastAPI, db: AsyncSession
) -> None:
    """Una membership `disabled` en otro tenant NO cuenta como disponible — mismo criterio que el
    login multi-tenant (`AuthService._eligible_memberships`, reusado aquí)."""
    user, tenant_a = await _seed_user_with_membership(db)
    tenant_b = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await SqlAlchemyUserTenantMembershipRepository(db).add(
        UserTenantMembership(user_id=user.id, tenant_id=tenant_b.id, status=UserStatus.disabled)
    )
    await db.commit()
    token = _access_token(user.id, tenant_a.id)

    async with _client(app) as c:
        r = await c.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    ids = {t["id"] for t in r.json()["available_tenants"]}
    assert ids == {str(tenant_a.id)}


async def test_me_available_tenants_excludes_membership_in_a_disabled_tenant(
    app: FastAPI, db: AsyncSession
) -> None:
    """Una membership `active` en un tenant `disabled` tampoco cuenta — el tenant deshabilitado
    invalida la membership aunque ella misma siga `active` (scenario-coverage)."""
    user, tenant_a = await _seed_user_with_membership(db)
    tenant_b = await SqlAlchemyTenantRepository(db).add(_make_tenant(status=TenantStatus.disabled))
    await SqlAlchemyUserTenantMembershipRepository(db).add(
        UserTenantMembership(user_id=user.id, tenant_id=tenant_b.id, status=UserStatus.active)
    )
    await db.commit()
    token = _access_token(user.id, tenant_a.id)

    async with _client(app) as c:
        r = await c.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    ids = {t["id"] for t in r.json()["available_tenants"]}
    assert ids == {str(tenant_a.id)}


# ── require_capability: decisión de ámbito ──


def _mount_probe_route(app: FastAPI, capability: str) -> None:
    @app.get(f"/_test/probe/{capability.replace('.', '-')}")
    async def _probe(
        subject_and_session: tuple = Depends(require_capability(capability)),
    ) -> dict[str, str]:
        subject, session = subject_and_session
        bypass = (
            await session.execute(text("SELECT current_setting('app.bypass_rls', true)"))
        ).scalar()
        return {"tenant_id": str(subject.tenant_id), "bypass_rls": bypass or ""}


async def test_require_capability_with_global_scope_opens_global_scope(
    app: FastAPI, db: AsyncSession
) -> None:
    user, tenant = await _seed_user_with_membership(db)
    await _grant_capability(
        db, user_id=user.id, tenant_id=None, capability="tenant.manage", scope="global"
    )
    _mount_probe_route(app, "tenant.manage")
    token = _access_token(user.id, tenant.id)

    async with _client(app) as c:
        r = await c.get("/_test/probe/tenant-manage", headers={"Authorization": f"Bearer {token}"})

    assert r.status_code == 200
    assert r.json()["bypass_rls"] == "on"


async def test_require_capability_with_tenant_scope_opens_tenant_scope(
    app: FastAPI, db: AsyncSession
) -> None:
    user, tenant = await _seed_user_with_membership(db)
    await _grant_capability(
        db, user_id=user.id, tenant_id=tenant.id, capability="ticket.reply", scope="tenant"
    )
    _mount_probe_route(app, "ticket.reply")
    token = _access_token(user.id, tenant.id)

    async with _client(app) as c:
        r = await c.get("/_test/probe/ticket-reply", headers={"Authorization": f"Bearer {token}"})

    assert r.status_code == 200
    body = r.json()
    assert body["tenant_id"] == str(tenant.id)
    assert body["bypass_rls"] != "on"


async def test_require_capability_prioritizes_global_over_tenant(
    app: FastAPI, db: AsyncSession
) -> None:
    user, tenant = await _seed_user_with_membership(db)
    await _grant_capability(
        db, user_id=user.id, tenant_id=tenant.id, capability="kb.read", scope="tenant"
    )
    await _grant_capability(
        db, user_id=user.id, tenant_id=None, capability="kb.read", scope="global"
    )
    _mount_probe_route(app, "kb.read")
    token = _access_token(user.id, tenant.id)

    async with _client(app) as c:
        r = await c.get("/_test/probe/kb-read", headers={"Authorization": f"Bearer {token}"})

    assert r.status_code == 200
    assert r.json()["bypass_rls"] == "on"


async def test_require_capability_without_the_capability_is_forbidden(
    app: FastAPI, db: AsyncSession
) -> None:
    user, tenant = await _seed_user_with_membership(db)
    _mount_probe_route(app, "tenant.manage")
    token = _access_token(user.id, tenant.id)

    async with _client(app) as c:
        r = await c.get("/_test/probe/tenant-manage", headers={"Authorization": f"Bearer {token}"})

    assert r.status_code == 403
    assert r.headers["content-type"].startswith("application/problem+json")


# ── switch-tenant / refresh / logout / password ──


async def test_switch_tenant_changes_tenant_without_repeating_credentials(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant_repo = SqlAlchemyTenantRepository(db)
    user_repo = SqlAlchemyUserRepository(db)
    membership_repo = SqlAlchemyUserTenantMembershipRepository(db)
    user = await user_repo.add(
        User(
            id=uuid.uuid4(),
            email=f"u-{uuid.uuid4()}@example.com",
            password_hash=hash_password("pw"),
        )
    )
    tenant_a, tenant_b = _make_tenant(), _make_tenant()
    for tenant in (tenant_a, tenant_b):
        await tenant_repo.add(tenant)
        await membership_repo.add(
            UserTenantMembership(user_id=user.id, tenant_id=tenant.id, status=UserStatus.active)
        )
    await db.commit()
    token_a = _access_token(user.id, tenant_a.id)

    async with _client(app) as c:
        r = await c.post(
            "/api/v1/auth/switch-tenant",
            json={"tenant_id": str(tenant_b.id)},
            headers={"Authorization": f"Bearer {token_a}"},
        )

    assert r.status_code == 200
    assert r.json()["access_token"]


async def test_switch_tenant_to_a_tenant_without_membership_is_rejected(
    app: FastAPI, db: AsyncSession
) -> None:
    user, tenant_a = await _seed_user_with_membership(db)
    tenant_c = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token_a = _access_token(user.id, tenant_a.id)

    async with _client(app) as c:
        r = await c.post(
            "/api/v1/auth/switch-tenant",
            json={"tenant_id": str(tenant_c.id)},
            headers={"Authorization": f"Bearer {token_a}"},
        )

    assert r.status_code == 401


async def test_logout_revokes_the_refresh_session(app: FastAPI, db: AsyncSession) -> None:
    user, _tenant = await _seed_user_with_membership(db)
    async with _client(app) as c:
        login = await c.post(
            "/api/v1/auth/login", json={"email": user.email, "password": "correct-password"}
        )
        r = await c.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        )
        refreshed = await c.post("/api/v1/auth/refresh")

    assert r.status_code == 204
    assert refreshed.status_code == 409


async def test_forgot_password_always_returns_202(app: FastAPI) -> None:
    """`forgot_password` responde igual exista o no el email (anti-enumeración) — 202 siempre."""
    async with _client(app) as c:
        r = await c.post("/api/v1/auth/password/forgot", json={"email": "nobody-here@example.com"})

    assert r.status_code == 202


async def test_reset_password_with_a_valid_token_updates_it(app: FastAPI, db: AsyncSession) -> None:
    user, _tenant = await _seed_user_with_membership(db, password="old-password")
    raw_token = new_opaque_token()
    await SqlAlchemyAuthTokenRepository(db).add(
        AuthToken(
            id=uuid.uuid4(),
            user_id=user.id,
            kind=AuthTokenKind.password_reset,
            token_hash=hash_token(raw_token),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    await db.commit()

    async with _client(app) as c:
        r = await c.post(
            "/api/v1/auth/password/reset",
            json={"token": raw_token, "new_password": "brand-new-password"},
        )
        relogin = await c.post(
            "/api/v1/auth/login", json={"email": user.email, "password": "brand-new-password"}
        )

    assert r.status_code == 204
    assert relogin.status_code == 200


async def test_reset_password_rejects_a_password_shorter_than_the_minimum(
    app: FastAPI, db: AsyncSession
) -> None:
    """Frontera `ResetPasswordRequest.new_password: Field(min_length=8)` — 7 caracteres no llega al
    mínimo. Ningún test lo cubría (destapado por el gate de mutation)."""
    user, _tenant = await _seed_user_with_membership(db, password="old-password")
    raw_token = new_opaque_token()
    await SqlAlchemyAuthTokenRepository(db).add(
        AuthToken(
            id=uuid.uuid4(),
            user_id=user.id,
            kind=AuthTokenKind.password_reset,
            token_hash=hash_token(raw_token),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    await db.commit()

    async with _client(app) as c:
        r = await c.post(
            "/api/v1/auth/password/reset",
            json={"token": raw_token, "new_password": "short12"},
        )

    assert r.status_code == 422


async def test_password_change_rejects_a_password_shorter_than_the_minimum(
    app: FastAPI, db: AsyncSession
) -> None:
    """Frontera `ChangePasswordRequest.new_password: Field(min_length=8)`."""
    user, tenant = await _seed_user_with_membership(db, password="old-password")
    token = _access_token(user.id, tenant.id)

    async with _client(app) as c:
        r = await c.post(
            "/api/v1/auth/password/change",
            json={"current_password": "old-password", "new_password": "short12"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert r.status_code == 422


async def test_reset_password_accepts_exactly_the_minimum_length(
    app: FastAPI, db: AsyncSession
) -> None:
    """Frontera exacta: `min_length=8` — un password de exactamente 8 caracteres es válido (el tope
    es inclusivo)."""
    user, _tenant = await _seed_user_with_membership(db, password="old-password")
    raw_token = new_opaque_token()
    await SqlAlchemyAuthTokenRepository(db).add(
        AuthToken(
            id=uuid.uuid4(),
            user_id=user.id,
            kind=AuthTokenKind.password_reset,
            token_hash=hash_token(raw_token),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    await db.commit()

    async with _client(app) as c:
        r = await c.post(
            "/api/v1/auth/password/reset",
            json={"token": raw_token, "new_password": "eight888"},
        )

    assert r.status_code == 204


async def test_password_change_accepts_exactly_the_minimum_length(
    app: FastAPI, db: AsyncSession
) -> None:
    user, tenant = await _seed_user_with_membership(db, password="old-password")
    token = _access_token(user.id, tenant.id)

    async with _client(app) as c:
        r = await c.post(
            "/api/v1/auth/password/change",
            json={"current_password": "old-password", "new_password": "eight888"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert r.status_code == 204


async def test_password_change_with_correct_current_password_updates_it(
    app: FastAPI, db: AsyncSession
) -> None:
    user, tenant = await _seed_user_with_membership(db, password="old-password")
    token = _access_token(user.id, tenant.id)

    async with _client(app) as c:
        r = await c.post(
            "/api/v1/auth/password/change",
            json={"current_password": "old-password", "new_password": "new-password-123"},
            headers={"Authorization": f"Bearer {token}"},
        )
        relogin = await c.post(
            "/api/v1/auth/login", json={"email": user.email, "password": "new-password-123"}
        )

    assert r.status_code == 204
    assert relogin.status_code == 200
