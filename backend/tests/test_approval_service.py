"""Tests de app.domain.services.approval_service (tarea backend-domain-services-08).

Nivel unit: `ApprovalRepository`/`AgentRunner` fakes en memoria + un `TicketService` real construido
sobre fakes de sus propios puertos (mismo patrón que test_ticket_service.py). Traza a CU-BE-06 (parcial:
solo la parte de `approval_service`, no el nodo `respond` del grafo).
"""

import uuid
from datetime import UTC, datetime

import pytest
from app.domain.entities.business import ApprovalTask, Ticket
from app.domain.entities.enums import ApprovalStatus, KbDomain, TicketPriority, TicketStatus
from app.domain.errors import Conflict, InvalidTransition, NotFound, Validation
from app.domain.ports.agent_runner import ApprovalOutcome
from app.domain.ports.repositories import PageResult
from app.domain.services.approval_service import ApprovalService
from app.domain.services.ticket_service import TicketService

_NOW = datetime(2026, 1, 1, tzinfo=UTC)
_TENANT_A = uuid.UUID(int=1)
_TENANT_B = uuid.UUID(int=2)


class _FakeClock:
    def now(self) -> datetime:
        return _NOW


class _FakeSlaPolicy:
    def due_at(
        self, priority: TicketPriority, from_: datetime, tenant_id: uuid.UUID
    ) -> datetime | None:
        return None


class _FakeTicketRepository:
    def __init__(self) -> None:
        self.store: dict[uuid.UUID, Ticket] = {}

    def seed(self, ticket: Ticket) -> None:
        self.store[ticket.id] = ticket

    async def get(self, ticket_id: uuid.UUID) -> Ticket | None:
        return self.store.get(ticket_id)

    async def add(self, ticket: Ticket) -> Ticket:
        self.store[ticket.id] = ticket
        return ticket

    async def update(self, ticket: Ticket) -> Ticket:
        self.store[ticket.id] = ticket
        return ticket

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 20,
        status: TicketStatus | None = None,
        priority: TicketPriority | None = None,
        domain: KbDomain | None = None,
        assignee_id: uuid.UUID | None = None,
        sort: str = "-updated_at",
    ) -> PageResult[Ticket]:
        items = [t for t in self.store.values() if t.tenant_id == tenant_id]
        if status is not None:
            items = [t for t in items if t.status == status]
        if priority is not None:
            items = [t for t in items if t.priority == priority]
        if domain is not None:
            items = [t for t in items if t.domain == domain]
        if assignee_id is not None:
            items = [t for t in items if t.assignee_id == assignee_id]
        reverse = sort.startswith("-")
        key = sort.lstrip("-")
        items.sort(key=lambda t: getattr(t, key) or 0, reverse=reverse)
        total = len(items)
        start = (page - 1) * page_size
        return PageResult(items=items[start : start + page_size], total=total)


class _FakeMessageRepository:
    async def add(self, message: object) -> object:
        return message

    async def list_by_ticket(
        self, ticket_id: uuid.UUID, *, page: int = 1, page_size: int = 20
    ) -> PageResult[object]:
        return PageResult(items=[], total=0)

    async def add_attachment(self, attachment: object) -> object:
        return attachment

    async def get_attachment(self, attachment_id: uuid.UUID) -> object | None:
        return None


class _FakeAuditLogRepository:
    async def add(self, entry: object) -> None:
        pass


class _FakeApprovalRepository:
    def __init__(self) -> None:
        self.store: dict[uuid.UUID, ApprovalTask] = {}

    def seed(self, task: ApprovalTask) -> None:
        self.store[task.id] = task

    async def add(self, task: ApprovalTask) -> ApprovalTask:
        self.store[task.id] = task
        return task

    async def list_pending(self, tenant_id: uuid.UUID) -> list[ApprovalTask]:
        return [
            t
            for t in self.store.values()
            if t.tenant_id == tenant_id and t.status is ApprovalStatus.pending
        ]

    async def decide_if_pending(
        self,
        task_id: uuid.UUID,
        decision: str,
        final_body: str | None,
        human_note: str | None,
    ) -> ApprovalTask | None:
        task = self.store.get(task_id)
        if task is None:
            raise NotFound(f"approval task {task_id} no existe", code="approval.not_found")
        if task.status is not ApprovalStatus.pending:
            return None
        task.status = ApprovalStatus(decision)
        task.final_body = final_body
        task.human_note = human_note
        self.store[task_id] = task
        return task


