"""Tests de integración del router `agent` (tarea `backend-routers-flujo-ia-01`).

`app` apunta a `app_engine` (rol `syntax_app`, RLS real) — mismo patrón que `test_router_tickets.py`.
1:1 con el `## Scenarios (Gherkin)` de la tarea (CU-BE-06 ampliado con los escenarios de disparo).
"""

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
import pytest_asyncio
from app.agents.nodes.grade import Grade
from app.core.config import Settings, get_settings
from app.core.deps import AGENT_TOP_K, get_chat_model_port, get_db_session, get_retriever_port
from app.core.security import JWT_ALGORITHM, create_access_token, hash_password
from app.domain.entities.business import AgentRun, Ticket
from app.domain.entities.enums import (
    AgentRunStatus,
    KbDomain,
    KbEstado,
    Package,
    RoleKind,
    TenantStatus,
    TicketPriority,
    TicketStatus,
    UserStatus,
)
from app.domain.entities.identity import Role, Tenant, User, UserTenantMembership
from app.domain.ports.vector import Hit
from app.domain.services.classification import Classification
from app.infra.db.repositories import (
    SqlAlchemyAgentRunRepository,
    SqlAlchemyMessageRepository,
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


def _settings(*, rate_limit: int = 10) -> Settings:
    return Settings(
        _env_file=None,
        jwt_secret=_JWT_SECRET,
        app_env="production",
        cors_origins=[],
        ai_draft_rate_limit_per_minute=rate_limit,
    )


_TRUNCATE_TABLES = (
    "TRUNCATE agent_run, ticket, audit_log, user_tenant, refresh_session, auth_token, user_role, "
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


def _make_app(app_engine: AsyncEngine, *, rate_limit: int = 10) -> FastAPI:
    test_app = create_app(_settings(rate_limit=rate_limit))

    async def _override_session() -> AsyncIterator[AsyncSession]:
        async with async_sessionmaker(app_engine, expire_on_commit=False)() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    test_app.dependency_overrides[get_db_session] = _override_session
    test_app.dependency_overrides[get_settings] = lambda: _settings(rate_limit=rate_limit)
    test_app.dependency_overrides[get_chat_model_port] = lambda: _FakeChatModel()
    test_app.dependency_overrides[get_retriever_port] = lambda: _FakeRetriever()
    return test_app


@pytest_asyncio.fixture(autouse=True)
async def _checkpointer_pool(
    app_db_url: str, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[None]:
    """`app.agents.checkpointer.get_checkpointer()` lee `get_settings()` GLOBAL (no vía FastAPI DI,
    así que `test_app.dependency_overrides[get_settings]` no lo alcanza) — mismo reset que
    `test_runner.py`/`test_checkpointer.py`, necesario porque `LangGraphAgentRunner` ahora compila el
    grafo con el checkpointer real en cada `trigger`/`resume`."""
    monkeypatch.setenv("DATABASE_URL", app_db_url)
    get_settings.cache_clear()

    import app.agents.checkpointer as checkpointer_module

    checkpointer_module._pool = None
    yield
    if checkpointer_module._pool is not None:
        await checkpointer_module._pool.close()
    checkpointer_module._pool = None
    get_settings.cache_clear()


class _FakeChatModel:
    """`ChatModel` de prueba: clasifica siempre resoluble + dominio conocido, contexto suficiente,
    devuelve un draft fijo — reproducible sin red, sin `OPENAI_API_KEY`."""

    async def classify(self, text: str, schema: type) -> Classification:
        return Classification(
            categoria="incidencia",
            dominio=KbDomain.media_and_dam,
            prioridad=TicketPriority.normal,
            resoluble=True,
        )

    async def grade(self, prompt: str, schema: type) -> Grade:
        return Grade(suficiente=True, motivo="contexto suficiente para responder")

    async def generate(self, prompt: str) -> str:
        return "aquí tienes la respuesta al ticket"


class _FakeRetriever:
    async def retrieve(
        self,
        query: str,
        *,
        top_k: int,
        domain: KbDomain | None = None,
        package: Package | None = None,
        estado: KbEstado | None = None,
    ) -> list[RankedHit]:
        hit = Hit(
            uc_id="CU-BE-05",
            chunk_id=uuid.uuid4(),
            section_type="comportamiento",
            title="Título",
            source_url="packages/x/docs/aiup/use-cases/CU-BE-05.md",
            domain=KbDomain.media_and_dam,
            estado=KbEstado.draft,
            score=0.9,
            content="contenido de referencia",
        )
        return [RankedHit(hit=hit, weighted_score=0.9)]


class _SpyRetriever(_FakeRetriever):
    """Además de devolver hits fijos, guarda el `top_k` con el que `trigger()` de verdad la llama —
    para verificar que `deps.AGENT_TOP_K` llega intacto a través de `_get_agent_runner`/`build_graph`."""

    def __init__(self) -> None:
        self.captured_top_k: int | None = None

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int,
        domain: KbDomain | None = None,
        package: Package | None = None,
        estado: KbEstado | None = None,
    ) -> list[RankedHit]:
        self.captured_top_k = top_k
        return await super().retrieve(
            query, top_k=top_k, domain=domain, package=package, estado=estado
        )


@pytest_asyncio.fixture
async def app(app_engine: AsyncEngine) -> AsyncIterator[FastAPI]:
    test_app = _make_app(app_engine)
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


async def _grant_global_capability(
    db: AsyncSession, *, user_id: uuid.UUID, capability: str
) -> None:
    """Asignación GLOBAL de verdad (`RoleKind.system`, `tenant_id=None`) — para `approval.decide`
    (`rbac.md` §3: capacidad exclusivamente `global`, mismo patrón que `test_router_approvals.py`)."""
    role_repo = SqlAlchemyRoleRepository(db)
    role = await role_repo.add(
        Role(id=uuid.uuid4(), name=f"role-{uuid.uuid4()}", kind=RoleKind.system, tenant_id=None)
    )
    existing_capability_id = (
        await db.execute(
            text("SELECT id FROM capability WHERE name = :name AND scope = 'global'"),
            {"name": capability},
        )
    ).scalar_one_or_none()
    if existing_capability_id is None:
        capability_id = uuid.uuid4()
        await db.execute(
            text("INSERT INTO capability (id, name, scope) VALUES (:id, :name, 'global')"),
            {"id": capability_id, "name": capability},
        )
    else:
        capability_id = existing_capability_id
    await db.execute(
        text("INSERT INTO role_capability (role_id, capability_id) VALUES (:r, :c)"),
        {"r": role.id, "c": capability_id},
    )
    await role_repo.assign(user_id, role.id, None)
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


def _make_ticket_entity(tenant_id: uuid.UUID, *, status: TicketStatus = TicketStatus.new) -> Ticket:
    return Ticket(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        subject="s",
        status=status,
        priority=TicketPriority.normal,
    )


def _make_agent_run_entity(
    *, tenant_id: uuid.UUID, ticket_id: uuid.UUID, run_seq: int = 1, status: AgentRunStatus
) -> AgentRun:
    return AgentRun(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        ticket_id=ticket_id,
        langgraph_thread_id=f"ticket_{ticket_id}_run_{run_seq}",
        run_seq=run_seq,
        status=status,
    )


# ── POST /tickets/{id}/ai-draft: camino feliz ──


async def test_triggering_a_draft_creates_a_pending_agent_run(
    app: FastAPI, db: AsyncSession
) -> None:
    """El tenant por defecto tiene `auto_approve=false` (`_make_tenant`) y el `_FakeChatModel`
    produce un contexto suficiente/resoluble → el run real llega a `interrupt()` y queda `running`
    (pendiente de aprobación), NUNCA `queued` (el grafo real no deja el run parado ahí)."""
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["agent.trigger"]
    )

    async with _client(app) as c:
        r = await c.post(f"/api/v1/tickets/{ticket.id}/ai-draft", headers=_auth_header(token))

    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "running"
    assert body["ticket_id"] == str(ticket.id)
    persisted = await SqlAlchemyAgentRunRepository(db).get(uuid.UUID(body["id"]))
    assert persisted is not None
    assert persisted.langgraph_thread_id == f"ticket_{ticket.id}_run_1"
    assert persisted.escalated is True


# ── POST /tickets/{id}/ai-draft: 409 run activo ──


async def test_triggering_twice_before_the_first_finishes_is_a_conflict(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["agent.trigger"]
    )

    async with _client(app) as c:
        first = await c.post(f"/api/v1/tickets/{ticket.id}/ai-draft", headers=_auth_header(token))
        second = await c.post(f"/api/v1/tickets/{ticket.id}/ai-draft", headers=_auth_header(token))

    assert first.status_code == 202
    assert second.status_code == 409
    assert second.headers["content-type"].startswith("application/problem+json")


async def test_reopening_a_ticket_with_a_non_terminal_previous_run_still_blocks_a_new_trigger(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(
        _make_ticket_entity(tenant.id, status=TicketStatus.reopened)
    )
    await SqlAlchemyAgentRunRepository(db).add(
        _make_agent_run_entity(
            tenant_id=tenant.id, ticket_id=ticket.id, status=AgentRunStatus.queued
        )
    )
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["agent.trigger"]
    )

    async with _client(app) as c:
        r = await c.post(f"/api/v1/tickets/{ticket.id}/ai-draft", headers=_auth_header(token))

    assert r.status_code == 409


async def test_two_concurrent_triggers_at_most_one_succeeds(app: FastAPI, db: AsyncSession) -> None:
    """CAS real bajo concurrencia: nunca dos 202 para el mismo ticket."""
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["agent.trigger"]
    )

    async with _client(app) as c:
        results = await asyncio.gather(
            c.post(f"/api/v1/tickets/{ticket.id}/ai-draft", headers=_auth_header(token)),
            c.post(f"/api/v1/tickets/{ticket.id}/ai-draft", headers=_auth_header(token)),
        )

    statuses = sorted(r.status_code for r in results)
    assert statuses == [202, 409]


