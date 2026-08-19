"""app.domain.services.ticket_service — ciclo de vida del ticket (FR-016/017/018/020/021, CU-BE-04).

Máquina de estados validada contra una tabla de aristas exacta (RN-1 de CU-BE-04). `reopen()` deja el
ticket en **`reopened`** (estado de reposo real, confirmado por el Gherkin literal del CU) — no
auto-encadena a `open`; una transición posterior y separada la retoma. `sla_due` se calcula vía el
puerto `SlaPolicy` (nunca inventado aquí); FR-030 (run nuevo al reabrir, huérfanos) es un hueco nombrado
fuera de este servicio (ver el plan).
"""

import uuid

from app.domain.entities.business import AuditLogEntry, Message, Ticket
from app.domain.entities.enums import MessageVisibility, TicketPriority, TicketStatus
from app.domain.errors import InvalidTransition, NotFound, Validation
from app.domain.ports.clock import Clock
from app.domain.ports.repositories import AuditLogRepository, MessageRepository, TicketRepository
from app.domain.ports.sla_policy import SlaPolicy

_VALID_TRANSITIONS: frozenset[tuple[TicketStatus, TicketStatus]] = frozenset(
    {
        (TicketStatus.new, TicketStatus.open),
        (TicketStatus.open, TicketStatus.pending),
        (TicketStatus.pending, TicketStatus.resolved),
        (TicketStatus.resolved, TicketStatus.closed),
        (TicketStatus.resolved, TicketStatus.reopened),
        (TicketStatus.closed, TicketStatus.reopened),
        (TicketStatus.reopened, TicketStatus.open),
    }
)

_DEFAULT_PRIORITY = TicketPriority.normal
_CSAT_MIN = 1
_CSAT_MAX = 5


class TicketService:
    """Servicio de dominio del ciclo de vida del ticket. Puertos por inyección de constructor."""

    def __init__(
        self,
        tickets: TicketRepository,
        messages: MessageRepository,
        audit_log: AuditLogRepository,
        sla_policy: SlaPolicy,
        clock: Clock,
    ) -> None:
        self._tickets = tickets
        self._messages = messages
        self._audit_log = audit_log
        self._sla_policy = sla_policy
        self._clock = clock

    async def _get_or_raise(self, ticket_id: uuid.UUID) -> Ticket:
        ticket = await self._tickets.get(ticket_id)
        if ticket is None:
            raise NotFound(f"ticket {ticket_id} no existe", code="ticket.not_found")
        return ticket

    async def _audit(self, ticket: Ticket, action: str, payload: dict[str, object]) -> None:
        await self._audit_log.add(
            AuditLogEntry(
                tenant_id=ticket.tenant_id,
                action=action,
                entity_type="ticket",
                entity_id=str(ticket.id),
                payload=payload,
            )
        )

    async def create(
        self, tenant_id: uuid.UUID, requester_id: uuid.UUID, subject: str, body: str
    ) -> Ticket:
        """Alta: estado inicial `new`; primer mensaje del solicitante `public`; `sla_due` vía `SlaPolicy`."""
        now = self._clock.now()
        sla_due = self._sla_policy.due_at(_DEFAULT_PRIORITY, now, tenant_id)
        ticket = Ticket(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            subject=subject,
            status=TicketStatus.new,
            priority=_DEFAULT_PRIORITY,
            requester_id=requester_id,
            sla_due=sla_due,
        )
        await self._tickets.add(ticket)
        await self._messages.add(
            Message(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                ticket_id=ticket.id,
                author_id=requester_id,
                visibility=MessageVisibility.public,
                body=body,
            )
        )
        await self._audit(ticket, "ticket.created", {"status": ticket.status.value})
        return ticket

    async def transition(self, ticket_id: uuid.UUID, new_status: TicketStatus) -> Ticket:
        """Aplica una transición si es una arista válida; si no, `InvalidTransition` (no muta)."""
        ticket = await self._get_or_raise(ticket_id)
        if (ticket.status, new_status) not in _VALID_TRANSITIONS:
            raise InvalidTransition(
                f"transición inválida: {ticket.status.value} → {new_status.value}",
                code="ticket.invalid_transition",
                details={"from": ticket.status.value, "to": new_status.value},
            )
        previous = ticket.status
        ticket.status = new_status
        await self._tickets.update(ticket)
        await self._audit(
            ticket, "ticket.transitioned", {"from": previous.value, "to": new_status.value}
        )
        return ticket

    async def reopen(self, ticket_id: uuid.UUID) -> Ticket:
        """`resolved`/`closed` → `reopened` (estado de reposo real) + recalcula `sla_due` vía `SlaPolicy`."""
        ticket = await self.transition(ticket_id, TicketStatus.reopened)
        ticket.sla_due = self._sla_policy.due_at(
            ticket.priority, self._clock.now(), ticket.tenant_id
        )
        await self._tickets.update(ticket)
        return ticket

    async def assign(
        self,
        ticket_id: uuid.UUID,
        assignee_id: uuid.UUID | None,
        assignee_tenant_id: uuid.UUID | None,
    ) -> Ticket:
        """Set/clear de `assignee_id`. Si `assignee_id` no pertenece al tenant del ticket → `Validation`."""
        ticket = await self._get_or_raise(ticket_id)
        if assignee_id is not None and assignee_tenant_id != ticket.tenant_id:
            raise Validation(
                "el assignee no pertenece al tenant del ticket",
                code="ticket.assign_cross_tenant",
                details={"ticket_id": str(ticket_id)},
            )
        ticket.assignee_id = assignee_id
        await self._tickets.update(ticket)
        await self._audit(
            ticket, "ticket.assigned", {"assignee_id": str(assignee_id) if assignee_id else None}
        )
        return ticket

    async def set_csat(self, ticket_id: uuid.UUID, value: int) -> Ticket:
        """Fija el CSAT (`1..5`); fuera de rango → `Validation` (defensa de dominio, 1ª línea)."""
        if not (_CSAT_MIN <= value <= _CSAT_MAX):
            raise Validation(
                f"csat fuera de rango: {value}",
                code="ticket.csat_out_of_range",
                details={"value": value},
            )
        ticket = await self._get_or_raise(ticket_id)
        ticket.csat = value
        await self._tickets.update(ticket)
        await self._audit(ticket, "ticket.csat_set", {"csat": value})
        return ticket