class _FakeAgentRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[uuid.UUID, ApprovalOutcome]] = []

    async def resume(self, agent_run_id: uuid.UUID, outcome: ApprovalOutcome) -> None:
        self.calls.append((agent_run_id, outcome))


def _make_ticket(*, tenant_id: uuid.UUID, status: TicketStatus) -> Ticket:
    return Ticket(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        subject="s",
        status=status,
        priority=TicketPriority.normal,
    )


def _make_approval_task(
    *,
    tenant_id: uuid.UUID = _TENANT_A,
    ticket_id: uuid.UUID,
    status: ApprovalStatus = ApprovalStatus.pending,
) -> ApprovalTask:
    return ApprovalTask(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        ticket_id=ticket_id,
        agent_run_id=uuid.uuid4(),
        status=status,
        draft_body="draft",
    )


@pytest.fixture
def context() -> tuple:
    tickets = _FakeTicketRepository()
    ticket_service = TicketService(
        tickets=tickets,
        messages=_FakeMessageRepository(),
        audit_log=_FakeAuditLogRepository(),
        sla_policy=_FakeSlaPolicy(),
        clock=_FakeClock(),
    )
    approvals = _FakeApprovalRepository()
    agent_runner = _FakeAgentRunner()
    svc = ApprovalService(
        approvals=approvals, ticket_service=ticket_service, agent_runner=agent_runner
    )
    return svc, approvals, tickets, agent_runner


async def test_approve_applies_cas_transitions_ticket_and_resumes_once(context: tuple) -> None:
    """approve: CAS aplica, el ticket transiciona a pending, y resume() se llama una sola vez."""
    svc, approvals, tickets, agent_runner = context
    ticket = _make_ticket(tenant_id=_TENANT_A, status=TicketStatus.open)
    tickets.seed(ticket)
    task = _make_approval_task(ticket_id=ticket.id)
    approvals.seed(task)

    updated = await svc.decide(task.id, "approve", None, None)

    assert updated.status is ApprovalStatus.approved
    assert (await tickets.get(ticket.id)).status is TicketStatus.pending
    assert len(agent_runner.calls) == 1
    called_agent_run_id, outcome = agent_runner.calls[0]
    assert called_agent_run_id == task.agent_run_id
    assert outcome.status is ApprovalStatus.approved


async def test_edit_requires_final_body_and_applies_it(context: tuple) -> None:
    """edit con final_body: CAS aplica con el texto corregido, ticket transiciona a pending."""
    svc, approvals, tickets, agent_runner = context
    ticket = _make_ticket(tenant_id=_TENANT_A, status=TicketStatus.open)
    tickets.seed(ticket)
    task = _make_approval_task(ticket_id=ticket.id)
    approvals.seed(task)

    updated = await svc.decide(task.id, "edit", "texto corregido", None)

    assert updated.status is ApprovalStatus.edited
    assert updated.final_body == "texto corregido"
    assert (await tickets.get(ticket.id)).status is TicketStatus.pending
    assert agent_runner.calls[0][1].final_body == "texto corregido"


@pytest.mark.parametrize("final_body", [None, ""])
async def test_edit_without_final_body_is_rejected_without_cas(
    context: tuple, final_body: str | None
) -> None:
    """edit sin final_body (None o vacío) se rechaza ANTES del CAS: la tarea sigue pending."""
    svc, approvals, tickets, agent_runner = context
    ticket = _make_ticket(tenant_id=_TENANT_A, status=TicketStatus.open)
    tickets.seed(ticket)
    task = _make_approval_task(ticket_id=ticket.id)
    approvals.seed(task)

    with pytest.raises(Validation):
        await svc.decide(task.id, "edit", final_body, None)

    assert approvals.store[task.id].status is ApprovalStatus.pending
    assert agent_runner.calls == []


async def test_reject_does_not_transition_ticket_and_requires_human_note(context: tuple) -> None:
    """reject: no transiciona el ticket, pero SÍ llama a resume() (el grafo necesita saber el outcome)."""
    svc, approvals, tickets, agent_runner = context
    ticket = _make_ticket(tenant_id=_TENANT_A, status=TicketStatus.open)
    tickets.seed(ticket)
    task = _make_approval_task(ticket_id=ticket.id)
    approvals.seed(task)

    updated = await svc.decide(task.id, "reject", None, "no aplica a este caso")

    assert updated.status is ApprovalStatus.rejected
    assert (await tickets.get(ticket.id)).status is TicketStatus.open  # sin transicionar
    assert len(agent_runner.calls) == 1
    assert agent_runner.calls[0][1].status is ApprovalStatus.rejected


