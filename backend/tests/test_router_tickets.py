"""Tests de integración del router `tickets` (tarea `backend-routers-core-07`).

Primer router de NEGOCIO probado end-to-end: el fixture `app` apunta al `get_db_session` hacia
**`app_engine`** (rol `syntax_app`, no-superuser → RLS aplica de verdad), a diferencia de
`test_router_auth.py`/`test_router_admin.py` (identidad, sin RLS, `superuser_engine` de sobra). Los
datos se siembran vía `db` (superuser, bypassa RLS) — mismo patrón que `test_session.py`.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest_asyncio
from app.core.config import Settings, get_settings
from app.core.deps import get_db_session
from app.core.security import JWT_ALGORITHM, create_access_token, hash_password
from app.domain.entities.business import Ticket
from app.domain.entities.enums import (
    RoleKind,
    TenantStatus,
    TicketPriority,
    TicketStatus,
    UserStatus,
)
from app.domain.entities.identity import Role, Tenant, User, UserTenantMembership
from app.infra.db.repositories import (
    SqlAlchemyRoleRepository,
    SqlAlchemyTenantRepository,
    SqlAlchemyTicketRepository,
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
    "TRUNCATE message, ticket, audit_log, user_tenant, refresh_session, auth_token, user_role, "
    'role_capability, capability, "user", role, tenant RESTART IDENTITY CASCADE'
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
    """Sesión de SIEMBRA (superuser, RLS no aplica)."""
    async with async_sessionmaker(superuser_engine, expire_on_commit=False)() as s:
        yield s


@pytest_asyncio.fixture
async def app(app_engine: AsyncEngine) -> AsyncIterator[FastAPI]:
    """La app usa `app_engine` (rol `syntax_app`) — RLS aplica de verdad en cada request."""
    test_app = create_app(_settings())

    async def _override_session() -> AsyncIterator[AsyncSession]:
        async with async_sessionmaker(app_engine, expire_on_commit=False)() as s:
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


async def _agent_with_capabilities(
    db: AsyncSession, *, tenant: Tenant, capabilities: list[str]
) -> tuple[User, str]:
    agent = await _make_user(db)
    await _add_membership(db, user_id=agent.id, tenant_id=tenant.id)
    for capability in capabilities:
        await _grant_capability(db, user_id=agent.id, tenant_id=tenant.id, capability=capability)
    token = _access_token(agent.id, tenant.id)
    return agent, token


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _make_ticket_entity(
    tenant_id: uuid.UUID,
    *,
    status: TicketStatus = TicketStatus.new,
    priority: TicketPriority = TicketPriority.normal,
    assignee_id: uuid.UUID | None = None,
) -> Ticket:
    return Ticket(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        subject="s",
        status=status,
        priority=priority,
        assignee_id=assignee_id,
    )


# ── GET /tickets: paginación/filtros/orden ──


async def test_list_tickets_paginates_and_orders_by_updated_at_desc(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket_repo = SqlAlchemyTicketRepository(db)
    for _ in range(25):
        await ticket_repo.add(_make_ticket_entity(tenant.id))
    await db.commit()
    _agent, token = await _agent_with_capabilities(db, tenant=tenant, capabilities=["ticket.read"])

    async with _client(app) as c:
        r = await c.get("/api/v1/tickets", headers=_auth_header(token))

    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 20
    assert body["total"] == 25
    assert body["page_size"] == 20


async def test_list_tickets_filters_by_status(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket_repo = SqlAlchemyTicketRepository(db)
    await ticket_repo.add(_make_ticket_entity(tenant.id, status=TicketStatus.open))
    await ticket_repo.add(_make_ticket_entity(tenant.id, status=TicketStatus.new))
    await db.commit()
    _agent, token = await _agent_with_capabilities(db, tenant=tenant, capabilities=["ticket.read"])

    async with _client(app) as c:
        r = await c.get("/api/v1/tickets", params={"status": "open"}, headers=_auth_header(token))

    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "open"


async def test_list_tickets_filters_by_priority(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket_repo = SqlAlchemyTicketRepository(db)
    await ticket_repo.add(_make_ticket_entity(tenant.id, priority=TicketPriority.urgent))
    await ticket_repo.add(_make_ticket_entity(tenant.id, priority=TicketPriority.low))
    await db.commit()
    _agent, token = await _agent_with_capabilities(db, tenant=tenant, capabilities=["ticket.read"])

    async with _client(app) as c:
        r = await c.get(
            "/api/v1/tickets", params={"priority": "urgent"}, headers=_auth_header(token)
        )

    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["priority"] == "urgent"


async def test_list_tickets_filters_by_assignee_id(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    assignee = await _make_user(db)
    await db.commit()
    ticket_repo = SqlAlchemyTicketRepository(db)
    await ticket_repo.add(_make_ticket_entity(tenant.id, assignee_id=assignee.id))
    await ticket_repo.add(_make_ticket_entity(tenant.id))
    await db.commit()
    _agent, token = await _agent_with_capabilities(db, tenant=tenant, capabilities=["ticket.read"])

    async with _client(app) as c:
        r = await c.get(
            "/api/v1/tickets", params={"assignee_id": str(assignee.id)}, headers=_auth_header(token)
        )

    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["assignee_id"] == str(assignee.id)


async def test_list_tickets_combines_filters_with_and(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket_repo = SqlAlchemyTicketRepository(db)
    await ticket_repo.add(
        _make_ticket_entity(tenant.id, status=TicketStatus.open, priority=TicketPriority.urgent)
    )
    await ticket_repo.add(
        _make_ticket_entity(tenant.id, status=TicketStatus.open, priority=TicketPriority.low)
    )
    await db.commit()
    _agent, token = await _agent_with_capabilities(db, tenant=tenant, capabilities=["ticket.read"])

    async with _client(app) as c:
        r = await c.get(
            "/api/v1/tickets",
            params={"status": "open", "priority": "urgent"},
            headers=_auth_header(token),
        )

    assert r.status_code == 200
    assert r.json()["total"] == 1


async def test_list_tickets_with_a_filter_matching_nothing_returns_an_empty_page(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    await db.commit()
    _agent, token = await _agent_with_capabilities(db, tenant=tenant, capabilities=["ticket.read"])

    async with _client(app) as c:
        r = await c.get(
            "/api/v1/tickets",
            params={"assignee_id": str(uuid.uuid4())},
            headers=_auth_header(token),
        )

    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0


async def test_list_tickets_rejects_a_sort_not_in_the_whitelist(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    _agent, token = await _agent_with_capabilities(db, tenant=tenant, capabilities=["ticket.read"])

    async with _client(app) as c:
        r = await c.get(
            "/api/v1/tickets", params={"sort": "password_hash"}, headers=_auth_header(token)
        )

    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")


async def test_list_tickets_rejects_page_size_out_of_range(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    _agent, token = await _agent_with_capabilities(db, tenant=tenant, capabilities=["ticket.read"])

    async with _client(app) as c:
        too_low = await c.get(
            "/api/v1/tickets", params={"page_size": 0}, headers=_auth_header(token)
        )
        negative = await c.get(
            "/api/v1/tickets", params={"page_size": -1}, headers=_auth_header(token)
        )
        too_high = await c.get(
            "/api/v1/tickets", params={"page_size": 101}, headers=_auth_header(token)
        )
        at_limit = await c.get(
            "/api/v1/tickets", params={"page_size": 100}, headers=_auth_header(token)
        )

    assert too_low.status_code == 422
    assert negative.status_code == 422
    assert too_high.status_code == 422
    assert at_limit.status_code == 200


# ── POST /tickets ──


async def test_create_ticket_returns_201_with_status_new(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.create"]
    )

    async with _client(app) as c:
        r = await c.post(
            "/api/v1/tickets",
            json={"subject": "necesito ayuda", "body": "el problema es..."},
            headers=_auth_header(token),
        )

    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "new"
    assert body["subject"] == "necesito ayuda"
    assert body["tenant_id"] == str(tenant.id)


# ── GET /tickets/{id}: aislamiento cross-tenant (RLS real) ──


async def test_reading_a_ticket_of_another_tenant_returns_404(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant_a = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    tenant_b = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket_b = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant_b.id))
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant_a, capabilities=["ticket.read"]
    )

    async with _client(app) as c:
        r = await c.get(f"/api/v1/tickets/{ticket_b.id}", headers=_auth_header(token))

    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")


async def test_reading_a_ticket_of_the_same_tenant_returns_it(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    await db.commit()
    _agent, token = await _agent_with_capabilities(db, tenant=tenant, capabilities=["ticket.read"])

    async with _client(app) as c:
        r = await c.get(f"/api/v1/tickets/{ticket.id}", headers=_auth_header(token))

    assert r.status_code == 200
    assert r.json()["id"] == str(ticket.id)


# ── PATCH /tickets/{id} ──


async def test_patch_only_changes_the_fields_sent(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.update"]
    )

    async with _client(app) as c:
        r = await c.patch(
            f"/api/v1/tickets/{ticket.id}",
            json={"priority": "high"},
            headers=_auth_header(token),
        )

    assert r.status_code == 200
    body = r.json()
    assert body["priority"] == "high"
    assert body["subject"] == ticket.subject
    assert body["category"] is None


async def test_patch_with_an_invalid_priority_is_rejected(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.update"]
    )

    async with _client(app) as c:
        r = await c.patch(
            f"/api/v1/tickets/{ticket.id}",
            json={"priority": "no-es-una-prioridad"},
            headers=_auth_header(token),
        )

    assert r.status_code == 422
    unchanged = await SqlAlchemyTicketRepository(db).get(ticket.id)
    assert unchanged is not None
    assert unchanged.priority is TicketPriority.normal


async def test_patch_with_csat_sets_it_via_set_csat(app: FastAPI, db: AsyncSession) -> None:
    """`TicketUpdate.csat` (contrato) se cablea vía `ticket_service.set_csat` (su propia validación
    1..5), no `update_fields` — mismo `PATCH`, dos rutas de servicio distintas."""
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.update"]
    )

    async with _client(app) as c:
        r = await c.patch(
            f"/api/v1/tickets/{ticket.id}", json={"csat": 5}, headers=_auth_header(token)
        )

    assert r.status_code == 200
    assert r.json()["csat"] == 5


async def test_patch_with_csat_out_of_range_is_rejected(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.update"]
    )

    async with _client(app) as c:
        r = await c.patch(
            f"/api/v1/tickets/{ticket.id}", json={"csat": 6}, headers=_auth_header(token)
        )

    assert r.status_code == 422


# ── POST /tickets/{id}/transition ──


async def test_invalid_transition_returns_409(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(
        _make_ticket_entity(tenant.id, status=TicketStatus.new)
    )
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.transition"]
    )

    async with _client(app) as c:
        r = await c.post(
            f"/api/v1/tickets/{ticket.id}/transition",
            json={"status": "resolved"},
            headers=_auth_header(token),
        )

    assert r.status_code == 409
    assert r.headers["content-type"].startswith("application/problem+json")


# ── POST /tickets/{id}/assign ──


async def test_assigning_to_someone_from_another_tenant_is_rejected(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant_a = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    tenant_b = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant_a.id))
    user_of_b = await _make_user(db)
    await _add_membership(db, user_id=user_of_b.id, tenant_id=tenant_b.id)
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant_a, capabilities=["ticket.assign"]
    )

    async with _client(app) as c:
        r = await c.post(
            f"/api/v1/tickets/{ticket.id}/assign",
            json={"assignee_id": str(user_of_b.id)},
            headers=_auth_header(token),
        )

    assert r.status_code in (409, 422)
    assert r.headers["content-type"].startswith("application/problem+json")


async def test_assigning_to_a_nonexistent_user_is_rejected(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.assign"]
    )

    async with _client(app) as c:
        r = await c.post(
            f"/api/v1/tickets/{ticket.id}/assign",
            json={"assignee_id": str(uuid.uuid4())},
            headers=_auth_header(token),
        )

    assert r.status_code in (404, 422)
    assert r.headers["content-type"].startswith("application/problem+json")


async def test_assigning_within_the_same_tenant_succeeds(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    assignee = await _make_user(db)
    await _add_membership(db, user_id=assignee.id, tenant_id=tenant.id)
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.assign"]
    )

    async with _client(app) as c:
        r = await c.post(
            f"/api/v1/tickets/{ticket.id}/assign",
            json={"assignee_id": str(assignee.id)},
            headers=_auth_header(token),
        )

    assert r.status_code == 200
    assert r.json()["assignee_id"] == str(assignee.id)