# ── POST /tickets/{id}/ai-draft: 429 rate limit ──


async def test_exceeding_the_rate_limit_returns_429(
    app_engine: AsyncEngine, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket_1 = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    ticket_2 = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["agent.trigger"]
    )
    limited_app = _make_app(app_engine, rate_limit=1)

    async with _client(limited_app) as c:
        first = await c.post(f"/api/v1/tickets/{ticket_1.id}/ai-draft", headers=_auth_header(token))
        second = await c.post(
            f"/api/v1/tickets/{ticket_2.id}/ai-draft", headers=_auth_header(token)
        )

    assert first.status_code == 202
    assert second.status_code == 429
    assert second.headers["content-type"].startswith("application/problem+json")
    limited_app.dependency_overrides.clear()


async def test_the_nth_trigger_exactly_at_the_limit_is_accepted(
    app_engine: AsyncEngine, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket_1 = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    ticket_2 = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["agent.trigger"]
    )
    limited_app = _make_app(app_engine, rate_limit=2)

    async with _client(limited_app) as c:
        first = await c.post(f"/api/v1/tickets/{ticket_1.id}/ai-draft", headers=_auth_header(token))
        second = await c.post(
            f"/api/v1/tickets/{ticket_2.id}/ai-draft", headers=_auth_header(token)
        )

    assert first.status_code == 202
    assert second.status_code == 202
    limited_app.dependency_overrides.clear()