@pytest.mark.parametrize("human_note", [None, ""])
async def test_reject_without_human_note_is_rejected_without_cas(
    context: tuple, human_note: str | None
) -> None:
    """reject sin human_note se rechaza ANTES del CAS: la tarea sigue pending, sin resume."""
    svc, approvals, tickets, agent_runner = context
    ticket = _make_ticket(tenant_id=_TENANT_A, status=TicketStatus.open)
    tickets.seed(ticket)
    task = _make_approval_task(ticket_id=ticket.id)
    approvals.seed(task)

    with pytest.raises(Validation):
        await svc.decide(task.id, "reject", None, human_note)

    assert approvals.store[task.id].status is ApprovalStatus.pending
    assert agent_runner.calls == []


async def test_decide_with_unknown_decision_value_is_rejected(context: tuple) -> None:
    """Un `decision` fuera de Decision (no forzado en runtime) se rechaza con Validation, no KeyError."""
    svc, approvals, tickets, agent_runner = context
    ticket = _make_ticket(tenant_id=_TENANT_A, status=TicketStatus.open)
    tickets.seed(ticket)
    task = _make_approval_task(ticket_id=ticket.id)
    approvals.seed(task)

    with pytest.raises(Validation):
        await svc.decide(task.id, "zzz-not-a-real-decision", None, None)  # type: ignore[arg-type]

    assert approvals.store[task.id].status is ApprovalStatus.pending
    assert agent_runner.calls == []


async def test_decide_on_nonexistent_task_raises_not_found(context: tuple) -> None:
    """task_id que no corresponde a ninguna ApprovalTask → NotFound (distinto de 'ya decidida')."""
    svc, *_ = context
    with pytest.raises(NotFound):
        await svc.decide(uuid.uuid4(), "approve", None, None)


async def test_double_decision_raises_conflict_without_second_resume(context: tuple) -> None:
    """Doble decisión: la 2ª decide_if_pending devuelve None → Conflict, sin un segundo resume()."""
    svc, approvals, tickets, agent_runner = context
    ticket = _make_ticket(tenant_id=_TENANT_A, status=TicketStatus.open)
    tickets.seed(ticket)
    task = _make_approval_task(ticket_id=ticket.id)
    approvals.seed(task)

    await svc.decide(task.id, "approve", None, None)
    assert len(agent_runner.calls) == 1

    with pytest.raises(Conflict):
        await svc.decide(task.id, "approve", None, None)
    assert len(agent_runner.calls) == 1  # sin segundo resume


async def test_list_pending_isolates_by_tenant(context: tuple) -> None:
    """list_pending(tenant_A) solo devuelve las tareas de A, aunque haya pendientes de B."""
    svc, approvals, tickets, _ = context
    ticket_a = _make_ticket(tenant_id=_TENANT_A, status=TicketStatus.open)
    ticket_b = _make_ticket(tenant_id=_TENANT_B, status=TicketStatus.open)
    tickets.seed(ticket_a)
    tickets.seed(ticket_b)
    task_a = _make_approval_task(tenant_id=_TENANT_A, ticket_id=ticket_a.id)
    task_b = _make_approval_task(tenant_id=_TENANT_B, ticket_id=ticket_b.id)
    approvals.seed(task_a)
    approvals.seed(task_b)

    pending_a = await svc.list_pending(_TENANT_A)

    assert [t.id for t in pending_a] == [task_a.id]


async def test_failure_after_cas_propagates_without_compensation(context: tuple) -> None:
    """Fallo tras el CAS (el ticket ya no admite la transición a pending): la excepción se propaga y
    la ApprovalTask YA quedó approved (riesgo conocido, sin compensación en este plan)."""
    svc, approvals, tickets, agent_runner = context
    # `new` -> `pending` no es una arista válida de _VALID_TRANSITIONS: transition() lanzará.
    ticket = _make_ticket(tenant_id=_TENANT_A, status=TicketStatus.new)
    tickets.seed(ticket)
    task = _make_approval_task(ticket_id=ticket.id)
    approvals.seed(task)

    with pytest.raises(InvalidTransition):
        await svc.decide(task.id, "approve", None, None)

    assert approvals.store[task.id].status is ApprovalStatus.approved  # ya no hay vuelta atrás
    assert agent_runner.calls == []  # no llegó a resume: transition() falló antes
