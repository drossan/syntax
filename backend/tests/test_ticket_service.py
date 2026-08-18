"""Tests de app.domain.services.ticket_service (tarea backend-domain-services-04).

Nivel unit, con TicketRepository/MessageRepository/AuditLogRepository/SlaPolicy fakes en memoria.
Traza a CU-BE-04. `reopen()` deja el ticket en `reopened` (estado de reposo real, no auto-encadena).
"""

import uuid
from datetime import UTC, datetime

import pytest
from app.domain.entities.business import Ticket
from app.domain.entities.enums import TicketPriority, TicketStatus
from app.domain.errors import InvalidTransition, NotFound, Validation
from app.domain.services.ticket_service import TicketService

_FIXED_NOW = datetime(2026, 1, 1, tzinfo=UTC)
_FIXED_SLA_DUE = datetime(2026, 1, 3, tzinfo=UTC)


class _FakeClock:
    def now(self) -> datetime:
        return _FIXED_NOW


class _FakeSlaPolicy:
    def __init__(self) -> None:
        self.calls: list[tuple[TicketPriority, datetime, uuid.UUID]] = []

    def due_at(
        self, priority: TicketPriority, from_: datetime, tenant_id: uuid.UUID
    ) -> datetime | None:
        self.calls.append((priority, from_, tenant_id))
        return _FIXED_SLA_DUE


class _FakeTicketRepository:
    def __init__(self) -> None:
        self.store: dict[uuid.UUID, Ticket] = {}

    async def get(self, ticket_id: uuid.UUID) -> Ticket | None:
        return self.store.get(ticket_id)

    async def add(self, ticket: Ticket) -> Ticket:
        self.store[ticket.id] = ticket
        return ticket

    async def update(self, ticket: Ticket) -> Ticket:
        self.store[ticket.id] = ticket
        return ticket

    async def list(self, tenant_id: uuid.UUID) -> list[Ticket]:
        return [t for t in self.store.values() if t.tenant_id == tenant_id]


class _FakeMessageRepository:
    def __init__(self) -> None:
        self.added: list[object] = []

    async def add(self, message: object) -> object:
        self.added.append(message)
        return message

    async def list_by_ticket(self, ticket_id: uuid.UUID) -> list[object]:
        return self.added


class _FakeAuditLogRepository:
    def __init__(self) -> None:
        self.entries: list[object] = []

    async def add(self, entry: object) -> None:
        self.entries.append(entry)


@pytest.fixture
def service() -> tuple[
    "TicketService",
    _FakeTicketRepository,
    _FakeMessageRepository,
    _FakeAuditLogRepository,
    _FakeSlaPolicy,
]:
    tickets = _FakeTicketRepository()
    messages = _FakeMessageRepository()
    audit = _FakeAuditLogRepository()
    sla = _FakeSlaPolicy()
    svc = TicketService(
        tickets=tickets, messages=messages, audit_log=audit, sla_policy=sla, clock=_FakeClock()
    )
    return svc, tickets, messages, audit, sla


_TENANT = uuid.UUID(int=1)
_REQUESTER = uuid.uuid4()


async def _make_ticket(svc: "TicketService") -> Ticket:
    return await svc.create(tenant_id=_TENANT, requester_id=_REQUESTER, subject="s", body="b")


async def test_create_ticket_starts_new_with_public_message(service: tuple) -> None:
    """Alta de un ticket: estado new en su tenant, primer mensaje público."""
    svc, _, messages, audit, sla = service
    ticket = await _make_ticket(svc)
    assert ticket.status is TicketStatus.new
    assert ticket.tenant_id == _TENANT
    assert len(messages.added) == 1
    assert len(audit.entries) == 1
    assert sla.calls  # sla_due se pidió al puerto


async def test_create_ticket_sets_sla_due_from_policy(service: tuple) -> None:
    """sla_due se fija desde SlaPolicy.due_at (no inventado en el servicio)."""
    svc, *_ = service
    ticket = await _make_ticket(svc)
    assert ticket.sla_due == _FIXED_SLA_DUE


@pytest.mark.parametrize(
    ("from_status", "to_status", "should_succeed"),
    [
        (TicketStatus.new, TicketStatus.open, True),
        (TicketStatus.open, TicketStatus.pending, True),
        (TicketStatus.pending, TicketStatus.resolved, True),
        (TicketStatus.resolved, TicketStatus.closed, True),
        (TicketStatus.resolved, TicketStatus.reopened, True),
        (TicketStatus.closed, TicketStatus.reopened, True),
        (TicketStatus.reopened, TicketStatus.open, True),
        (TicketStatus.new, TicketStatus.closed, False),  # salta la cadena
        (TicketStatus.open, TicketStatus.open, False),  # auto-transición
        (TicketStatus.closed, TicketStatus.open, False),  # closed no va directo a open
    ],
)
async def test_transition_follows_exact_edge_table(
    service: tuple, from_status: TicketStatus, to_status: TicketStatus, should_succeed: bool
) -> None:
    """La máquina de estados valida contra la tabla exacta de aristas (RN-1 de CU-BE-04)."""
    svc, tickets, *_ = service
    ticket = await _make_ticket(svc)
    ticket.status = from_status
    await tickets.update(ticket)
    if should_succeed:
        updated = await svc.transition(ticket.id, to_status)
        assert updated.status is to_status
    else:
        with pytest.raises(InvalidTransition):
            await svc.transition(ticket.id, to_status)
        assert (await tickets.get(ticket.id)).status is from_status  # no muta


