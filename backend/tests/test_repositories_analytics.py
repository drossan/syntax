"""Tests de integración de `SqlAlchemyAnalyticsRepository` (tarea `backend-routers-flujo-ia-05`).

Postgres real vía `superuser_engine` (RLS no aplica). Primer y único adaptador de este puerto.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest_asyncio
from app.domain.entities.business import AgentRun, ApprovalTask, Ticket
from app.domain.entities.enums import (
    AgentRunStatus,
    ApprovalStatus,
    TenantStatus,
    TicketPriority,
    TicketStatus,
)
from app.domain.entities.identity import Tenant
from app.infra.db.repositories.agent_run import SqlAlchemyAgentRunRepository
from app.infra.db.repositories.analytics import SqlAlchemyAnalyticsRepository
from app.infra.db.repositories.approval import SqlAlchemyApprovalRepository
from app.infra.db.repositories.tenant import SqlAlchemyTenantRepository
from app.infra.db.repositories.ticket import SqlAlchemyTicketRepository
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

_TRUNCATE_TABLES = "TRUNCATE approval_task, agent_run, ticket, tenant RESTART IDENTITY CASCADE"


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables(superuser_engine: AsyncEngine) -> AsyncIterator[None]:
    async with superuser_engine.begin() as conn:
        await conn.execute(text(_TRUNCATE_TABLES))
    yield
    async with superuser_engine.begin() as conn:
        await conn.execute(text(_TRUNCATE_TABLES))


@pytest_asyncio.fixture
async def session(superuser_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with async_sessionmaker(superuser_engine, expire_on_commit=False)() as s:
        yield s


async def _make_tenant(session: AsyncSession) -> Tenant:
    return await SqlAlchemyTenantRepository(session).add(
        Tenant(id=uuid.uuid4(), slug=f"t-{uuid.uuid4()}", name="T", status=TenantStatus.active)
    )


async def _make_ticket(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    status: TicketStatus = TicketStatus.new,
    sla_due: datetime | None = None,
) -> Ticket:
    return await SqlAlchemyTicketRepository(session).add(
        Ticket(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            subject="s",
            status=status,
            priority=TicketPriority.normal,
            sla_due=sla_due,
        )
    )


async def _make_agent_run(
    session: AsyncSession, *, tenant_id: uuid.UUID, ticket_id: uuid.UUID, confidence: float | None
) -> AgentRun:
    return await SqlAlchemyAgentRunRepository(session).add(
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


async def _make_approval_task(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    ticket_id: uuid.UUID,
    agent_run_id: uuid.UUID,
    status: ApprovalStatus = ApprovalStatus.pending,
) -> ApprovalTask:
    return await SqlAlchemyApprovalRepository(session).add(
        ApprovalTask(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            ticket_id=ticket_id,
            agent_run_id=agent_run_id,
            status=status,
            draft_body="d",
        )
    )


async def test_summary_with_no_data_returns_all_zeros_and_null_confidence(
    session: AsyncSession,
) -> None:
    tenant = await _make_tenant(session)
    await session.commit()

    result = await SqlAlchemyAnalyticsRepository(session).summary(tenant.id)

    assert result.tickets_by_status == {
        "new": 0,
        "open": 0,
        "pending": 0,
        "resolved": 0,
        "closed": 0,
        "reopened": 0,
    }
    assert result.approvals_pending == 0
    assert result.avg_confidence is None
    assert result.sla_breaches == 0


async def test_tickets_by_status_always_has_the_six_keys_even_with_partial_data(
    session: AsyncSession,
) -> None:
    tenant = await _make_tenant(session)
    await session.commit()
    await _make_ticket(session, tenant.id, status=TicketStatus.new)
    await _make_ticket(session, tenant.id, status=TicketStatus.new)
    await _make_ticket(session, tenant.id, status=TicketStatus.open)
    await session.commit()

    result = await SqlAlchemyAnalyticsRepository(session).summary(tenant.id)

    assert result.tickets_by_status == {
        "new": 2,
        "open": 1,
        "pending": 0,
        "resolved": 0,
        "closed": 0,
        "reopened": 0,
    }


async def test_approvals_pending_only_counts_pending_status(session: AsyncSession) -> None:
    """2 `pending` + 1 `rejected` (no 1+1): distingue `==` de `!=`/`>` sobre el enum de status — con
    conteos iguales, un mutante que invierte la condición daría el mismo número por coincidencia."""
    tenant = await _make_tenant(session)
    await session.commit()
    ticket = await _make_ticket(session, tenant.id)
    await session.commit()
    run = await _make_agent_run(session, tenant_id=tenant.id, ticket_id=ticket.id, confidence=None)
    await session.commit()
    await _make_approval_task(
        session,
        tenant_id=tenant.id,
        ticket_id=ticket.id,
        agent_run_id=run.id,
        status=ApprovalStatus.pending,
    )
    await _make_approval_task(
        session,
        tenant_id=tenant.id,
        ticket_id=ticket.id,
        agent_run_id=run.id,
        status=ApprovalStatus.pending,
    )
    await _make_approval_task(
        session,
        tenant_id=tenant.id,
        ticket_id=ticket.id,
        agent_run_id=run.id,
        status=ApprovalStatus.rejected,
    )
    await session.commit()

    result = await SqlAlchemyAnalyticsRepository(session).summary(tenant.id)

    assert result.approvals_pending == 2


async def test_approvals_pending_isolates_by_tenant_not_range(session: AsyncSession) -> None:
    """IDs deterministas (bajo/medio/alto) para matar mutantes de comparación (`==`→`<=`/`>=`/
    `is not`) en el filtro `tenant_id` de `approval_scope`."""
    low = await SqlAlchemyTenantRepository(session).add(
        Tenant(id=uuid.UUID(int=10), slug="low", name="low", status=TenantStatus.active)
    )
    mid = await SqlAlchemyTenantRepository(session).add(
        Tenant(id=uuid.UUID(int=20), slug="mid", name="mid", status=TenantStatus.active)
    )
    high = await SqlAlchemyTenantRepository(session).add(
        Tenant(id=uuid.UUID(int=30), slug="high", name="high", status=TenantStatus.active)
    )
    await session.commit()
    for tenant in (low, mid, high):
        ticket = await _make_ticket(session, tenant.id)
        run = await _make_agent_run(
            session, tenant_id=tenant.id, ticket_id=ticket.id, confidence=None
        )
        await _make_approval_task(
            session, tenant_id=tenant.id, ticket_id=ticket.id, agent_run_id=run.id
        )
    await session.commit()

    result = await SqlAlchemyAnalyticsRepository(session).summary(mid.id)

    assert result.approvals_pending == 1


async def test_avg_confidence_isolates_by_tenant_not_range(session: AsyncSession) -> None:
    """IDs deterministas (bajo/medio/alto) para matar mutantes de comparación en el filtro
    `tenant_id` de `agent_run_scope` — sin esto, `avg_confidence` podría arrastrar runs de otro
    tenant si el operador se invirtiera silenciosamente."""
    low = await SqlAlchemyTenantRepository(session).add(
        Tenant(id=uuid.UUID(int=110), slug="low2", name="low2", status=TenantStatus.active)
    )
    mid = await SqlAlchemyTenantRepository(session).add(
        Tenant(id=uuid.UUID(int=120), slug="mid2", name="mid2", status=TenantStatus.active)
    )
    high = await SqlAlchemyTenantRepository(session).add(
        Tenant(id=uuid.UUID(int=130), slug="high2", name="high2", status=TenantStatus.active)
    )
    await session.commit()
    low_ticket = await _make_ticket(session, low.id)
    mid_ticket = await _make_ticket(session, mid.id)
    high_ticket = await _make_ticket(session, high.id)
    await _make_agent_run(session, tenant_id=low.id, ticket_id=low_ticket.id, confidence=0.1)
    await _make_agent_run(session, tenant_id=mid.id, ticket_id=mid_ticket.id, confidence=0.5)
    await _make_agent_run(session, tenant_id=high.id, ticket_id=high_ticket.id, confidence=0.9)
    await session.commit()

    result = await SqlAlchemyAnalyticsRepository(session).summary(mid.id)

    assert result.avg_confidence == 0.5


async def test_avg_confidence_ignores_null_confidence_runs(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    await session.commit()
    ticket = await _make_ticket(session, tenant.id)
    await session.commit()
    await _make_agent_run(session, tenant_id=tenant.id, ticket_id=ticket.id, confidence=0.8)
    await _make_agent_run(session, tenant_id=tenant.id, ticket_id=ticket.id, confidence=0.6)
    await _make_agent_run(session, tenant_id=tenant.id, ticket_id=ticket.id, confidence=None)
    await session.commit()

    result = await SqlAlchemyAnalyticsRepository(session).summary(tenant.id)

    assert result.avg_confidence is not None
    assert round(result.avg_confidence, 2) == 0.70


async def test_an_sla_due_exactly_at_now_does_not_count_as_a_breach(session: AsyncSession) -> None:
    """`sla_due < now()` es estricto: capturamos el `now()` de POSTGRES (no de Python) y lo usamos
    como `sla_due`, todo dentro de la MISMA transacción (sin `commit` intermedio) para que sea
    literalmente el mismo instante — `now()` es estable por transacción en Postgres, así que la
    comparación posterior ve el mismo valor exacto, nunca "estrictamente menor"."""
    tenant = await _make_tenant(session)
    await session.commit()
    pg_now = (await session.execute(text("SELECT now()"))).scalar_one()
    await _make_ticket(session, tenant.id, status=TicketStatus.open, sla_due=pg_now)

    result = await SqlAlchemyAnalyticsRepository(session).summary(tenant.id)

    assert result.sla_breaches == 0


async def test_sla_breaches_counts_overdue_open_tickets(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    await session.commit()
    now = datetime.now(UTC)
    await _make_ticket(
        session, tenant.id, status=TicketStatus.open, sla_due=now - timedelta(hours=1)
    )
    await session.commit()

    result = await SqlAlchemyAnalyticsRepository(session).summary(tenant.id)

    assert result.sla_breaches == 1


async def test_sla_breaches_excludes_null_sla_due(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    await session.commit()
    await _make_ticket(session, tenant.id, status=TicketStatus.open, sla_due=None)
    await session.commit()

    result = await SqlAlchemyAnalyticsRepository(session).summary(tenant.id)

    assert result.sla_breaches == 0


async def test_sla_breaches_excludes_future_sla_due(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    await session.commit()
    now = datetime.now(UTC)
    await _make_ticket(
        session, tenant.id, status=TicketStatus.open, sla_due=now + timedelta(hours=1)
    )
    await session.commit()

    result = await SqlAlchemyAnalyticsRepository(session).summary(tenant.id)

    assert result.sla_breaches == 0


async def test_sla_breaches_excludes_resolved_and_closed_tickets(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    await session.commit()
    now = datetime.now(UTC)
    await _make_ticket(
        session, tenant.id, status=TicketStatus.resolved, sla_due=now - timedelta(hours=1)
    )
    await _make_ticket(
        session, tenant.id, status=TicketStatus.closed, sla_due=now - timedelta(hours=1)
    )
    await session.commit()

    result = await SqlAlchemyAnalyticsRepository(session).summary(tenant.id)

    assert result.sla_breaches == 0


async def test_summary_with_tenant_id_isolates_by_tenant(session: AsyncSession) -> None:
    tenant_a = await _make_tenant(session)
    tenant_b = await _make_tenant(session)
    await session.commit()
    await _make_ticket(session, tenant_a.id, status=TicketStatus.new)
    await _make_ticket(session, tenant_b.id, status=TicketStatus.new)
    await _make_ticket(session, tenant_b.id, status=TicketStatus.new)
    await session.commit()

    result = await SqlAlchemyAnalyticsRepository(session).summary(tenant_a.id)

    assert result.tickets_by_status["new"] == 1


async def test_summary_with_tenant_id_none_aggregates_cross_tenant(session: AsyncSession) -> None:
    tenant_a = await _make_tenant(session)
    tenant_b = await _make_tenant(session)
    await session.commit()
    await _make_ticket(session, tenant_a.id, status=TicketStatus.new)
    await _make_ticket(session, tenant_b.id, status=TicketStatus.new)
    await session.commit()

    result = await SqlAlchemyAnalyticsRepository(session).summary(None)

    assert result.tickets_by_status["new"] == 2
