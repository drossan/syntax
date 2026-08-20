"""Tests de integración del router `analytics` (tarea `backend-routers-flujo-ia-05`).

`app` apunta a `app_engine` (rol `syntax_app`, RLS real). 1:1 con el `## Scenarios (Gherkin)` de la
tarea.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest_asyncio
from app.core.config import Settings, get_settings
from app.core.deps import get_db_session
from app.core.security import JWT_ALGORITHM, create_access_token, hash_password
from app.domain.entities.business import AgentRun, ApprovalTask, Ticket
from app.domain.entities.enums import (
    AgentRunStatus,
    ApprovalStatus,
    RoleKind,
    TenantStatus,
    TicketPriority,
    TicketStatus,
    UserStatus,
)
from app.domain.entities.identity import Role, Tenant, User, UserTenantMembership
from app.infra.db.repositories import (
    SqlAlchemyAgentRunRepository,
    SqlAlchemyApprovalRepository,
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
    "TRUNCATE approval_task, agent_run, ticket, audit_log, user_tenant, refresh_session, auth_token, "
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
    async with async_sessionmaker(superuser_engine, expire_on_commit=False)() as s:
        yield s


@pytest_asyncio.fixture
async def app(app_engine: AsyncEngine) -> AsyncIterator[FastAPI]:
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
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID | None,
    capability: str,
    scope: str,
) -> None:
    kind = RoleKind.system if tenant_id is None else RoleKind.tenant
    role_repo = SqlAlchemyRoleRepository(db)
    role = await role_repo.add(
        Role(id=uuid.uuid4(), name=f"role-{uuid.uuid4()}", kind=kind, tenant_id=tenant_id)
    )
    existing_capability_id = (
        await db.execute(
            text("SELECT id FROM capability WHERE name = :name AND scope = :scope"),
            {"name": capability, "scope": scope},
        )
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
    db: AsyncSession, *, tenant: Tenant, capabilities: list[str], scope: str = "tenant"
) -> tuple[User, str]:
    agent = await _make_user(db)
    await _add_membership(db, user_id=agent.id, tenant_id=tenant.id)
    for capability in capabilities:
        await _grant_capability(
            db,
            user_id=agent.id,
            tenant_id=None if scope == "global" else tenant.id,
            capability=capability,
            scope=scope,
        )
    token = _access_token(agent.id, tenant.id)
    return agent, token


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _seed_ticket(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    status: TicketStatus = TicketStatus.new,
    sla_due: datetime | None = None,
) -> Ticket:
    return await SqlAlchemyTicketRepository(db).add(
        Ticket(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            subject="s",
            status=status,
            priority=TicketPriority.normal,
            sla_due=sla_due,
        )
    )


async def _seed_agent_run(
    db: AsyncSession, *, tenant_id: uuid.UUID, ticket_id: uuid.UUID, confidence: float | None
) -> AgentRun:
    return await SqlAlchemyAgentRunRepository(db).add(
        AgentRun(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            ticket_id=ticket_id,
            langgraph_thread_id=f"ticket_{ticket_id}_run_1",
            run_seq=1,
            status=AgentRunStatus.succeeded,
            confidence=confidence,
        )
    )


async def _seed_approval_task(
    db: AsyncSession, *, tenant_id: uuid.UUID, ticket_id: uuid.UUID, agent_run_id: uuid.UUID
) -> ApprovalTask:
    return await SqlAlchemyApprovalRepository(db).add(
        ApprovalTask(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            ticket_id=ticket_id,
            agent_run_id=agent_run_id,
            status=ApprovalStatus.pending,
            draft_body="d",
        )
    )


async def test_summary_with_real_data_aggregates_correctly(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    now = datetime.now(UTC)
    ticket_new = await _seed_ticket(db, tenant.id, status=TicketStatus.new)
    ticket_overdue = await _seed_ticket(
        db, tenant.id, status=TicketStatus.open, sla_due=now - timedelta(hours=1)
    )
    await db.commit()
    run = await _seed_agent_run(db, tenant_id=tenant.id, ticket_id=ticket_new.id, confidence=0.9)
    await db.commit()
    await _seed_approval_task(
        db, tenant_id=tenant.id, ticket_id=ticket_overdue.id, agent_run_id=run.id
    )
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["analytics.read"]
    )

    async with _client(app) as c:
        r = await c.get("/api/v1/analytics/summary", headers=_auth_header(token))

    assert r.status_code == 200
    body = r.json()
    assert body["tickets_by_status"]["new"] == 1
    assert body["tickets_by_status"]["open"] == 1
    assert body["approvals_pending"] == 1
    assert body["avg_confidence"] == 0.9
    assert body["sla_breaches"] == 1


async def test_summary_with_no_data_returns_all_zeros_and_null_confidence(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["analytics.read"]
    )

    async with _client(app) as c:
        r = await c.get("/api/v1/analytics/summary", headers=_auth_header(token))

    assert r.status_code == 200
    body = r.json()
    assert body["tickets_by_status"] == {
        "new": 0,
        "open": 0,
        "pending": 0,
        "resolved": 0,
        "closed": 0,
        "reopened": 0,
    }
    assert body["approvals_pending"] == 0
    assert body["avg_confidence"] is None
    assert body["sla_breaches"] == 0


async def test_a_tenant_scoped_subject_only_sees_its_own_tenant(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant_a = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    tenant_b = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    await _seed_ticket(db, tenant_a.id, status=TicketStatus.new)
    await _seed_ticket(db, tenant_b.id, status=TicketStatus.new)
    await _seed_ticket(db, tenant_b.id, status=TicketStatus.new)
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant_a, capabilities=["analytics.read"]
    )

    async with _client(app) as c:
        r = await c.get("/api/v1/analytics/summary", headers=_auth_header(token))

    assert r.status_code == 200
    assert r.json()["tickets_by_status"]["new"] == 1


async def test_a_global_scoped_subject_aggregates_cross_tenant(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant_a = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    tenant_b = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    await _seed_ticket(db, tenant_a.id, status=TicketStatus.new)
    await _seed_ticket(db, tenant_b.id, status=TicketStatus.new)
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant_a, capabilities=["analytics.read"], scope="global"
    )

    async with _client(app) as c:
        r = await c.get("/api/v1/analytics/summary", headers=_auth_header(token))

    assert r.status_code == 200
    assert r.json()["tickets_by_status"]["new"] == 2


async def test_tickets_by_status_always_has_the_six_keys(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    await _seed_ticket(db, tenant.id, status=TicketStatus.new)
    await _seed_ticket(db, tenant.id, status=TicketStatus.resolved)
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["analytics.read"]
    )

    async with _client(app) as c:
        r = await c.get("/api/v1/analytics/summary", headers=_auth_header(token))

    assert r.status_code == 200
    assert set(r.json()["tickets_by_status"].keys()) == {
        "new",
        "open",
        "pending",
        "resolved",
        "closed",
        "reopened",
    }


async def test_a_resolved_ticket_with_overdue_sla_does_not_count_as_a_breach(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    await _seed_ticket(
        db,
        tenant.id,
        status=TicketStatus.resolved,
        sla_due=datetime.now(UTC) - timedelta(hours=1),
    )
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["analytics.read"]
    )

    async with _client(app) as c:
        r = await c.get("/api/v1/analytics/summary", headers=_auth_header(token))

    assert r.status_code == 200
    assert r.json()["sla_breaches"] == 0


async def test_a_subject_without_the_capability_cannot_read_the_summary(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    _agent, token = await _agent_with_capabilities(db, tenant=tenant, capabilities=["ticket.read"])

    async with _client(app) as c:
        r = await c.get("/api/v1/analytics/summary", headers=_auth_header(token))

    assert r.status_code == 403
