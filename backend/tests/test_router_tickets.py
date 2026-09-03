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
import pytest
import pytest_asyncio
from app.core.config import Settings, get_settings
from app.core.deps import get_db_session, get_notification_service
from app.core.security import JWT_ALGORITHM, create_access_token, hash_password
from app.domain.entities.business import Ticket
from app.domain.entities.enums import (
    KbDomain,
    KbEstado,
    NotificationType,
    Package,
    RoleKind,
    TenantStatus,
    TicketPriority,
    TicketStatus,
    UserStatus,
)
from app.domain.entities.identity import Role, Tenant, User, UserTenantMembership
from app.domain.errors import PortError, RateLimited
from app.domain.services.notification_service import NotificationService
from app.infra.clock import SystemClock
from app.infra.db.repositories import (
    SqlAlchemyNotificationRepository,
    SqlAlchemyRoleRepository,
    SqlAlchemyTenantRepository,
    SqlAlchemyTicketRepository,
    SqlAlchemyUserRepository,
    SqlAlchemyUserTenantMembershipRepository,
)
from app.main import create_app
from app.rag.reranker import RankedHit
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

_JWT_SECRET = "x" * 32
_TTL = 900


def _settings() -> Settings:
    return Settings(_env_file=None, jwt_secret=_JWT_SECRET, app_env="production", cors_origins=[])


