"""Tests de integración de `SqlAlchemyApprovalRepository` (tarea `backend-routers-flujo-ia-02`).

Postgres real vía `superuser_engine` (RLS no aplica). Primer adaptador de `ApprovalRepository` —
`decide_if_pending` (CAS) no tenía adaptador real hasta esta tarea. `list()` ordena por
`ticket.sla_due, agent_run.confidence` (JOIN — ninguna de las dos columnas vive en `approval_task`).
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
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
from app.domain.errors import NotFound
from app.infra.db.repositories.agent_run import SqlAlchemyAgentRunRepository
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
    session: AsyncSession, tenant_id: uuid.UUID, *, sla_due: datetime | None = None
) -> Ticket:
    return await SqlAlchemyTicketRepository(session).add(
        Ticket(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            subject="s",
            status=TicketStatus.new,
            priority=TicketPriority.normal,
            sla_due=sla_due,
        )
    )


async def _make_agent_run(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    ticket_id: uuid.UUID,
    confidence: float | None = None,
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


def _make_approval_task(
    *,
    tenant_id: uuid.UUID,
    ticket_id: uuid.UUID,
    agent_run_id: uuid.UUID,
    status: ApprovalStatus = ApprovalStatus.pending,
) -> ApprovalTask:
    return ApprovalTask(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        ticket_id=ticket_id,
        agent_run_id=agent_run_id,
        status=status,
        draft_body="draft",
    )


async def _seed_task(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    status: ApprovalStatus = ApprovalStatus.pending,
    sla_due: datetime | None = None,
    confidence: float | None = None,
) -> ApprovalTask:
    ticket = await _make_ticket(session, tenant_id, sla_due=sla_due)
    run = await _make_agent_run(
        session, tenant_id=tenant_id, ticket_id=ticket.id, confidence=confidence
    )
    return await SqlAlchemyApprovalRepository(session).add(
        _make_approval_task(
            tenant_id=tenant_id, ticket_id=ticket.id, agent_run_id=run.id, status=status
        )
    )


async def test_add_persists_and_is_retrievable_via_list(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    await session.commit()
    task = await _seed_task(session, tenant_id=tenant.id)
    await session.commit()

    result = await SqlAlchemyApprovalRepository(session).list(tenant.id, page=1, page_size=20)

    assert [t.id for t in result.items] == [task.id]
    assert result.total == 1


async def test_list_without_status_returns_only_pending(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    await session.commit()
    pending = await _seed_task(session, tenant_id=tenant.id, status=ApprovalStatus.pending)
    await _seed_task(session, tenant_id=tenant.id, status=ApprovalStatus.rejected)
    await session.commit()

    result = await SqlAlchemyApprovalRepository(session).list(tenant.id, page=1, page_size=20)

    assert [t.id for t in result.items] == [pending.id]


async def test_list_with_status_filters_by_that_status(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    await session.commit()
    await _seed_task(session, tenant_id=tenant.id, status=ApprovalStatus.pending)
    rejected = await _seed_task(session, tenant_id=tenant.id, status=ApprovalStatus.rejected)
    await session.commit()

    result = await SqlAlchemyApprovalRepository(session).list(
        tenant.id, status=ApprovalStatus.rejected, page=1, page_size=20
    )

    assert [t.id for t in result.items] == [rejected.id]


async def test_list_orders_by_sla_due_then_confidence(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    await session.commit()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    later = await _seed_task(session, tenant_id=tenant.id, sla_due=now + timedelta(hours=2))
    earlier = await _seed_task(session, tenant_id=tenant.id, sla_due=now + timedelta(hours=1))
    await session.commit()

    result = await SqlAlchemyApprovalRepository(session).list(tenant.id, page=1, page_size=20)

    assert [t.id for t in result.items] == [earlier.id, later.id]


async def test_list_with_tenant_id_isolates_by_tenant(session: AsyncSession) -> None:
    tenant_a = await _make_tenant(session)
    tenant_b = await _make_tenant(session)
    await session.commit()
    task_a = await _seed_task(session, tenant_id=tenant_a.id)
    await _seed_task(session, tenant_id=tenant_b.id)
    await session.commit()

    result = await SqlAlchemyApprovalRepository(session).list(tenant_a.id, page=1, page_size=20)

    assert [t.id for t in result.items] == [task_a.id]


async def test_list_with_tenant_id_none_aggregates_cross_tenant(session: AsyncSession) -> None:
    tenant_a = await _make_tenant(session)
    tenant_b = await _make_tenant(session)
    await session.commit()
    task_a = await _seed_task(session, tenant_id=tenant_a.id)
    task_b = await _seed_task(session, tenant_id=tenant_b.id)
    await session.commit()

    result = await SqlAlchemyApprovalRepository(session).list(None, page=1, page_size=20)

    assert {t.id for t in result.items} == {task_a.id, task_b.id}
    assert result.total == 2


async def test_list_paginates(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    await session.commit()
    for _ in range(25):
        await _seed_task(session, tenant_id=tenant.id)
    await session.commit()

    result = await SqlAlchemyApprovalRepository(session).list(tenant.id, page=1, page_size=20)

    assert len(result.items) == 20
    assert result.total == 25


async def test_decide_if_pending_applies_and_returns_updated_task(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    await session.commit()
    task = await _seed_task(session, tenant_id=tenant.id)
    await session.commit()
    repo = SqlAlchemyApprovalRepository(session)

    updated = await repo.decide_if_pending(task.id, "approved", None, None)
    await session.commit()

    assert updated is not None
    assert updated.status is ApprovalStatus.approved


async def test_decide_if_pending_returns_none_when_already_decided(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    await session.commit()
    task = await _seed_task(session, tenant_id=tenant.id)
    await session.commit()
    repo = SqlAlchemyApprovalRepository(session)
    await repo.decide_if_pending(task.id, "approved", None, None)
    await session.commit()

    second = await repo.decide_if_pending(task.id, "approved", None, None)

    assert second is None


async def test_decide_if_pending_raises_not_found_for_missing_task(session: AsyncSession) -> None:
    repo = SqlAlchemyApprovalRepository(session)

    with pytest.raises(NotFound):
        await repo.decide_if_pending(uuid.uuid4(), "approved", None, None)


async def test_decide_if_pending_with_final_body_persists_it(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    await session.commit()
    task = await _seed_task(session, tenant_id=tenant.id)
    await session.commit()
    repo = SqlAlchemyApprovalRepository(session)

    updated = await repo.decide_if_pending(task.id, "edited", "texto corregido", "nota")

    assert updated is not None
    assert updated.final_body == "texto corregido"
    assert updated.human_note == "nota"