async def test_transition_on_missing_ticket_raises_not_found(service: tuple) -> None:
    """Transicionar un ticket_id inexistente → NotFound."""
    svc, *_ = service
    with pytest.raises(NotFound):
        await svc.transition(uuid.uuid4(), TicketStatus.open)


@pytest.mark.parametrize("from_status", [TicketStatus.resolved, TicketStatus.closed])
async def test_reopen_leaves_ticket_in_reopened_state(
    service: tuple, from_status: TicketStatus
) -> None:
    """reopen() deja el ticket en 'reopened' (estado de reposo real) desde resolved o closed."""
    svc, tickets, *_ = service
    ticket = await _make_ticket(svc)
    ticket.status = from_status
    await tickets.update(ticket)
    reopened = await svc.reopen(ticket.id)
    assert reopened.status is TicketStatus.reopened


async def test_reopen_recomputes_sla_due(service: tuple) -> None:
    """reopen() recalcula sla_due vía SlaPolicy (coherente con 'al crear/reabrir')."""
    svc, tickets, _, _, sla = service
    ticket = await _make_ticket(svc)
    ticket.status = TicketStatus.closed
    ticket.sla_due = None
    await tickets.update(ticket)
    calls_before = len(sla.calls)
    reopened = await svc.reopen(ticket.id)
    assert reopened.sla_due == _FIXED_SLA_DUE
    assert len(sla.calls) == calls_before + 1


async def test_reopened_to_open_is_separate_transition(service: tuple) -> None:
    """reopened→open es una transición posterior e independiente (no la aplica reopen())."""
    svc, tickets, *_ = service
    ticket = await _make_ticket(svc)
    ticket.status = TicketStatus.reopened
    await tickets.update(ticket)
    updated = await svc.transition(ticket.id, TicketStatus.open)
    assert updated.status is TicketStatus.open


async def test_assign_sets_assignee(service: tuple) -> None:
    """assign() fija el assignee_id del ticket (mismo tenant)."""
    svc, *_ = service
    ticket = await _make_ticket(svc)
    assignee_id = uuid.uuid4()
    updated = await svc.assign(ticket.id, assignee_id, assignee_tenant_id=_TENANT)
    assert updated.assignee_id == assignee_id


async def test_assign_clears_assignee_with_none(service: tuple) -> None:
    """assign(None) limpia la asignación (sin comprobar tenant, no hay a quién comprobar)."""
    svc, *_ = service
    ticket = await _make_ticket(svc)
    await svc.assign(ticket.id, uuid.uuid4(), assignee_tenant_id=_TENANT)
    cleared = await svc.assign(ticket.id, None, assignee_tenant_id=None)
    assert cleared.assignee_id is None


@pytest.mark.parametrize("other_tenant", [uuid.UUID(int=2), uuid.UUID(int=0)])
async def test_assign_cross_tenant_is_rejected(service: tuple, other_tenant: uuid.UUID) -> None:
    """Asignar a un assignee de OTRO tenant se rechaza (Validation) en ambos órdenes de UUID."""
    svc, tickets, *_ = service
    ticket = await _make_ticket(svc)
    with pytest.raises(Validation):
        await svc.assign(ticket.id, uuid.uuid4(), assignee_tenant_id=other_tenant)
    assert (await tickets.get(ticket.id)).assignee_id is None


async def test_assign_same_tenant_by_value_not_identity_is_allowed(service: tuple) -> None:
    """Un assignee_tenant_id con el MISMO valor (objeto UUID distinto) se acepta (comparación por valor)."""
    svc, *_ = service
    ticket = await _make_ticket(svc)
    same_value_different_object = uuid.UUID(str(_TENANT))
    assert same_value_different_object is not _TENANT
    updated = await svc.assign(
        ticket.id, uuid.uuid4(), assignee_tenant_id=same_value_different_object
    )
    assert updated.assignee_id is not None


@pytest.mark.parametrize(
    ("value", "should_succeed"), [(0, False), (1, True), (5, True), (6, False)]
)
async def test_set_csat_range(service: tuple, value: int, should_succeed: bool) -> None:
    """CSAT fuera de 1..5 se rechaza (Validation), dentro se acepta."""
    svc, *_ = service
    ticket = await _make_ticket(svc)
    if should_succeed:
        updated = await svc.set_csat(ticket.id, value)
        assert updated.csat == value
    else:
        with pytest.raises(Validation):
            await svc.set_csat(ticket.id, value)


async def test_every_mutation_is_audited(service: tuple) -> None:
    """Toda mutación (crear/transicionar/asignar/csat) escribe una entrada de auditoría."""
    svc, _tickets, _messages, audit, _sla = service
    ticket = await _make_ticket(svc)
    count_after_create = len(audit.entries)
    await svc.transition(ticket.id, TicketStatus.open)
    await svc.assign(ticket.id, uuid.uuid4(), assignee_tenant_id=_TENANT)
    await svc.set_csat(ticket.id, 5)
    assert len(audit.entries) == count_after_create + 3
