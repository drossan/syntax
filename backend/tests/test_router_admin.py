"""Tests de integración de los routers `admin_tenants`/`admin_users`/`admin_roles` (tarea
`backend-routers-core-06`). Mismo patrón que `test_router_auth.py`: cliente HTTP real
(`httpx.ASGITransport`) contra `create_app()`, `get_db_session`/`get_settings` sobreescritos hacia
`syntax_test` (Postgres real, `superuser_engine`). 1:1 con los 17 escenarios Gherkin de la tarea.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest_asyncio
from app.core.config import Settings, get_settings
from app.core.deps import get_db_session
from app.core.security import JWT_ALGORITHM, create_access_token, hash_password
from app.domain.entities.enums import RoleKind, TenantStatus, UserStatus
from app.domain.entities.identity import Role, Tenant, User, UserTenantMembership
from app.infra.db.repositories import (
    SqlAlchemyRoleRepository,
    SqlAlchemyTenantRepository,
    SqlAlchemyUserRepository,
    SqlAlchemyUserTenantMembershipRepository,
)
from app.main import create_app
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

_JWT_SECRET = "x" * 32
_TTL = 900


def _settings() -> Settings:
    return Settings(_env_file=None, jwt_secret=_JWT_SECRET, app_env="production", cors_origins=[])


_TRUNCATE_TABLES = (
    "TRUNCATE audit_log, user_tenant, refresh_session, auth_token, user_role, role_capability, "
    'capability, "user", role, tenant RESTART IDENTITY CASCADE'
)


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables(superuser_engine: AsyncEngine) -> AsyncIterator[None]:
    async with superuser_engine.begin() as conn:
        await conn.execute(text(_TRUNCATE_TABLES))
    yield
    async with superuser_engine.begin() as conn:
        await conn.execute(text(_TRUNCATE_TABLES))


@pytest_asyncio.fixture
async def db(superuser_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with async_sessionmaker(superuser_engine, expire_on_commit=False)() as s:
        yield s


@pytest_asyncio.fixture
async def app(superuser_engine: AsyncEngine) -> AsyncIterator[FastAPI]:
    test_app = create_app(_settings())

    async def _override_session() -> AsyncIterator[AsyncSession]:
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


async def _make_user(db: AsyncSession, *, email: str | None = None) -> User:
    return await SqlAlchemyUserRepository(db).add(
        User(
            id=uuid.uuid4(),
            email=email or f"u-{uuid.uuid4()}@example.com",
            password_hash=hash_password("pw"),
        )
    )


async def _add_membership(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    status: UserStatus = UserStatus.active,
) -> None:
    await SqlAlchemyUserTenantMembershipRepository(db).add(
        UserTenantMembership(user_id=user_id, tenant_id=tenant_id, status=status)
    )


async def _grant_capability(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID | None,
    capability: str,
    scope: str,
) -> None:
    """Siembra rol+capability+asignación (mismo patrón que `test_router_auth.py`, ahora usando el
    puerto real `RoleRepository.assign` para la asignación en vez de SQL crudo — no existía cuando se
    escribió aquel fichero)."""
    kind = RoleKind.system if tenant_id is None else RoleKind.tenant
    role_repo = SqlAlchemyRoleRepository(db)
    role = await role_repo.add(
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
    await role_repo.assign(user_id, role.id, tenant_id)
    await db.commit()


def _access_token(user_id: uuid.UUID, tenant_id: uuid.UUID | None) -> str:
    return create_access_token(
        str(user_id),
        str(tenant_id) if tenant_id is not None else None,
        secret=_JWT_SECRET,
        algorithm=JWT_ALGORITHM,
        ttl=_TTL,
        now=datetime.now(UTC),
    )


async def _admin_with_capability(
    db: AsyncSession, *, tenant: Tenant, capability: str, scope: str
) -> tuple[User, str]:
    admin = await _make_user(db)
    await _add_membership(db, user_id=admin.id, tenant_id=tenant.id)
    await _grant_capability(
        db,
        user_id=admin.id,
        tenant_id=None if scope == "global" else tenant.id,
        capability=capability,
        scope=scope,
    )
    token = _access_token(admin.id, tenant.id)
    return admin, token


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── /admin/tenants ──


async def test_soporte_global_lists_all_tenants(app: FastAPI, db: AsyncSession) -> None:
    tenant_a = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    tenant_b = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    admin, token = await _admin_with_capability(
        db, tenant=tenant_a, capability="tenant.manage", scope="global"
    )

    async with _client(app) as c:
        r = await c.get("/api/v1/admin/tenants", headers=_auth_header(token))

    assert r.status_code == 200
    body = r.json()
    slugs = {item["slug"] for item in body["items"]}
    assert {tenant_a.slug, tenant_b.slug} <= slugs


async def test_client_without_tenant_manage_cannot_list_tenants(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    user = await _make_user(db)
    await _add_membership(db, user_id=user.id, tenant_id=tenant.id)
    await db.commit()
    token = _access_token(user.id, tenant.id)

    async with _client(app) as c:
        r = await c.get("/api/v1/admin/tenants", headers=_auth_header(token))

    assert r.status_code == 403
    assert r.headers["content-type"].startswith("application/problem+json")


# ── /admin/settings ──


async def test_tenant_admin_reads_own_auto_approve(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    _admin, token = await _admin_with_capability(
        db, tenant=tenant, capability="tenant.settings.manage", scope="tenant"
    )

    async with _client(app) as c:
        r = await c.get("/api/v1/admin/settings", headers=_auth_header(token))

    assert r.status_code == 200
    assert r.json() == {"auto_approve": False}


async def test_tenant_admin_updates_own_auto_approve(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    _admin, token = await _admin_with_capability(
        db, tenant=tenant, capability="tenant.settings.manage", scope="tenant"
    )

    async with _client(app) as c:
        r = await c.patch(
            "/api/v1/admin/settings", json={"auto_approve": True}, headers=_auth_header(token)
        )
        reread = await c.get("/api/v1/admin/settings", headers=_auth_header(token))

    assert r.status_code == 200
    assert r.json() == {"auto_approve": True}
    assert reread.json() == {"auto_approve": True}


async def test_soporte_global_reads_settings_of_a_specific_tenant_with_tenant_id(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    tenant.auto_approve = True
    await SqlAlchemyTenantRepository(db).update(tenant)
    await db.commit()
    _admin, token = await _admin_with_capability(
        db, tenant=tenant, capability="tenant.settings.manage", scope="global"
    )

    async with _client(app) as c:
        r = await c.get(
            "/api/v1/admin/settings",
            params={"tenant_id": str(tenant.id)},
            headers=_auth_header(token),
        )

    assert r.status_code == 200
    assert r.json() == {"auto_approve": True}


async def test_soporte_global_without_tenant_id_gets_422(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    _admin, token = await _admin_with_capability(
        db, tenant=tenant, capability="tenant.settings.manage", scope="global"
    )

    async with _client(app) as c:
        r = await c.get("/api/v1/admin/settings", headers=_auth_header(token))

    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")


# ── /admin/users ──


async def test_invite_existing_global_user_only_adds_membership(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant_a = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    tenant_b = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    existing_user = await _make_user(db, email="shared@example.com")
    await _add_membership(db, user_id=existing_user.id, tenant_id=tenant_a.id)
    await db.commit()
    _admin, token = await _admin_with_capability(
        db, tenant=tenant_b, capability="user.manage", scope="tenant"
    )

    async with _client(app) as c:
        r = await c.post(
            "/api/v1/admin/users",
            json={"email": "shared@example.com", "roles": []},
            headers=_auth_header(token),
        )

    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "shared@example.com"
    assert body["status"] == "invited"
    membership = await SqlAlchemyUserTenantMembershipRepository(db).get(
        existing_user.id, tenant_b.id
    )
    assert membership is not None
    assert membership.status is UserStatus.invited


async def test_invite_with_roles_assigns_them(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    role = await SqlAlchemyRoleRepository(db).add(
        Role(id=uuid.uuid4(), name="agent", kind=RoleKind.tenant, tenant_id=tenant.id)
    )
    await db.commit()
    _admin, token = await _admin_with_capability(
        db, tenant=tenant, capability="user.manage", scope="tenant"
    )

    async with _client(app) as c:
        r = await c.post(
            "/api/v1/admin/users",
            json={"email": "with-role@example.com", "roles": [str(role.id)]},
            headers=_auth_header(token),
        )

    assert r.status_code == 201
    assert r.json()["roles"] == ["agent"]


async def test_invite_already_active_email_in_same_tenant_returns_409(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    already_active = await _make_user(db, email="active@example.com")
    await _add_membership(
        db, user_id=already_active.id, tenant_id=tenant.id, status=UserStatus.active
    )
    await db.commit()
    _admin, token = await _admin_with_capability(
        db, tenant=tenant, capability="user.manage", scope="tenant"
    )

    async with _client(app) as c:
        r = await c.post(
            "/api/v1/admin/users",
            json={"email": "active@example.com", "roles": []},
            headers=_auth_header(token),
        )

    assert r.status_code == 409
    assert r.headers["content-type"].startswith("application/problem+json")


async def test_list_users_does_not_show_other_tenants_memberships(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant_a = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    tenant_b = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    user_a = await _make_user(db)
    await _add_membership(db, user_id=user_a.id, tenant_id=tenant_a.id)
    user_b = await _make_user(db)
    await _add_membership(db, user_id=user_b.id, tenant_id=tenant_b.id)
    await db.commit()
    _admin, token = await _admin_with_capability(
        db, tenant=tenant_a, capability="user.manage", scope="tenant"
    )

    async with _client(app) as c:
        r = await c.get("/api/v1/admin/users", headers=_auth_header(token))

    assert r.status_code == 200
    emails = {item["email"] for item in r.json()["items"]}
    assert user_a.email in emails
    assert user_b.email not in emails


async def test_list_users_on_an_empty_tenant_returns_an_empty_page(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    _admin, token = await _admin_with_capability(
        db, tenant=tenant, capability="user.manage", scope="tenant"
    )

    async with _client(app) as c:
        r = await c.get("/api/v1/admin/users", headers=_auth_header(token))

    assert r.status_code == 200
    body = r.json()
    non_admin_items = [item for item in body["items"] if item["email"] != _admin.email]
    assert non_admin_items == []


async def test_list_users_rejects_page_below_1(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    _admin, token = await _admin_with_capability(
        db, tenant=tenant, capability="user.manage", scope="tenant"
    )

    async with _client(app) as c:
        r = await c.get("/api/v1/admin/users", params={"page": 0}, headers=_auth_header(token))

    assert r.status_code == 422


async def test_list_users_rejects_page_size_out_of_range(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    _admin, token = await _admin_with_capability(
        db, tenant=tenant, capability="user.manage", scope="tenant"
    )

    async with _client(app) as c:
        too_low = await c.get(
            "/api/v1/admin/users", params={"page_size": 0}, headers=_auth_header(token)
        )
        too_high = await c.get(
            "/api/v1/admin/users", params={"page_size": 101}, headers=_auth_header(token)
        )

    assert too_low.status_code == 422
    assert too_high.status_code == 422


async def test_list_users_accepts_page_size_at_the_boundaries(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    _admin, token = await _admin_with_capability(
        db, tenant=tenant, capability="user.manage", scope="tenant"
    )

    async with _client(app) as c:
        lowest = await c.get(
            "/api/v1/admin/users", params={"page_size": 1}, headers=_auth_header(token)
        )
        highest = await c.get(
            "/api/v1/admin/users", params={"page_size": 100}, headers=_auth_header(token)
        )

    assert lowest.status_code == 200
    assert lowest.json()["page_size"] == 1
    assert highest.status_code == 200
    assert highest.json()["page_size"] == 100


async def test_list_users_defaults_to_page_size_20(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    _admin, token = await _admin_with_capability(
        db, tenant=tenant, capability="user.manage", scope="tenant"
    )

    async with _client(app) as c:
        r = await c.get("/api/v1/admin/users", headers=_auth_header(token))

    assert r.status_code == 200
    assert r.json()["page_size"] == 20


async def test_patch_user_updates_its_roles(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    role = await SqlAlchemyRoleRepository(db).add(
        Role(id=uuid.uuid4(), name="agent", kind=RoleKind.tenant, tenant_id=tenant.id)
    )
    user = await _make_user(db)
    await _add_membership(db, user_id=user.id, tenant_id=tenant.id)
    await db.commit()
    _admin, token = await _admin_with_capability(
        db, tenant=tenant, capability="user.manage", scope="tenant"
    )

    async with _client(app) as c:
        r = await c.patch(
            f"/api/v1/admin/users/{user.id}",
            json={"roles": [str(role.id)]},
            headers=_auth_header(token),
        )

    assert r.status_code == 200
    assert r.json()["roles"] == ["agent"]


async def test_patch_user_with_an_unknown_status_is_rejected(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    user = await _make_user(db)
    await _add_membership(db, user_id=user.id, tenant_id=tenant.id)
    await db.commit()
    _admin, token = await _admin_with_capability(
        db, tenant=tenant, capability="user.manage", scope="tenant"
    )

    async with _client(app) as c:
        r = await c.patch(
            f"/api/v1/admin/users/{user.id}",
            json={"status": "not-a-real-status"},
            headers=_auth_header(token),
        )

    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")


async def test_disable_user_is_soft_delete_of_that_membership_only(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant_a = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    tenant_b = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    user = await _make_user(db)
    await _add_membership(db, user_id=user.id, tenant_id=tenant_a.id)
    await _add_membership(db, user_id=user.id, tenant_id=tenant_b.id)
    await db.commit()
    _admin, token = await _admin_with_capability(
        db, tenant=tenant_a, capability="user.manage", scope="tenant"
    )

    async with _client(app) as c:
        r = await c.patch(
            f"/api/v1/admin/users/{user.id}",
            json={"status": "disabled"},
            headers=_auth_header(token),
        )

    assert r.status_code == 200
    assert r.json()["status"] == "disabled"
    membership_repo = SqlAlchemyUserTenantMembershipRepository(db)
    assert (await membership_repo.get(user.id, tenant_a.id)).status is UserStatus.disabled  # type: ignore[union-attr]
    assert (await membership_repo.get(user.id, tenant_b.id)).status is UserStatus.active  # type: ignore[union-attr]


async def test_patch_user_without_membership_in_that_tenant_returns_404(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant_a = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    tenant_b = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    user_in_b_only = await _make_user(db)
    await _add_membership(db, user_id=user_in_b_only.id, tenant_id=tenant_b.id)
    await db.commit()
    _admin, token = await _admin_with_capability(
        db, tenant=tenant_a, capability="user.manage", scope="tenant"
    )

    async with _client(app) as c:
        r = await c.patch(
            f"/api/v1/admin/users/{user_in_b_only.id}",
            json={"status": "disabled"},
            headers=_auth_header(token),
        )

    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")


# ── /admin/capabilities · /admin/roles ──


async def test_capabilities_catalog_is_accessible_with_role_manage(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    _admin, token = await _admin_with_capability(
        db, tenant=tenant, capability="role.manage", scope="tenant"
    )

    async with _client(app) as c:
        r = await c.get("/api/v1/admin/capabilities", headers=_auth_header(token))

    assert r.status_code == 200
    names = {item["name"] for item in r.json()}
    assert "role.manage" in names


async def test_list_roles_returns_system_seed_and_tenant_custom_roles(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    custom_role = await SqlAlchemyRoleRepository(db).add(
        Role(id=uuid.uuid4(), name="agent", kind=RoleKind.tenant, tenant_id=tenant.id)
    )
    system_role = await SqlAlchemyRoleRepository(db).add(
        Role(id=uuid.uuid4(), name="support_admin", kind=RoleKind.system, tenant_id=None)
    )
    await db.commit()
    _admin, token = await _admin_with_capability(
        db, tenant=tenant, capability="role.manage", scope="tenant"
    )

    async with _client(app) as c:
        r = await c.get("/api/v1/admin/roles", headers=_auth_header(token))

    assert r.status_code == 200
    ids = {item["id"] for item in r.json()}
    assert {str(custom_role.id), str(system_role.id)} <= ids


async def test_create_custom_role_with_an_unknown_capability_is_rejected(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    _admin, token = await _admin_with_capability(
        db, tenant=tenant, capability="role.manage", scope="tenant"
    )

    async with _client(app) as c:
        r = await c.post(
            "/api/v1/admin/roles",
            json={"name": "con-capacidad-inventada", "capabilities": ["no.existe"]},
            headers=_auth_header(token),
        )

    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")


async def test_editing_another_tenants_custom_role_returns_404(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant_a = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    tenant_b = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    role_of_b = await SqlAlchemyRoleRepository(db).add(
        Role(id=uuid.uuid4(), name="agent-b", kind=RoleKind.tenant, tenant_id=tenant_b.id)
    )
    await db.commit()
    _admin, token = await _admin_with_capability(
        db, tenant=tenant_a, capability="role.manage", scope="tenant"
    )

    async with _client(app) as c:
        r = await c.patch(
            f"/api/v1/admin/roles/{role_of_b.id}",
            json={"name": "renombrado", "capabilities": []},
            headers=_auth_header(token),
        )

    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")


async def test_delete_custom_role_removes_it(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    role = await SqlAlchemyRoleRepository(db).add(
        Role(id=uuid.uuid4(), name="agent", kind=RoleKind.tenant, tenant_id=tenant.id)
    )
    await db.commit()
    _admin, token = await _admin_with_capability(
        db, tenant=tenant, capability="role.manage", scope="tenant"
    )

    async with _client(app) as c:
        r = await c.delete(f"/api/v1/admin/roles/{role.id}", headers=_auth_header(token))
        listing = await c.get("/api/v1/admin/roles", headers=_auth_header(token))

    assert r.status_code == 204
    assert str(role.id) not in {item["id"] for item in listing.json()}


async def test_create_custom_role_with_empty_capabilities_is_valid(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    _admin, token = await _admin_with_capability(
        db, tenant=tenant, capability="role.manage", scope="tenant"
    )

    async with _client(app) as c:
        r = await c.post(
            "/api/v1/admin/roles",
            json={"name": "sin-capacidades", "capabilities": []},
            headers=_auth_header(token),
        )

    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "sin-capacidades"
    assert body["capabilities"] == []
    assert body["kind"] == "tenant"


async def test_create_custom_role_with_a_global_scope_capability_is_rejected(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    admin, token = await _admin_with_capability(
        db, tenant=tenant, capability="role.manage", scope="tenant"
    )
    # `tenant.manage` es una capacidad de ámbito `global` en el catálogo — el admin la posee (para
    # que el rechazo sea por el invariante de ámbito, no por "el componedor no la posee").
    await _grant_capability(
        db, user_id=admin.id, tenant_id=None, capability="tenant.manage", scope="global"
    )

    async with _client(app) as c:
        r = await c.post(
            "/api/v1/admin/roles",
            json={"name": "quiere-global", "capabilities": ["tenant.manage"]},
            headers=_auth_header(token),
        )

    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")


async def test_create_custom_role_with_a_capability_the_composer_lacks_is_rejected(
    app: FastAPI, db: AsyncSession
) -> None:
    """Distinto del rechazo por ámbito `global`: aquí la capacidad SÍ es de ámbito `tenant` (la
    permite un rol custom), pero el admin componedor no la posee él mismo — no-escalada de
    privilegios (CU-BE-09, FR-037)."""
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    _admin, token = await _admin_with_capability(
        db, tenant=tenant, capability="role.manage", scope="tenant"
    )
    await db.execute(
        text("INSERT INTO capability (id, name, scope) VALUES (:id, :name, :scope)"),
        {"id": uuid.uuid4(), "name": "ticket.reply", "scope": "tenant"},
    )
    await db.commit()

    async with _client(app) as c:
        r = await c.post(
            "/api/v1/admin/roles",
            json={"name": "quiere-lo-que-no-tiene", "capabilities": ["ticket.reply"]},
            headers=_auth_header(token),
        )

    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")


async def test_editing_a_system_role_is_rejected(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    _admin, token = await _admin_with_capability(
        db, tenant=tenant, capability="role.manage", scope="tenant"
    )
    system_role = await SqlAlchemyRoleRepository(db).add(
        Role(id=uuid.uuid4(), name="support_admin", kind=RoleKind.system, tenant_id=None)
    )
    await db.commit()

    async with _client(app) as c:
        r = await c.patch(
            f"/api/v1/admin/roles/{system_role.id}",
            json={"name": "renombrado", "capabilities": []},
            headers=_auth_header(token),
        )

    assert r.status_code == 409
    assert r.headers["content-type"].startswith("application/problem+json")


# ── auditoría ──


async def test_creating_a_tenant_is_audited(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    _admin, token = await _admin_with_capability(
        db, tenant=tenant, capability="tenant.manage", scope="global"
    )

    async with _client(app) as c:
        r = await c.post(
            "/api/v1/admin/tenants",
            json={"slug": f"nuevo-{uuid.uuid4()}", "name": "Nuevo"},
            headers=_auth_header(token),
        )

    assert r.status_code == 201
    new_tenant_id = r.json()["id"]
    row = (
        await db.execute(
            text("SELECT action, entity_id FROM audit_log WHERE action = 'tenant.created'")
        )
    ).one()
    assert row.entity_id == new_tenant_id
