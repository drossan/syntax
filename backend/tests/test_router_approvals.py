"""Tests de integración del router `approvals` (tarea `backend-routers-flujo-ia-02`).

`app` apunta a `app_engine` (rol `syntax_app`, RLS real) — mismo patrón que `test_router_agent.py`.
1:1 con el `## Scenarios (Gherkin)` de la tarea.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

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
    """Sesión de SIEMBRA (superuser, RLS no aplica)."""
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
    """Siembra rol+capability+asignación (mismo patrón que `test_router_admin.py`). `tenant_id=None`
    es una asignación GLOBAL de verdad (`RoleKind.system`, `role_repo.assign(..., None)`) — no basta con
    que la capacidad tenga `scope='global'` en su propia columna si la asignación del rol sigue atada a
    un tenant concreto."""
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


async def _seed_task(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    status: ApprovalStatus = ApprovalStatus.pending,
    sla_due: datetime | None = None,
) -> ApprovalTask:
    ticket = await SqlAlchemyTicketRepository(db).add(
        Ticket(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            subject="s",
            status=TicketStatus.open,
            priority=TicketPriority.normal,
            sla_due=sla_due,
        )
    )
    run = await SqlAlchemyAgentRunRepository(db).add(
        AgentRun(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            ticket_id=ticket.id,
            langgraph_thread_id=f"ticket_{ticket.id}_run_1",
            run_seq=1,
            status=AgentRunStatus.succeeded,
        )
    )
    return await SqlAlchemyApprovalRepository(db).add(
        ApprovalTask(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            ticket_id=ticket.id,
            agent_run_id=run.id,
            status=status,
            draft_body="draft",
        )
    )


# ── GET /approvals ──


async def test_listing_without_a_status_filter_returns_only_pending(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    pending = await _seed_task(db, tenant_id=tenant.id, status=ApprovalStatus.pending)
    await _seed_task(db, tenant_id=tenant.id, status=ApprovalStatus.rejected)
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["approval.decide"], scope="global"
    )

    async with _client(app) as c:
        r = await c.get("/api/v1/approvals", headers=_auth_header(token))

    assert r.status_code == 200
    body = r.json()
    assert [item["id"] for item in body["items"]] == [str(pending.id)]


async def test_filtering_by_status_returns_only_that_status(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    await _seed_task(db, tenant_id=tenant.id, status=ApprovalStatus.pending)
    rejected = await _seed_task(db, tenant_id=tenant.id, status=ApprovalStatus.rejected)
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["approval.decide"], scope="global"
    )

    async with _client(app) as c:
        r = await c.get(
            "/api/v1/approvals", params={"status": "rejected"}, headers=_auth_header(token)
        )

    assert r.status_code == 200
    body = r.json()
    assert [item["id"] for item in body["items"]] == [str(rejected.id)]


async def test_an_unsupported_sort_is_rejected(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["approval.decide"], scope="global"
    )

    async with _client(app) as c:
        r = await c.get(
            "/api/v1/approvals", params={"sort": "confidence"}, headers=_auth_header(token)
        )

    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")


async def test_a_tenant_scoped_subject_only_sees_its_own_tenant_queue(
    app: FastAPI, db: AsyncSession
) -> None:
    """Grant tenant-scoped (invariante de RBAC lo impide en producción, aquí se ejercita el
    comportamiento genérico del puerto/servicio directamente)."""
    tenant_a = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    tenant_b = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    task_a = await _seed_task(db, tenant_id=tenant_a.id)
    await _seed_task(db, tenant_id=tenant_b.id)
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant_a, capabilities=["approval.decide"], scope="tenant"
    )

    async with _client(app) as c:
        r = await c.get("/api/v1/approvals", headers=_auth_header(token))

    assert r.status_code == 200
    body = r.json()
    assert [item["id"] for item in body["items"]] == [str(task_a.id)]


async def test_a_global_scoped_subject_sees_every_tenants_queue(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant_a = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    tenant_b = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    task_a = await _seed_task(db, tenant_id=tenant_a.id)
    task_b = await _seed_task(db, tenant_id=tenant_b.id)
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant_a, capabilities=["approval.decide"], scope="global"
    )

    async with _client(app) as c:
        r = await c.get("/api/v1/approvals", headers=_auth_header(token))

    assert r.status_code == 200
    body = r.json()
    assert {item["id"] for item in body["items"]} == {str(task_a.id), str(task_b.id)}


async def test_a_subject_without_the_capability_cannot_list_the_queue(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    _agent, token = await _agent_with_capabilities(db, tenant=tenant, capabilities=["ticket.read"])

    async with _client(app) as c:
        r = await c.get("/api/v1/approvals", headers=_auth_header(token))

    assert r.status_code == 403


# ── POST /approvals/{id}/approve|edit|reject ──


async def test_approving_a_pending_task_returns_200_with_approved_status(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    task = await _seed_task(db, tenant_id=tenant.id)
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["approval.decide"], scope="global"
    )

    async with _client(app) as c:
        r = await c.post(f"/api/v1/approvals/{task.id}/approve", headers=_auth_header(token))

    assert r.status_code == 200
    assert r.json()["status"] == "approved"


async def test_editing_without_final_body_is_rejected(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    task = await _seed_task(db, tenant_id=tenant.id)
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["approval.decide"], scope="global"
    )

    async with _client(app) as c:
        r = await c.post(f"/api/v1/approvals/{task.id}/edit", json={}, headers=_auth_header(token))

    assert r.status_code == 422


async def test_editing_with_final_body_persists_it(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    task = await _seed_task(db, tenant_id=tenant.id)
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["approval.decide"], scope="global"
    )

    async with _client(app) as c:
        r = await c.post(
            f"/api/v1/approvals/{task.id}/edit",
            json={"final_body": "texto corregido"},
            headers=_auth_header(token),
        )

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "edited"
    assert body["final_body"] == "texto corregido"


async def test_rejecting_without_human_note_is_rejected(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    task = await _seed_task(db, tenant_id=tenant.id)
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["approval.decide"], scope="global"
    )

    async with _client(app) as c:
        r = await c.post(
            f"/api/v1/approvals/{task.id}/reject", json={}, headers=_auth_header(token)
        )

    assert r.status_code == 422


async def test_rejecting_with_human_note_returns_200_without_public_message(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    task = await _seed_task(db, tenant_id=tenant.id)
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["approval.decide"], scope="global"
    )

    async with _client(app) as c:
        r = await c.post(
            f"/api/v1/approvals/{task.id}/reject",
            json={"human_note": "no aplica"},
            headers=_auth_header(token),
        )

    assert r.status_code == 200
    assert r.json()["status"] == "rejected"


async def test_deciding_the_same_task_twice_is_a_conflict(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    task = await _seed_task(db, tenant_id=tenant.id)
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["approval.decide"], scope="global"
    )

    async with _client(app) as c:
        first = await c.post(f"/api/v1/approvals/{task.id}/approve", headers=_auth_header(token))
        second = await c.post(f"/api/v1/approvals/{task.id}/approve", headers=_auth_header(token))

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.headers["content-type"].startswith("application/problem+json")


async def test_deciding_a_nonexistent_task_returns_404(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["approval.decide"], scope="global"
    )

    async with _client(app) as c:
        r = await c.post(f"/api/v1/approvals/{uuid.uuid4()}/approve", headers=_auth_header(token))

    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")


async def test_a_subject_without_the_capability_cannot_decide(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    task = await _seed_task(db, tenant_id=tenant.id)
    await db.commit()
    _agent, token = await _agent_with_capabilities(db, tenant=tenant, capabilities=["ticket.read"])

    async with _client(app) as c:
        r = await c.post(f"/api/v1/approvals/{task.id}/approve", headers=_auth_header(token))

    assert r.status_code == 403
