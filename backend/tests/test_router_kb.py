"""Tests de integración del router `kb` (tarea `backend-routers-core-09`): superficie HTTP sobre el
adaptador STUB (`StubVectorStore`) — resultados vacíos/deterministas, comportamiento esperado hasta la
tarea 14. KB es global (sin RLS) — `superuser_engine` de sobra, igual que `test_router_admin.py`.
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
    "TRUNCATE user_tenant, refresh_session, auth_token, user_role, role_capability, "
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


def _make_tenant() -> Tenant:
    return Tenant(
        id=uuid.uuid4(), slug=f"t-{uuid.uuid4()}", name="Tenant", status=TenantStatus.active
    )


async def _make_user(db: AsyncSession) -> User:
    return await SqlAlchemyUserRepository(db).add(
        User(
            id=uuid.uuid4(),
            email=f"u-{uuid.uuid4()}@example.com",
            password_hash=hash_password("pw"),
        )
    )


async def _add_membership(db: AsyncSession, *, user_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    await SqlAlchemyUserTenantMembershipRepository(db).add(
        UserTenantMembership(user_id=user_id, tenant_id=tenant_id, status=UserStatus.active)
    )


async def _grant_capability(
    db: AsyncSession, *, user_id: uuid.UUID, tenant_id: uuid.UUID, capability: str
) -> None:
    role_repo = SqlAlchemyRoleRepository(db)
    role = await role_repo.add(
        Role(
            id=uuid.uuid4(), name=f"role-{uuid.uuid4()}", kind=RoleKind.tenant, tenant_id=tenant_id
        )
    )
    existing_capability_id = (
        await db.execute(text("SELECT id FROM capability WHERE name = :name"), {"name": capability})
    ).scalar_one_or_none()
    if existing_capability_id is None:
        capability_id = uuid.uuid4()
        await db.execute(
            text("INSERT INTO capability (id, name, scope) VALUES (:id, :name, 'tenant')"),
            {"id": capability_id, "name": capability},
        )
    else:
        capability_id = existing_capability_id
    await db.execute(
        text("INSERT INTO role_capability (role_id, capability_id) VALUES (:r, :c)"),
        {"r": role.id, "c": capability_id},
    )
    await role_repo.assign(user_id, role.id, tenant_id)
    await db.commit()


def _access_token(user_id: uuid.UUID, tenant_id: uuid.UUID) -> str:
    return create_access_token(
        str(user_id),
        str(tenant_id),
        secret=_JWT_SECRET,
        algorithm=JWT_ALGORITHM,
        ttl=_TTL,
        now=datetime.now(UTC),
    )


async def _agent(db: AsyncSession, *, tenant: Tenant, with_capability: bool) -> str:
    user = await _make_user(db)
    await _add_membership(db, user_id=user.id, tenant_id=tenant.id)
    if with_capability:
        await _grant_capability(db, user_id=user.id, tenant_id=tenant.id, capability="kb.read")
    return _access_token(user.id, tenant.id)


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_search_without_kb_read_is_forbidden(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token = await _agent(db, tenant=tenant, with_capability=False)

    async with _client(app) as c:
        r = await c.get("/api/v1/kb/search", params={"q": "algo"}, headers=_auth_header(token))

    assert r.status_code == 403
    assert r.headers["content-type"].startswith("application/problem+json")


async def test_search_with_kb_read_returns_an_empty_deterministic_page(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token = await _agent(db, tenant=tenant, with_capability=True)

    async with _client(app) as c:
        r = await c.get("/api/v1/kb/search", params={"q": "algo"}, headers=_auth_header(token))

    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0


async def test_search_without_q_is_rejected(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token = await _agent(db, tenant=tenant, with_capability=True)

    async with _client(app) as c:
        r = await c.get("/api/v1/kb/search", headers=_auth_header(token))

    assert r.status_code == 422


async def test_list_documents_returns_an_empty_deterministic_page(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token = await _agent(db, tenant=tenant, with_capability=True)

    async with _client(app) as c:
        r = await c.get("/api/v1/kb/documents", headers=_auth_header(token))

    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0


async def test_list_documents_without_kb_read_is_forbidden(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token = await _agent(db, tenant=tenant, with_capability=False)

    async with _client(app) as c:
        r = await c.get("/api/v1/kb/documents", headers=_auth_header(token))

    assert r.status_code == 403


async def test_get_document_returns_404(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token = await _agent(db, tenant=tenant, with_capability=True)

    async with _client(app) as c:
        r = await c.get("/api/v1/kb/documents/UC-API-001", headers=_auth_header(token))

    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")


async def test_get_document_without_kb_read_is_forbidden(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token = await _agent(db, tenant=tenant, with_capability=False)

    async with _client(app) as c:
        r = await c.get("/api/v1/kb/documents/UC-API-001", headers=_auth_header(token))

    assert r.status_code == 403


async def test_search_does_not_depend_on_the_subjects_tenant(
    app: FastAPI, db: AsyncSession
) -> None:
    """KB no filtra por tenant (recurso global) — dos subjects de tenants DISTINTOS, ambos con
    kb.read, obtienen la misma respuesta (vacía hoy)."""
    tenant_a = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    tenant_b = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token_a = await _agent(db, tenant=tenant_a, with_capability=True)
    token_b = await _agent(db, tenant=tenant_b, with_capability=True)

    async with _client(app) as c:
        r_a = await c.get("/api/v1/kb/search", params={"q": "algo"}, headers=_auth_header(token_a))
        r_b = await c.get("/api/v1/kb/search", params={"q": "algo"}, headers=_auth_header(token_b))

    assert r_a.status_code == r_b.status_code == 200
    assert r_a.json() == r_b.json()


async def test_search_rejects_page_size_out_of_range(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token = await _agent(db, tenant=tenant, with_capability=True)

    async with _client(app) as c:
        too_low = await c.get(
            "/api/v1/kb/search",
            params={"q": "algo", "page_size": 0},
            headers=_auth_header(token),
        )
        too_high = await c.get(
            "/api/v1/kb/search",
            params={"q": "algo", "page_size": 101},
            headers=_auth_header(token),
        )
        at_limit = await c.get(
            "/api/v1/kb/search",
            params={"q": "algo", "page_size": 100},
            headers=_auth_header(token),
        )

    assert too_low.status_code == 422
    assert too_high.status_code == 422
    assert at_limit.status_code == 200


async def test_search_rejects_an_invalid_domain_filter(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token = await _agent(db, tenant=tenant, with_capability=True)

    async with _client(app) as c:
        r = await c.get(
            "/api/v1/kb/search",
            params={"q": "algo", "domain": "no-es-un-dominio"},
            headers=_auth_header(token),
        )

    assert r.status_code == 422