async def test_one_tenants_rate_limit_does_not_affect_another(
    app_engine: AsyncEngine, db: AsyncSession
) -> None:
    tenant_a = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    tenant_b = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket_a1 = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant_a.id))
    ticket_a2 = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant_a.id))
    ticket_b = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant_b.id))
    await db.commit()
    _agent_a, token_a = await _agent_with_capabilities(
        db, tenant=tenant_a, capabilities=["agent.trigger"]
    )
    _agent_b, token_b = await _agent_with_capabilities(
        db, tenant=tenant_b, capabilities=["agent.trigger"]
    )
    limited_app = _make_app(app_engine, rate_limit=1)

    async with _client(limited_app) as c:
        await c.post(f"/api/v1/tickets/{ticket_a1.id}/ai-draft", headers=_auth_header(token_a))
        exhausted_a = await c.post(
            f"/api/v1/tickets/{ticket_a2.id}/ai-draft", headers=_auth_header(token_a)
        )
        tenant_b_first = await c.post(
            f"/api/v1/tickets/{ticket_b.id}/ai-draft", headers=_auth_header(token_b)
        )

    assert exhausted_a.status_code == 429
    assert tenant_b_first.status_code == 202
    limited_app.dependency_overrides.clear()


# ── POST /tickets/{id}/ai-draft: 404 ──


