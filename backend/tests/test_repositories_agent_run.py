"""Tests de integración de `SqlAlchemyAgentRunRepository` (tarea `backend-routers-flujo-ia-01`).

Postgres real vía `superuser_engine` (RLS no aplica — se prueba el CONTRATO del adaptador: CRUD,
`next_run_seq`, `get_active_for_ticket` y el CAS real de `add()` contra el índice único parcial
`ix_agent_run_active_per_ticket`, no el aislamiento RLS en sí).
"""

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from app.domain.entities.business import AgentRun, Ticket
from app.domain.entities.enums import AgentRunStatus, TenantStatus, TicketPriority, TicketStatus
from app.domain.entities.identity import Tenant
from app.domain.errors import Conflict
from app.infra.db.repositories.agent_run import SqlAlchemyAgentRunRepository
from app.infra.db.repositories.tenant import SqlAlchemyTenantRepository
from app.infra.db.repositories.ticket import SqlAlchemyTicketRepository
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

_TRUNCATE_TABLES = "TRUNCATE agent_run, ticket, tenant RESTART IDENTITY CASCADE"


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


async def _make_ticket(session: AsyncSession, tenant_id: uuid.UUID) -> Ticket:
    return await SqlAlchemyTicketRepository(session).add(
        Ticket(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            subject="s",
            status=TicketStatus.new,
            priority=TicketPriority.normal,
        )
    )


def _make_run(
    *,
    tenant_id: uuid.UUID,
    ticket_id: uuid.UUID,
    run_seq: int = 1,
    status: AgentRunStatus = AgentRunStatus.queued,
    thread: str | None = None,
) -> AgentRun:
    return AgentRun(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        ticket_id=ticket_id,
        langgraph_thread_id=thread or f"ticket_{ticket_id}_run_{run_seq}",
        run_seq=run_seq,
        status=status,
    )


