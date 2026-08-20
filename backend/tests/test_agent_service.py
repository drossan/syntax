"""Tests de app.domain.services.agent_service (tarea backend-routers-flujo-ia-01).

Nivel unit: puertos fake en memoria (`TicketRepository`/`AgentRunRepository`/`AgentRunner`/
`RateLimiter`). Traza a CU-BE-06 ampliado (escenarios de disparo) — la CAS real bajo concurrencia y el
aislamiento cross-tenant por RLS se verifican en integración (`test_repositories_agent_run.py` /
`test_router_agent.py`), no aquí.
"""

import uuid

import pytest
from app.domain.entities.business import AgentRun, Ticket
from app.domain.entities.enums import AgentRunStatus, TicketPriority, TicketStatus
from app.domain.errors import Conflict, NotFound, RateLimited
from app.domain.services.agent_service import AgentService

_TENANT = uuid.uuid4()


class _FakeTicketRepository:
    def __init__(self) -> None:
        self.store: dict[uuid.UUID, Ticket] = {}

    def seed(self, ticket: Ticket) -> None:
        self.store[ticket.id] = ticket

    async def get(self, ticket_id: uuid.UUID) -> Ticket | None:
        return self.store.get(ticket_id)


class _FakeAgentRunRepository:
    def __init__(self, *, active_run: AgentRun | None = None) -> None:
        self.store: dict[uuid.UUID, AgentRun] = {}
        self._active_run = active_run
        self.next_seq = 1
        self.get_active_for_ticket_calls: list[uuid.UUID] = []

    async def get(self, agent_run_id: uuid.UUID) -> AgentRun | None:
        return self.store.get(agent_run_id)

    async def add(self, run: AgentRun) -> AgentRun:
        self.store[run.id] = run
        return run

    async def next_run_seq(self, ticket_id: uuid.UUID) -> int:
        return self.next_seq

    async def get_active_for_ticket(self, ticket_id: uuid.UUID) -> AgentRun | None:
        self.get_active_for_ticket_calls.append(ticket_id)
        return self._active_run


class _FakeAgentRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[uuid.UUID, uuid.UUID, int, str]] = []

    async def trigger(
        self, tenant_id: uuid.UUID, ticket_id: uuid.UUID, run_seq: int, thread_id: str
    ) -> AgentRun:
        self.calls.append((tenant_id, ticket_id, run_seq, thread_id))
        return AgentRun(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            ticket_id=ticket_id,
            langgraph_thread_id=thread_id,
            run_seq=run_seq,
            status=AgentRunStatus.queued,
        )

    async def resume(self, agent_run_id: uuid.UUID, outcome: object) -> None:
        raise NotImplementedError


class _FakeRateLimiter:
    def __init__(self, *, allow: bool = True) -> None:
        self._allow = allow
        self.calls: list[str] = []

    async def check_and_increment(self, key: str) -> bool:
        self.calls.append(key)
        return self._allow


def _make_ticket(tenant_id: uuid.UUID = _TENANT) -> Ticket:
    return Ticket(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        subject="s",
        status=TicketStatus.open,
        priority=TicketPriority.normal,
    )


def _make_active_run(ticket_id: uuid.UUID) -> AgentRun:
    return AgentRun(
        id=uuid.uuid4(),
        tenant_id=_TENANT,
        ticket_id=ticket_id,
        langgraph_thread_id="ticket_x_run_1",
        run_seq=1,
        status=AgentRunStatus.queued,
    )


def _context(
    *, active_run: AgentRun | None = None, allow_rate_limit: bool = True
) -> tuple[
    AgentService, _FakeTicketRepository, _FakeAgentRunRepository, _FakeAgentRunner, _FakeRateLimiter
]:
    tickets = _FakeTicketRepository()
    agent_runs = _FakeAgentRunRepository(active_run=active_run)
    agent_runner = _FakeAgentRunner()
    rate_limiter = _FakeRateLimiter(allow=allow_rate_limit)
    svc = AgentService(
        tickets=tickets, agent_runs=agent_runs, agent_runner=agent_runner, rate_limiter=rate_limiter
    )
    return svc, tickets, agent_runs, agent_runner, rate_limiter


# ── trigger(): camino feliz ──