async def test_triggering_on_a_nonexistent_ticket_returns_404(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["agent.trigger"]
    )

    async with _client(app) as c:
        r = await c.post(f"/api/v1/tickets/{uuid.uuid4()}/ai-draft", headers=_auth_header(token))

    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")


async def test_triggering_on_a_ticket_of_another_tenant_returns_404(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant_a = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    tenant_b = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket_b = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant_b.id))
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant_a, capabilities=["agent.trigger"]
    )

    async with _client(app) as c:
        r = await c.post(f"/api/v1/tickets/{ticket_b.id}/ai-draft", headers=_auth_header(token))

    assert r.status_code == 404


# ── POST /tickets/{id}/ai-draft: 403 ──


async def test_triggering_without_agent_trigger_capability_returns_403(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    await db.commit()
    _agent, token = await _agent_with_capabilities(db, tenant=tenant, capabilities=["ticket.read"])

    async with _client(app) as c:
        r = await c.post(f"/api/v1/tickets/{ticket.id}/ai-draft", headers=_auth_header(token))

    assert r.status_code == 403


# ── GET /agent-runs/{id} ──


async def test_reading_an_existing_run_returns_its_state(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    await db.commit()
    run = await SqlAlchemyAgentRunRepository(db).add(
        _make_agent_run_entity(
            tenant_id=tenant.id, ticket_id=ticket.id, status=AgentRunStatus.queued
        )
    )
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["agent.trigger"]
    )

    async with _client(app) as c:
        r = await c.get(f"/api/v1/agent-runs/{run.id}", headers=_auth_header(token))

    assert r.status_code == 200
    body = r.json()
    assert body["id"] == str(run.id)
    assert body["status"] == "queued"
    assert body["confidence"] is None
    assert body["sources"] == []
    assert body["error"] is None


async def test_a_run_of_another_tenant_is_invisible(app: FastAPI, db: AsyncSession) -> None:
    tenant_a = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    tenant_b = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket_b = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant_b.id))
    await db.commit()
    run_b = await SqlAlchemyAgentRunRepository(db).add(
        _make_agent_run_entity(
            tenant_id=tenant_b.id, ticket_id=ticket_b.id, status=AgentRunStatus.queued
        )
    )
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant_a, capabilities=["agent.trigger"]
    )

    async with _client(app) as c:
        r = await c.get(f"/api/v1/agent-runs/{run_b.id}", headers=_auth_header(token))

    assert r.status_code == 404


async def test_a_read_only_role_can_read_the_run_without_triggering(
    app: FastAPI, db: AsyncSession
) -> None:
    """agent.trigger OR ticket.read: basta con ticket.read para leer el estado del run."""
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    await db.commit()
    run = await SqlAlchemyAgentRunRepository(db).add(
        _make_agent_run_entity(
            tenant_id=tenant.id, ticket_id=ticket.id, status=AgentRunStatus.queued
        )
    )
    await db.commit()
    _agent, token = await _agent_with_capabilities(db, tenant=tenant, capabilities=["ticket.read"])

    async with _client(app) as c:
        r = await c.get(f"/api/v1/agent-runs/{run.id}", headers=_auth_header(token))

    assert r.status_code == 200