async def test_add_persists_and_returns_the_agent_run(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    ticket = await _make_ticket(session, tenant.id)
    await session.commit()
    repo = SqlAlchemyAgentRunRepository(session)

    run = await repo.add(_make_run(tenant_id=tenant.id, ticket_id=ticket.id))
    await session.commit()

    assert run.status is AgentRunStatus.queued
    fetched = await repo.get(run.id)
    assert fetched is not None
    assert fetched.id == run.id
    assert fetched.tenant_id == tenant.id
    assert fetched.ticket_id == ticket.id


async def test_get_returns_none_when_missing(session: AsyncSession) -> None:
    repo = SqlAlchemyAgentRunRepository(session)
    assert await repo.get(uuid.uuid4()) is None


async def test_add_raises_conflict_when_the_ticket_already_has_an_active_run(
    session: AsyncSession,
) -> None:
    """El 2º INSERT concurrente/secuencial de un run no-terminal para el MISMO ticket viola el
    índice único parcial — CAS real, no un check previo del repositorio."""
    tenant = await _make_tenant(session)
    ticket = await _make_ticket(session, tenant.id)
    await session.commit()
    repo = SqlAlchemyAgentRunRepository(session)
    await repo.add(_make_run(tenant_id=tenant.id, ticket_id=ticket.id, run_seq=1))
    await session.commit()

    with pytest.raises(Conflict):
        await repo.add(_make_run(tenant_id=tenant.id, ticket_id=ticket.id, run_seq=2))


async def test_add_succeeds_for_a_new_run_once_the_previous_one_is_terminal(
    session: AsyncSession,
) -> None:
    tenant = await _make_tenant(session)
    ticket = await _make_ticket(session, tenant.id)
    await session.commit()
    repo = SqlAlchemyAgentRunRepository(session)
    first = await repo.add(
        _make_run(
            tenant_id=tenant.id, ticket_id=ticket.id, run_seq=1, status=AgentRunStatus.succeeded
        )
    )
    await session.commit()

    second = await repo.add(_make_run(tenant_id=tenant.id, ticket_id=ticket.id, run_seq=2))
    await session.commit()

    assert first.id != second.id


async def test_update_status_persists_the_new_status(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    ticket = await _make_ticket(session, tenant.id)
    await session.commit()
    repo = SqlAlchemyAgentRunRepository(session)
    run = await repo.add(_make_run(tenant_id=tenant.id, ticket_id=ticket.id))
    await session.commit()

    updated = await repo.update_status(run.id, "succeeded")
    await session.commit()

    assert updated.status is AgentRunStatus.succeeded
    fetched = await repo.get(run.id)
    assert fetched is not None
    assert fetched.status is AgentRunStatus.succeeded


async def test_next_run_seq_starts_at_one_for_a_ticket_without_runs(
    session: AsyncSession,
) -> None:
    tenant = await _make_tenant(session)
    ticket = await _make_ticket(session, tenant.id)
    await session.commit()
    repo = SqlAlchemyAgentRunRepository(session)

    assert await repo.next_run_seq(ticket.id) == 1


async def test_next_run_seq_increments_from_the_highest_existing_seq(
    session: AsyncSession,
) -> None:
    tenant = await _make_tenant(session)
    ticket = await _make_ticket(session, tenant.id)
    await session.commit()
    repo = SqlAlchemyAgentRunRepository(session)
    await repo.add(
        _make_run(
            tenant_id=tenant.id, ticket_id=ticket.id, run_seq=1, status=AgentRunStatus.succeeded
        )
    )
    await repo.add(
        _make_run(tenant_id=tenant.id, ticket_id=ticket.id, run_seq=2, status=AgentRunStatus.failed)
    )
    await session.commit()

    assert await repo.next_run_seq(ticket.id) == 3


async def test_next_run_seq_filters_by_exact_ticket_id_not_range(session: AsyncSession) -> None:
    """IDs deterministas (bajo/medio/alto) para matar mutantes de comparación (`==`→`<=`/`>=`/
    `is not`) en el filtro `ticket_id` — sin esto, `next_run_seq` podría filtrar por rango en vez de
    por igualdad exacta y arrastrar el `run_seq` de OTRO ticket."""
    tenant = await _make_tenant(session)
    ticket_repo = SqlAlchemyTicketRepository(session)
    low = await ticket_repo.add(
        Ticket(
            id=uuid.UUID(int=10),
            tenant_id=tenant.id,
            subject="s",
            status=TicketStatus.new,
            priority=TicketPriority.normal,
        )
    )
    mid = await ticket_repo.add(
        Ticket(
            id=uuid.UUID(int=20),
            tenant_id=tenant.id,
            subject="s",
            status=TicketStatus.new,
            priority=TicketPriority.normal,
        )
    )
    high = await ticket_repo.add(
        Ticket(
            id=uuid.UUID(int=30),
            tenant_id=tenant.id,
            subject="s",
            status=TicketStatus.new,
            priority=TicketPriority.normal,
        )
    )
    await session.commit()
    repo = SqlAlchemyAgentRunRepository(session)
    await repo.add(
        _make_run(
            tenant_id=tenant.id, ticket_id=low.id, run_seq=99, status=AgentRunStatus.succeeded
        )
    )
    await repo.add(
        _make_run(tenant_id=tenant.id, ticket_id=mid.id, run_seq=1, status=AgentRunStatus.succeeded)
    )
    await repo.add(
        _make_run(
            tenant_id=tenant.id, ticket_id=high.id, run_seq=99, status=AgentRunStatus.succeeded
        )
    )
    await session.commit()

    assert await repo.next_run_seq(mid.id) == 2


async def test_get_active_for_ticket_returns_none_without_any_run(
    session: AsyncSession,
) -> None:
    tenant = await _make_tenant(session)
    ticket = await _make_ticket(session, tenant.id)
    await session.commit()
    repo = SqlAlchemyAgentRunRepository(session)

    assert await repo.get_active_for_ticket(ticket.id) is None


async def test_get_active_for_ticket_returns_none_when_all_runs_are_terminal(
    session: AsyncSession,
) -> None:
    tenant = await _make_tenant(session)
    ticket = await _make_ticket(session, tenant.id)
    await session.commit()
    repo = SqlAlchemyAgentRunRepository(session)
    await repo.add(
        _make_run(
            tenant_id=tenant.id, ticket_id=ticket.id, run_seq=1, status=AgentRunStatus.succeeded
        )
    )
    await session.commit()

    assert await repo.get_active_for_ticket(ticket.id) is None


@pytest.mark.parametrize("status", [AgentRunStatus.queued, AgentRunStatus.running])
async def test_get_active_for_ticket_returns_the_non_terminal_run(
    session: AsyncSession, status: AgentRunStatus
) -> None:
    tenant = await _make_tenant(session)
    ticket = await _make_ticket(session, tenant.id)
    await session.commit()
    repo = SqlAlchemyAgentRunRepository(session)
    run = await repo.add(_make_run(tenant_id=tenant.id, ticket_id=ticket.id, status=status))
    await session.commit()

    active = await repo.get_active_for_ticket(ticket.id)

    assert active is not None
    assert active.id == run.id


async def test_get_active_for_ticket_filters_by_exact_ticket_id_not_range(
    session: AsyncSession,
) -> None:
    """IDs deterministas (bajo/medio/alto): un run activo de OTRO ticket nunca se confunde con el
    del ticket consultado — mata los mismos mutantes de comparación que `next_run_seq`."""
    tenant = await _make_tenant(session)
    ticket_repo = SqlAlchemyTicketRepository(session)
    low = await ticket_repo.add(
        Ticket(
            id=uuid.UUID(int=110),
            tenant_id=tenant.id,
            subject="s",
            status=TicketStatus.new,
            priority=TicketPriority.normal,
        )
    )
    mid = await ticket_repo.add(
        Ticket(
            id=uuid.UUID(int=120),
            tenant_id=tenant.id,
            subject="s",
            status=TicketStatus.new,
            priority=TicketPriority.normal,
        )
    )
    high = await ticket_repo.add(
        Ticket(
            id=uuid.UUID(int=130),
            tenant_id=tenant.id,
            subject="s",
            status=TicketStatus.new,
            priority=TicketPriority.normal,
        )
    )
    await session.commit()
    repo = SqlAlchemyAgentRunRepository(session)
    await repo.add(_make_run(tenant_id=tenant.id, ticket_id=low.id, status=AgentRunStatus.queued))
    await repo.add(_make_run(tenant_id=tenant.id, ticket_id=high.id, status=AgentRunStatus.queued))
    await session.commit()

    assert await repo.get_active_for_ticket(mid.id) is None