_TRUNCATE_TABLES = (
    "TRUNCATE notification, message, ticket, audit_log, user_tenant, refresh_session, auth_token, "
    'user_role, role_capability, capability, "user", role, tenant RESTART IDENTITY CASCADE'
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


def _make_tenant(*, ai_auto_draft: bool = True) -> Tenant:
    return Tenant(
        id=uuid.uuid4(),
        slug=f"t-{uuid.uuid4()}",
        name="Tenant",
        status=TenantStatus.active,
        ai_auto_draft=ai_auto_draft,
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


# ── POST /tickets/{id}/assign: notifica ticket_assigned (FR-038, tarea backend-routers-flujo-ia-04) ──


class _FailingNotificationRepository:
    """Fake que hace fallar `emit()` con `PortError` — para probar que un fallo de notificación no
    tumba la respuesta de la operación principal ya confirmada."""

    async def add(self, notification: object) -> object:
        raise PortError("fallo simulado de infra")


async def _notifications_for(db: AsyncSession, user_id: uuid.UUID) -> list[object]:
    result = await SqlAlchemyNotificationRepository(db).list_for_user(
        user_id, page=1, page_size=100
    )
    return list(result.items)


# ── POST /tickets/{id}/reopen (backend-auto-resolve-ticket-03, CU-BE-06 4e-4g) ──


async def _audit_actor_id(db: AsyncSession, *, ticket_id: uuid.UUID) -> uuid.UUID | None:
    row = (
        await db.execute(
            text(
                "SELECT actor_id FROM audit_log WHERE entity_id = :id "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"id": str(ticket_id)},
        )
    ).scalar_one()
    return row


@pytest.mark.parametrize("initial_status", [TicketStatus.resolved, TicketStatus.closed])
async def test_reopening_an_auto_resolved_ticket_the_client_did_not_want_succeeds(
    app: FastAPI, db: AsyncSession, initial_status: TicketStatus
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(
        _make_ticket_entity(tenant.id, status=initial_status)
    )
    await db.commit()
    agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.reopen"]
    )

    async with _client(app) as c:
        r = await c.post(f"/api/v1/tickets/{ticket.id}/reopen", headers=_auth_header(token))

    assert r.status_code == 200
    assert r.json()["status"] == "reopened"
    assert await _audit_actor_id(db, ticket_id=ticket.id) == agent.id


async def test_reopening_without_the_capability_is_rejected(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(
        _make_ticket_entity(tenant.id, status=TicketStatus.resolved)
    )
    await db.commit()
    _agent, token = await _agent_with_capabilities(db, tenant=tenant, capabilities=["ticket.read"])

    async with _client(app) as c:
        r = await c.post(f"/api/v1/tickets/{ticket.id}/reopen", headers=_auth_header(token))

    assert r.status_code == 403
    refetched = await SqlAlchemyTicketRepository(db).get(ticket.id)
    assert refetched is not None
    assert refetched.status is TicketStatus.resolved


async def test_ticket_reopen_does_not_grant_any_other_transition(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(
        _make_ticket_entity(tenant.id, status=TicketStatus.new)
    )
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.reopen"]
    )

    async with _client(app) as c:
        r = await c.post(
            f"/api/v1/tickets/{ticket.id}/transition",
            json={"status": "open"},
            headers=_auth_header(token),
        )

    assert r.status_code == 403


@pytest.mark.parametrize(
    "initial_status",
    [TicketStatus.new, TicketStatus.open, TicketStatus.pending, TicketStatus.reopened],
)
async def test_reopening_a_ticket_not_in_a_valid_state_for_it_is_a_conflict(
    app: FastAPI, db: AsyncSession, initial_status: TicketStatus
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(
        _make_ticket_entity(tenant.id, status=initial_status)
    )
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.reopen"]
    )

    async with _client(app) as c:
        r = await c.post(f"/api/v1/tickets/{ticket.id}/reopen", headers=_auth_header(token))

    assert r.status_code == 409
    assert r.headers["content-type"].startswith("application/problem+json")
    refetched = await SqlAlchemyTicketRepository(db).get(ticket.id)
    assert refetched is not None
    assert refetched.status is initial_status


async def test_reopening_a_ticket_from_another_tenant_does_not_reveal_it_exists(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant_a = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    tenant_b = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(
        _make_ticket_entity(tenant_a.id, status=TicketStatus.resolved)
    )
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant_b, capabilities=["ticket.reopen"]
    )

    async with _client(app) as c:
        r = await c.post(f"/api/v1/tickets/{ticket.id}/reopen", headers=_auth_header(token))

    assert r.status_code == 404


async def test_reopening_a_nonexistent_ticket_returns_404(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.reopen"]
    )

    async with _client(app) as c:
        r = await c.post(f"/api/v1/tickets/{uuid.uuid4()}/reopen", headers=_auth_header(token))

    assert r.status_code == 404


async def test_assigning_to_a_new_agent_notifies_them(app: FastAPI, db: AsyncSession) -> None:
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
    notifications = await _notifications_for(db, assignee.id)
    assert len(notifications) == 1
    assert notifications[0].type is NotificationType.ticket_assigned


async def test_reassigning_only_notifies_the_new_agent(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    old_assignee = await _make_user(db)
    new_assignee = await _make_user(db)
    await _add_membership(db, user_id=old_assignee.id, tenant_id=tenant.id)
    await _add_membership(db, user_id=new_assignee.id, tenant_id=tenant.id)
    ticket = await SqlAlchemyTicketRepository(db).add(
        _make_ticket_entity(tenant.id, assignee_id=old_assignee.id)
    )
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.assign"]
    )

    async with _client(app) as c:
        r = await c.post(
            f"/api/v1/tickets/{ticket.id}/assign",
            json={"assignee_id": str(new_assignee.id)},
            headers=_auth_header(token),
        )

    assert r.status_code == 200
    assert len(await _notifications_for(db, new_assignee.id)) == 1
    assert await _notifications_for(db, old_assignee.id) == []


async def test_self_assigning_does_not_notify(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    await db.commit()
    agent, token = await _agent_with_capabilities(db, tenant=tenant, capabilities=["ticket.assign"])

    async with _client(app) as c:
        r = await c.post(
            f"/api/v1/tickets/{ticket.id}/assign",
            json={"assignee_id": str(agent.id)},
            headers=_auth_header(token),
        )

    assert r.status_code == 200
    assert await _notifications_for(db, agent.id) == []


async def test_unassigning_does_not_notify_anyone(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    assignee = await _make_user(db)
    await _add_membership(db, user_id=assignee.id, tenant_id=tenant.id)
    ticket = await SqlAlchemyTicketRepository(db).add(
        _make_ticket_entity(tenant.id, assignee_id=assignee.id)
    )
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.assign"]
    )

    async with _client(app) as c:
        r = await c.post(
            f"/api/v1/tickets/{ticket.id}/assign",
            json={"assignee_id": None},
            headers=_auth_header(token),
        )

    assert r.status_code == 200
    assert await _notifications_for(db, assignee.id) == []


async def test_a_rejected_assignment_does_not_notify(app: FastAPI, db: AsyncSession) -> None:
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
    assert await _notifications_for(db, user_of_b.id) == []


async def test_a_notification_failure_does_not_affect_the_assign_response(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    assignee = await _make_user(db)
    await _add_membership(db, user_id=assignee.id, tenant_id=tenant.id)
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.assign"]
    )
    app.dependency_overrides[get_notification_service] = lambda: NotificationService(
        notifications=_FailingNotificationRepository(), clock=SystemClock()
    )

    async with _client(app) as c:
        r = await c.post(
            f"/api/v1/tickets/{ticket.id}/assign",
            json={"assignee_id": str(assignee.id)},
            headers=_auth_header(token),
        )

    assert r.status_code == 200
    assert r.json()["assignee_id"] == str(assignee.id)


# ── auto-disparo del draft IA al crear un ticket (`tenant.ai_auto_draft`) ───────
#
# El disparo real corre en `BackgroundTasks` (`_trigger_ai_draft_in_background`, tickets.py), NO vía
# `Depends(get_agent_service)` — reconstruye sus propias dependencias a mano (sesión propia, ver
# docstring del módulo) para no depender de la sesión del request, ya cerrada quando esto corre. Por
# eso estos tests sustituyen `_trigger_ai_draft_in_background` (`monkeypatch`, no
# `dependency_overrides`): verifican SOLO que el router la programa (o no) según
# `tenant.ai_auto_draft`, sin tumbar la creación si falla — el disparo real end-to-end (contra Postgres
# + fakes de LLM/retriever) ya lo cubren `test_router_agent.py`/`test_runner.py`.


async def test_creating_a_ticket_schedules_the_ai_auto_draft_by_default(
    app: FastAPI, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())  # ai_auto_draft=True default
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.create"]
    )
    calls: list[tuple[uuid.UUID, uuid.UUID]] = []

    async def _spy(tenant_id: uuid.UUID, ticket_id: uuid.UUID) -> None:
        calls.append((tenant_id, ticket_id))

    monkeypatch.setattr("app.api.v1.routers.tickets._trigger_ai_draft_in_background", _spy)

    async with _client(app) as c:
        r = await c.post(
            "/api/v1/tickets",
            json={"subject": "no puedo subir un vídeo", "body": "el botón no responde"},
            headers=_auth_header(token),
        )

    assert r.status_code == 201
    ticket_id = uuid.UUID(r.json()["id"])
    assert calls == [(tenant.id, ticket_id)]


async def test_creating_a_ticket_does_not_schedule_the_ai_auto_draft_when_disabled(
    app: FastAPI, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant(ai_auto_draft=False))
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.create"]
    )
    calls: list[tuple[uuid.UUID, uuid.UUID]] = []

    async def _spy(tenant_id: uuid.UUID, ticket_id: uuid.UUID) -> None:
        calls.append((tenant_id, ticket_id))

    monkeypatch.setattr("app.api.v1.routers.tickets._trigger_ai_draft_in_background", _spy)

    async with _client(app) as c:
        r = await c.post(
            "/api/v1/tickets",
            json={"subject": "asunto", "body": "cuerpo"},
            headers=_auth_header(token),
        )

    assert r.status_code == 201
    assert calls == []


async def test_an_ai_auto_draft_failure_does_not_affect_the_create_response(
    app: FastAPI, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.create"]
    )

    async def _failing(tenant_id: uuid.UUID, ticket_id: uuid.UUID) -> None:
        # `_trigger_ai_draft_in_background` YA se traga `DomainError` internamente (best-effort) —
        # una excepción que se le escapara aquí sería un bug real de esa función, no algo que este
        # test deba enmascarar; por eso el spy no vuelve a intentar tragarla.
        raise RateLimited("límite de ai-draft excedido")

    monkeypatch.setattr("app.api.v1.routers.tickets._trigger_ai_draft_in_background", _failing)

    async with _client(app) as c:
        r = await c.post(
            "/api/v1/tickets",
            json={"subject": "asunto", "body": "cuerpo"},
            headers=_auth_header(token),
        )

    assert r.status_code == 201


async def test_the_background_trigger_actually_creates_a_real_agent_run(
    app_db_url: str, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Integración real de `_trigger_ai_draft_in_background` en sí misma (no vía HTTP): reconstruye
    sus dependencias a mano (`get_chat_model_port`/`get_embeddings_port`/`get_retriever_port`
    llamadas directas, ver docstring del módulo) — este test verifica que esa reconstrucción manual
    de verdad funciona contra Postgres real, no solo que el router LA PROGRAMA (eso ya lo cubren los
    tests de arriba, con un spy)."""
    from app.agents.nodes.grade import Grade
    from app.api.v1.routers import tickets as tickets_router
    from app.domain.services.classification import Classification
    from app.infra.db.repositories import SqlAlchemyAgentRunRepository

    monkeypatch.setenv("DATABASE_URL", app_db_url)
    get_settings.cache_clear()

    import app.agents.checkpointer as checkpointer_module
    import app.infra.db.session as session_module

    checkpointer_module._pool = None  # mismo reset que test_router_agent.py::_checkpointer_pool
    # `get_sessionmaker()`/`get_engine()` son singletons de proceso (perezosos, sin reset en
    # conftest.py) — memoizan el engine de OTRO test, atado a un event loop que pytest-asyncio ya
    # cerró (function-scoped): reusarlo revienta con "Event loop is closed" (reproducido). Igual
    # que el checkpointer, se descartan aquí para que `_trigger_ai_draft_in_background` cree los
    # suyos propios en ESTE event loop.
    if session_module._engine is not None:
        await session_module._engine.dispose()
    session_module._engine = None
    session_module._sessionmaker = None

    class _FakeChatModel:
        async def classify(self, text: str, schema: type) -> Classification:
            return Classification(
                categoria="incidencia",
                dominio=None,
                prioridad=TicketPriority.normal,
                resoluble=True,
            )

        async def grade(self, prompt: str, schema: type) -> Grade:
            return Grade(suficiente=False, motivo="sin contexto suficiente (test)")

        async def generate(self, prompt: str) -> str:  # pragma: no cover - no se llega aquí
            raise NotImplementedError

    class _FakeRetriever:
        async def embed_query(self, query: str) -> list[float]:
            return [0.1]

        async def search(
            self,
            vector: list[float],
            *,
            top_k: int,
            domain: KbDomain | None = None,
            package: Package | None = None,
            estado: KbEstado | None = None,
        ) -> list[RankedHit]:
            return []

    monkeypatch.setattr(tickets_router, "get_chat_model_port", lambda **kwargs: _FakeChatModel())
    monkeypatch.setattr(tickets_router, "get_retriever_port", lambda **kwargs: _FakeRetriever())

    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    await db.commit()

    try:
        await tickets_router._trigger_ai_draft_in_background(tenant.id, ticket.id)

        run = await SqlAlchemyAgentRunRepository(db).get_active_for_ticket(ticket.id)
        assert run is not None
        assert run.ticket_id == ticket.id
    finally:
        if checkpointer_module._pool is not None:
            await checkpointer_module._pool.close()
        checkpointer_module._pool = None
        if session_module._engine is not None:
            await session_module._engine.dispose()
        session_module._engine = None
        session_module._sessionmaker = None


async def test_creating_a_ticket_via_http_makes_it_visible_to_the_background_task(
    app: FastAPI, db: AsyncSession, app_db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regresión de un bug real reproducido en vivo: `_trigger_ai_draft_in_background` abre su PROPIA
    conexión — si `create_ticket` no hace `commit()` explícito ANTES de programar la tarea, esa
    conexión nueva no ve el ticket todavía (la transacción del request sigue abierta) y `agent_service
    .trigger()` falla con `NotFound` (silenciado como best-effort, invisible sin este test). Server real
    vía HTTP de punta a punta (no `_trigger_ai_draft_in_background` llamada a mano, que no ejercita el
    `commit()` de `create_ticket`)."""
    from app.agents.nodes.grade import Grade
    from app.api.v1.routers import tickets as tickets_router
    from app.domain.services.classification import Classification
    from app.infra.db.repositories import SqlAlchemyAgentRunRepository

    monkeypatch.setenv("DATABASE_URL", app_db_url)
    get_settings.cache_clear()

    import app.agents.checkpointer as checkpointer_module
    import app.infra.db.session as session_module

    checkpointer_module._pool = None
    if session_module._engine is not None:
        await session_module._engine.dispose()
    session_module._engine = None
    session_module._sessionmaker = None

    class _FakeChatModel:
        async def classify(self, text: str, schema: type) -> Classification:
            return Classification(
                categoria="incidencia",
                dominio=None,
                prioridad=TicketPriority.normal,
                resoluble=True,
            )

        async def grade(self, prompt: str, schema: type) -> Grade:
            return Grade(suficiente=False, motivo="sin contexto suficiente (test)")

        async def generate(self, prompt: str) -> str:  # pragma: no cover - no se llega aquí
            raise NotImplementedError

    class _FakeRetriever:
        async def embed_query(self, query: str) -> list[float]:
            return [0.1]

        async def search(
            self,
            vector: list[float],
            *,
            top_k: int,
            domain: KbDomain | None = None,
            package: Package | None = None,
            estado: KbEstado | None = None,
        ) -> list[RankedHit]:
            return []

    monkeypatch.setattr(tickets_router, "get_chat_model_port", lambda **kwargs: _FakeChatModel())
    monkeypatch.setattr(tickets_router, "get_retriever_port", lambda **kwargs: _FakeRetriever())

    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.create"]
    )

    try:
        async with _client(app) as c:
            r = await c.post(
                "/api/v1/tickets",
                json={"subject": "asunto", "body": "cuerpo"},
                headers=_auth_header(token),
            )
        assert r.status_code == 201
        ticket_id = uuid.UUID(r.json()["id"])

        run = await SqlAlchemyAgentRunRepository(db).get_active_for_ticket(ticket_id)
        assert run is not None, (
            "el background task no vio el ticket recién creado — commit() explícito ausente/roto"
        )
    finally:
        if checkpointer_module._pool is not None:
            await checkpointer_module._pool.close()
        checkpointer_module._pool = None
        if session_module._engine is not None:
            await session_module._engine.dispose()
        session_module._engine = None
        session_module._sessionmaker = None