async def test_trigger_creates_a_queued_agent_run() -> None:
    svc, tickets, agent_runs, agent_runner, rate_limiter = _context()
    ticket = _make_ticket()
    tickets.seed(ticket)

    run = await svc.trigger(_TENANT, ticket.id)

    assert run.status is AgentRunStatus.queued
    assert run.ticket_id == ticket.id
    assert agent_runner.calls == [(_TENANT, ticket.id, 1, f"ticket_{ticket.id}_run_1")]


async def test_trigger_consumes_rate_limit_quota_keyed_by_tenant() -> None:
    svc, tickets, *_rest, rate_limiter = _context()
    ticket = _make_ticket()
    tickets.seed(ticket)

    await svc.trigger(_TENANT, ticket.id)

    assert rate_limiter.calls == [str(_TENANT)]


# ── trigger(): 404 ticket inexistente ──


async def test_trigger_on_a_nonexistent_ticket_raises_not_found() -> None:
    svc, *_ = _context()

    with pytest.raises(NotFound):
        await svc.trigger(_TENANT, uuid.uuid4())


async def test_trigger_on_a_nonexistent_ticket_does_not_consume_rate_limit_quota() -> None:
    svc, tickets, agent_runs, agent_runner, rate_limiter = _context()

    with pytest.raises(NotFound):
        await svc.trigger(_TENANT, uuid.uuid4())

    assert rate_limiter.calls == []
    assert agent_runs.get_active_for_ticket_calls == []
    assert agent_runner.calls == []


# ── trigger(): 409 run activo ──


async def test_trigger_with_an_active_run_raises_conflict() -> None:
    ticket_id = uuid.uuid4()
    svc, tickets, agent_runs, agent_runner, rate_limiter = _context(
        active_run=_make_active_run(ticket_id)
    )
    ticket = _make_ticket()
    tickets.seed(Ticket(**{**ticket.model_dump(), "id": ticket_id}))

    with pytest.raises(Conflict):
        await svc.trigger(_TENANT, ticket_id)


async def test_trigger_with_an_active_run_does_not_consume_rate_limit_quota() -> None:
    """scenario-coverage #1/#3: un disparo que va a fallar por 409 no gasta cuota de rate-limit."""
    ticket_id = uuid.uuid4()
    svc, tickets, agent_runs, agent_runner, rate_limiter = _context(
        active_run=_make_active_run(ticket_id)
    )
    ticket = _make_ticket()
    tickets.seed(Ticket(**{**ticket.model_dump(), "id": ticket_id}))

    with pytest.raises(Conflict):
        await svc.trigger(_TENANT, ticket_id)

    assert rate_limiter.calls == []
    assert agent_runner.calls == []


async def test_reopening_a_ticket_with_a_non_terminal_previous_run_still_blocks_a_new_trigger() -> (
    None
):
    """Limitación conocida y aceptada (grilling P1): sin 15/16, un run queued bloquea para siempre."""
    ticket_id = uuid.uuid4()
    svc, tickets, *_rest = _context(active_run=_make_active_run(ticket_id))
    ticket = _make_ticket()
    tickets.seed(
        Ticket(**{**ticket.model_dump(), "id": ticket_id, "status": TicketStatus.reopened})
    )

    with pytest.raises(Conflict):
        await svc.trigger(_TENANT, ticket_id)


# ── trigger(): 429 rate limit ──


async def test_trigger_beyond_the_rate_limit_raises_rate_limited() -> None:
    svc, tickets, *_rest = _context(allow_rate_limit=False)
    ticket = _make_ticket()
    tickets.seed(ticket)

    with pytest.raises(RateLimited):
        await svc.trigger(_TENANT, ticket.id)


async def test_trigger_beyond_the_rate_limit_does_not_create_an_agent_run() -> None:
    svc, tickets, agent_runs, agent_runner, rate_limiter = _context(allow_rate_limit=False)
    ticket = _make_ticket()
    tickets.seed(ticket)

    with pytest.raises(RateLimited):
        await svc.trigger(_TENANT, ticket.id)

    assert agent_runner.calls == []
    assert agent_runs.store == {}


# ── get() ──


async def test_get_returns_an_existing_run() -> None:
    svc, tickets, agent_runs, agent_runner, rate_limiter = _context()
    run = _make_active_run(uuid.uuid4())
    agent_runs.store[run.id] = run

    fetched = await svc.get(run.id)

    assert fetched is run


async def test_get_on_a_nonexistent_run_raises_not_found() -> None:
    svc, *_ = _context()

    with pytest.raises(NotFound):
        await svc.get(uuid.uuid4())