async def test_reading_without_agent_trigger_nor_ticket_read_returns_403(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    await db.commit()
    run = await SqlAlchemyAgentRunRepository(db).add(
        _make_agent_run_entity(
            tenant_id=tenant.id, ticket_id=ticket.id, status=AgentRunStatus.queued
        )
    )
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.create"]
    )

    async with _client(app) as c:
        r = await c.get(f"/api/v1/agent-runs/{run.id}", headers=_auth_header(token))

    assert r.status_code == 403


async def test_reading_a_nonexistent_run_returns_404(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["agent.trigger"]
    )

    async with _client(app) as c:
        r = await c.get(f"/api/v1/agent-runs/{uuid.uuid4()}", headers=_auth_header(token))

    assert r.status_code == 404


# ── e2e: trigger → approve produce un Message(public) real (tarea backend-agent-graph-10) ──


async def test_trigger_then_approve_publishes_a_real_public_message(
    app: FastAPI, db: AsyncSession
) -> None:
    """Contrato HTTP completo contra el `LangGraphAgentRunner` real (no `StubAgentRunner`): disparar
    y aprobar produce un `Message(public)` real, y `GET /agent-runs/{id}` refleja `succeeded`."""
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    # `open`, no `new`: `approval_service.decide()` transiciona el ticket a `pending` al aprobar, y
    # `new → pending` no es una transición válida (solo `open → pending`, `ticket_service.py`).
    ticket = await SqlAlchemyTicketRepository(db).add(
        _make_ticket_entity(tenant.id, status=TicketStatus.open)
    )
    await db.commit()
    agent, token = await _agent_with_capabilities(db, tenant=tenant, capabilities=["agent.trigger"])
    await _grant_global_capability(db, user_id=agent.id, capability="approval.decide")

    async with _client(app) as c:
        triggered = await c.post(
            f"/api/v1/tickets/{ticket.id}/ai-draft", headers=_auth_header(token)
        )
        assert triggered.status_code == 202
        run_id = triggered.json()["id"]

        approvals_page = await c.get("/api/v1/approvals", headers=_auth_header(token))
        assert approvals_page.status_code == 200
        [task] = [t for t in approvals_page.json()["items"] if t["agent_run_id"] == run_id]

        approved = await c.post(
            f"/api/v1/approvals/{task['id']}/approve", headers=_auth_header(token)
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == "approved"

        run_after = await c.get(f"/api/v1/agent-runs/{run_id}", headers=_auth_header(token))

    assert run_after.status_code == 200
    assert run_after.json()["status"] == "succeeded"
    messages = await SqlAlchemyMessageRepository(db).list_by_ticket(ticket.id)
    published = [m for m in messages.items if m.is_ai_draft]
    assert len(published) == 1
    assert "aquí tienes la respuesta" in published[0].body


async def test_a_misconfigured_llm_provider_fails_controlled_not_a_hang(
    app_engine: AsyncEngine, db: AsyncSession
) -> None:
    """Un `settings.llm_provider` no soportado se detecta al resolver la dependencia (ANTES del
    handler), no enterrado en la ejecución del grafo — `PortError` explícito, no un 500 opaco."""
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["agent.trigger"]
    )
    broken_app = create_app(_settings())

    async def _override_session() -> AsyncIterator[AsyncSession]:
        async with async_sessionmaker(app_engine, expire_on_commit=False)() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    broken_app.dependency_overrides[get_db_session] = _override_session
    broken_app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        jwt_secret=_JWT_SECRET,
        app_env="production",
        cors_origins=[],
        llm_provider="unsupported-provider",
    )

    async with _client(broken_app) as c:
        r = await c.post(f"/api/v1/tickets/{ticket.id}/ai-draft", headers=_auth_header(token))

    assert r.status_code >= 500
    broken_app.dependency_overrides.clear()


