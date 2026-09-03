"""app.domain.services.ticket_service — ciclo de vida del ticket (FR-016/017/018/020/021, CU-BE-04).

Máquina de estados validada contra una tabla de aristas exacta (RN-1 de CU-BE-04). `reopen()` deja el
ticket en **`reopened`** (estado de reposo real, confirmado por el Gherkin literal del CU) — no
auto-encadena a `open`; una transición posterior y separada la retoma. `sla_due` se calcula vía el
puerto `SlaPolicy` (nunca inventado aquí); FR-030 (run nuevo al reabrir, huérfanos) es un hueco nombrado
fuera de este servicio (ver el plan).
"""

import uuid

from app.domain.entities.business import AuditLogEntry, Message, Ticket
from app.domain.entities.enums import KbDomain, MessageVisibility, TicketPriority, TicketStatus
from app.domain.errors import InvalidTransition, NotFound, Validation
from app.domain.ports.clock import Clock
from app.domain.ports.repositories import (
    AuditLogRepository,
    MessageRepository,
    PageResult,
    TicketRepository,
)
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


def _shortest_path(start: TicketStatus, target: TicketStatus) -> list[TicketStatus] | None:
    """BFS sobre `_VALID_TRANSITIONS` con visitados — cycle-safe (el grafo tiene ciclos reales).
    Devuelve la secuencia de estados a recorrer (sin incluir `start`), o `None` si `target` es
    inalcanzable desde `start`. Usado por `advance_to()`; no valida `start == target` (responsabilidad
    del llamante, que lo trata como no-op antes de llegar aquí).

    Las aristas HACIA `reopened` (`resolved→reopened`, `closed→reopened`) se excluyen del recorrido
    salvo que `reopened` sea el propio `target` — "reabrir" es una acción de negocio deliberada
    (`reopen()`), no un paso intermedio implícito hacia otro destino. Sin esta exclusión, un ticket
    `resolved` "alcanzaría" `pending` rebotando por el ciclo `resolved→reopened→open→pending`, lo que
    cambiaría el comportamiento observable de `approval_service.decide()` (antes fallaba con
    `InvalidTransition` para un ticket ya `resolved` — reproducido y confirmado con test real)."""
    queue: list[tuple[TicketStatus, list[TicketStatus]]] = [(start, [])]
    visited: set[TicketStatus] = {start}
    while queue:
        node, path = queue.pop(0)
        for from_status, to_status in _VALID_TRANSITIONS:
            if from_status is not node or to_status in visited:
                continue
            if to_status is TicketStatus.reopened and target is not TicketStatus.reopened:
                continue
            next_path = [*path, to_status]
            if to_status is target:
                return next_path
            visited.add(to_status)
            queue.append((to_status, next_path))
    return None


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

    async def get(self, ticket_id: uuid.UUID) -> Ticket:
        """`GET /tickets/{id}` (07): `NotFound` si no existe — el aislamiento cross-tenant lo da la
        RLS/filtro app-level del adaptador (un ticket de otro tenant nunca llega a esta capa)."""
        return await self._get_or_raise(ticket_id)

    async def list_tickets(
        self,
        tenant_id: uuid.UUID,
        *,
        page: int,
        page_size: int,
        status: TicketStatus | None = None,
        priority: TicketPriority | None = None,
        domain: KbDomain | None = None,
        assignee_id: uuid.UUID | None = None,
        sort: str = "-updated_at",
    ) -> PageResult[Ticket]:
        """`GET /tickets` (07): pass-through paginado/filtrado/ordenado al puerto (`sort` YA validado
        por el router contra la whitelist antes de llegar aquí)."""
        return await self._tickets.list(
            tenant_id,
            page=page,
            page_size=page_size,
            status=status,
            priority=priority,
            domain=domain,
            assignee_id=assignee_id,
            sort=sort,
        )

    async def _audit(
        self,
        ticket: Ticket,
        action: str,
        payload: dict[str, object],
        *,
        actor_id: uuid.UUID | None = None,
    ) -> None:
        await self._audit_log.add(
            AuditLogEntry(
                tenant_id=ticket.tenant_id,
                action=action,
                entity_type="ticket",
                entity_id=str(ticket.id),
                payload=payload,
                actor_id=actor_id,
            )
        )

    async def create(
        self,
        tenant_id: uuid.UUID,
        requester_id: uuid.UUID,
        subject: str,
        body: str,
        priority: TicketPriority | None = None,
    ) -> Ticket:
        """Alta: estado inicial `new`; primer mensaje del solicitante `public`; `sla_due` vía
        `SlaPolicy`. `priority` por defecto `normal` (contrato, `POST /tickets`, tarea 07 — la
        prioridad inicial es opcional en el request)."""
        now = self._clock.now()
        initial_priority = priority if priority is not None else _DEFAULT_PRIORITY
        sla_due = self._sla_policy.due_at(initial_priority, now, tenant_id)
        ticket = Ticket(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            subject=subject,
            status=TicketStatus.new,
            priority=initial_priority,
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

    async def transition(
        self,
        ticket_id: uuid.UUID,
        new_status: TicketStatus,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> Ticket:
        """Aplica una transición si es una arista válida; si no, `InvalidTransition` (no muta).

        `actor_id` es opcional (default `None`, sin cambio de comportamiento para los llamantes
        existentes) — quien decide la transición, para el audit log (`None` = "sistema", ninguna
        decisión humana detrás, p.ej. el camino auto de `respond.py`)."""
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
            ticket,
            "ticket.transitioned",
            {"from": previous.value, "to": new_status.value},
            actor_id=actor_id,
        )
        return ticket

    async def reopen(self, ticket_id: uuid.UUID, *, actor_id: uuid.UUID | None = None) -> Ticket:
        """`resolved`/`closed` → `reopened` (estado de reposo real) + recalcula `sla_due` vía
        `SlaPolicy`. `actor_id`: el `Subject` que decide reabrir (opcional, default `None`)."""
        ticket = await self.transition(ticket_id, TicketStatus.reopened, actor_id=actor_id)
        ticket.sla_due = self._sla_policy.due_at(
            ticket.priority, self._clock.now(), ticket.tenant_id
        )
        await self._tickets.update(ticket)
        return ticket

    async def advance_to(
        self,
        ticket_id: uuid.UUID,
        target: TicketStatus,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> Ticket:
        """Encadena transiciones válidas desde el estado ACTUAL del ticket hasta `target`, recorriendo
        `_VALID_TRANSITIONS` (BFS con visitados — el grafo tiene ciclos reales, p.ej.
        `open→pending→resolved→reopened→open`; sin marcar visitados un destino inalcanzable podría no
        terminar). Semánticas (decisión de `scenario-coverage`, plan `auto-resolve-ticket`):

        - Si el ticket YA está en `target`: no-op, no propaga `InvalidTransition` — necesario para que
          `approval_service.decide()` no cambie de comportamiento ante una segunda decisión con el
          ticket ya en `pending`.
        - Si no hay ningún camino de aristas válidas hasta `target`: `InvalidTransition`.
        - Si un salto intermedio falla (excepción de `self._tickets.update()` o de infra): el ticket
          queda en el ÚLTIMO estado alcanzado con éxito — no revierte, no unit-of-work cross-repo
          (mismo criterio ya aceptado en `approval_service.py`).
        """
        ticket = await self._get_or_raise(ticket_id)
        if ticket.status is target:
            return ticket

        path = _shortest_path(ticket.status, target)
        if path is None:
            raise InvalidTransition(
                f"sin camino válido: {ticket.status.value} → {target.value}",
                code="ticket.invalid_transition",
                details={"from": ticket.status.value, "to": target.value},
            )

        current = ticket
        for hop in path:
            current = await self.transition(ticket_id, hop, actor_id=actor_id)
        return current

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

    async def update_fields(
        self,
        ticket_id: uuid.UUID,
        *,
        subject: str | None = None,
        priority: TicketPriority | None = None,
        category: str | None = None,
    ) -> Ticket:
        """`PATCH` parcial: solo muta los campos NO-`None` pasados — no reimplementa la máquina de
        estados (`status` sigue siendo exclusivo de `transition`) ni el CSAT (`set_csat`, con su
        propia validación de rango)."""
        ticket = await self._get_or_raise(ticket_id)
        changes: dict[str, object] = {}
        if subject is not None:
            ticket.subject = subject
            changes["subject"] = subject
        if priority is not None:
            ticket.priority = priority
            changes["priority"] = priority.value
        if category is not None:
            ticket.category = category
            changes["category"] = category
        if not changes:
            return ticket
        await self._tickets.update(ticket)
        await self._audit(ticket, "ticket.updated", changes)
        return ticket