async def test_trigger_uses_the_configured_agent_top_k(
    app_engine: AsyncEngine, db: AsyncSession
) -> None:
    """`deps.AGENT_TOP_K` llega intacto al `Retriever` real a través de `_get_agent_runner` — sin
    esto, un cambio silencioso en el wiring podría desalinear `top_k` sin que nada lo note."""
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["agent.trigger"]
    )
    spy_app = _make_app(app_engine)
    spy_retriever = _SpyRetriever()
    spy_app.dependency_overrides[get_retriever_port] = lambda: spy_retriever

    async with _client(spy_app) as c:
        r = await c.post(f"/api/v1/tickets/{ticket.id}/ai-draft", headers=_auth_header(token))

    assert r.status_code == 202
    assert AGENT_TOP_K == 8, "actualiza este literal si cambia deps.AGENT_TOP_K"
    assert spy_retriever.captured_top_k == 8
    spy_app.dependency_overrides.clear()


# ── GET /tickets/{id}/agent-runs/active — descubrir el run activo (gap ai_auto_draft) ──


async def test_no_active_run_returns_null_not_404(app: FastAPI, db: AsyncSession) -> None:
    """Sin ningún `agent.trigger` disparado todavía, "sin run activo" es un resultado legítimo — 200
    con cuerpo `null`, nunca 404 (no es "el recurso no existe", es "no hay ninguno todavía")."""
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    await db.commit()
    _agent, token = await _agent_with_capabilities(db, tenant=tenant, capabilities=["ticket.read"])

    async with _client(app) as c:
        r = await c.get(
            f"/api/v1/tickets/{ticket.id}/agent-runs/active", headers=_auth_header(token)
        )

    assert r.status_code == 200
    assert r.json() is None


async def test_discovers_the_run_created_by_someone_else(app: FastAPI, db: AsyncSession) -> None:
    """Escenario `ai_auto_draft`: el servidor dispara el run SIN que este cliente lo pida — un
    segundo request (mismo ticket, capacidad `ticket.read` basta) lo descubre igual."""
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    await db.commit()
    _trigger_agent, trigger_token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["agent.trigger"]
    )
    _viewer_agent, viewer_token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.read"]
    )

    async with _client(app) as c:
        triggered = await c.post(
            f"/api/v1/tickets/{ticket.id}/ai-draft", headers=_auth_header(trigger_token)
        )
        discovered = await c.get(
            f"/api/v1/tickets/{ticket.id}/agent-runs/active", headers=_auth_header(viewer_token)
        )

    assert triggered.status_code == 202
    assert discovered.status_code == 200
    body = discovered.json()
    assert body is not None
    assert body["id"] == triggered.json()["id"]
    assert body["status"] == "running"


async def test_a_terminal_run_is_no_longer_the_active_one(app: FastAPI, db: AsyncSession) -> None:
    """Un run ya `succeeded`/`failed` no es "activo" — tras publicarse (auto_approve) el endpoint
    vuelve a `null`, no se queda pegado al último run terminado."""
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    tenant.auto_approve = True
    tenant = await SqlAlchemyTenantRepository(db).update(tenant)
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["agent.trigger", "ticket.read"]
    )

    async with _client(app) as c:
        triggered = await c.post(
            f"/api/v1/tickets/{ticket.id}/ai-draft", headers=_auth_header(token)
        )
        after = await c.get(
            f"/api/v1/tickets/{ticket.id}/agent-runs/active", headers=_auth_header(token)
        )

    assert triggered.json()["status"] == "succeeded"  # auto_approve=True + _FakeChatModel confiado
    assert after.status_code == 200
    assert after.json() is None


async def test_active_agent_run_requires_ticket_read_or_agent_trigger(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    await db.commit()
    _agent, token = await _agent_with_capabilities(db, tenant=tenant, capabilities=["kb.read"])

    async with _client(app) as c:
        r = await c.get(
            f"/api/v1/tickets/{ticket.id}/agent-runs/active", headers=_auth_header(token)
        )

    assert r.status_code == 403
