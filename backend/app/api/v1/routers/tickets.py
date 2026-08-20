"""app.api.v1.routers.tickets — endpoints de tickets (contrato 06/07).

Primer router de NEGOCIO (tabla con RLS real, a diferencia de identidad/admin). `sort` se valida
contra `TICKET_SORT_FIELDS` AQUÍ, antes de llamar al repo (422 si no está en la whitelist — nunca se
interpola un string arbitrario en SQL). Aislamiento cross-tenant de `GET/PATCH /tickets/{id}` lo da la
RLS + el filtro app-level del adaptador, sin lógica extra en el router (un ticket de otro tenant es
invisible para la sesión, no un caso especial a programar).

`PATCH /tickets/{id}` se protege con `ticket.update` (capacidad nueva de esta tarea, `rbac.md`):
ningún rol del catálogo la concede sin `ticket.read`, así que basta una capacidad, no dos.

`assign_ticket` cierra FR-038 (tarea 12): tras asignar con éxito, notifica al nuevo `assignee_id` — la
resta de conjuntos `{assignee_id} - {subject.id, None}` cubre autoasignación y desasignación sin `if`
ad-hoc (ambas dan un conjunto vacío de destinatarios). `notification_service.emit()` es best-effort: un
`PortError` se loguea y NO tumba la respuesta 200 ya confirmada (la notificación no es atómica con la
asignación).
"""

import uuid

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.common import Page
from app.api.v1.schemas.tickets import (
    Ticket,
    TicketAssignRequest,
    TicketCreate,
    TicketTransitionRequest,
    TicketUpdate,
)
from app.core.deps import get_notification_service, get_ticket_service, require_capability
from app.domain.entities.business import Ticket as TicketEntity
from app.domain.entities.enums import KbDomain, NotificationType, TicketPriority, TicketStatus
from app.domain.entities.identity import Subject
from app.domain.errors import PortError, Validation
from app.domain.ports.repositories import TICKET_SORT_FIELDS
from app.domain.services.notification_service import NotificationService
from app.domain.services.ticket_service import TicketService
from app.infra.db.repositories import SqlAlchemyUserTenantMembershipRepository

router = APIRouter(prefix="/tickets", tags=["tickets"])

_logger = structlog.get_logger()


def _to_schema(ticket: TicketEntity) -> Ticket:
    return Ticket(
        id=ticket.id,
        tenant_id=ticket.tenant_id,
        subject=ticket.subject,
        status=ticket.status.value,
        priority=ticket.priority.value,
        domain=ticket.domain.value if ticket.domain is not None else None,
        category=ticket.category,
        requester_id=ticket.requester_id,
        assignee_id=ticket.assignee_id,
        sla_due=ticket.sla_due,
        csat=ticket.csat,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
    )


def _validate_sort(sort: str) -> str:
    if sort.removeprefix("-") not in TICKET_SORT_FIELDS:
        raise Validation(
            f"sort no admitido: {sort}",
            code="ticket.sort_not_allowed",
            details={"field": "sort", "message": f"sort no admitido: {sort}"},
        )
    return sort


def _parse_priority(value: str | None) -> TicketPriority | None:
    """`str` de un `TicketCreate`/`TicketUpdate` → `TicketPriority`, o `Validation` (422) — nunca un
    `ValueError` crudo (500) por un valor que no es del enum."""
    if value is None:
        return None
    try:
        return TicketPriority(value)
    except ValueError as exc:
        raise Validation(
            f"priority no admitida: {value}",
            code="ticket.invalid_priority",
            details={"field": "priority", "message": f"priority no admitida: {value}"},
        ) from exc


def _parse_status(value: str) -> TicketStatus:
    try:
        return TicketStatus(value)
    except ValueError as exc:
        raise Validation(
            f"status no admitido: {value}",
            code="ticket.invalid_status",
            details={"field": "status", "message": f"status no admitido: {value}"},
        ) from exc


@router.get("")
async def list_tickets(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: TicketStatus | None = Query(None),
    priority: TicketPriority | None = Query(None),
    domain: KbDomain | None = Query(None),
    assignee_id: uuid.UUID | None = Query(None),
    sort: str = Query("-updated_at"),
    subject_session: tuple[Subject, AsyncSession] = Depends(require_capability("ticket.read")),
    ticket_service: TicketService = Depends(get_ticket_service),
) -> Page[Ticket]:
    subject, _session = subject_session
    _validate_sort(sort)
    result = await ticket_service.list_tickets(
        subject.tenant_id,
        page=page,
        page_size=page_size,
        status=status,
        priority=priority,
        domain=domain,
        assignee_id=assignee_id,
        sort=sort,
    )
    return Page(
        items=[_to_schema(t) for t in result.items],
        page=page,
        page_size=page_size,
        total=result.total,
    )


@router.post("", status_code=201)
async def create_ticket(
    payload: TicketCreate,
    subject_session: tuple[Subject, AsyncSession] = Depends(require_capability("ticket.create")),
    ticket_service: TicketService = Depends(get_ticket_service),
) -> Ticket:
    subject, _session = subject_session
    priority = _parse_priority(payload.priority)
    ticket = await ticket_service.create(
        tenant_id=subject.tenant_id,
        requester_id=subject.id,
        subject=payload.subject,
        body=payload.body,
        priority=priority,
    )
    return _to_schema(ticket)


@router.get("/{id}")
async def get_ticket(
    id: uuid.UUID,
    subject_session: tuple[Subject, AsyncSession] = Depends(require_capability("ticket.read")),
    ticket_service: TicketService = Depends(get_ticket_service),
) -> Ticket:
    _subject, _session = subject_session
    ticket = await ticket_service.get(id)
    return _to_schema(ticket)


@router.patch("/{id}")
async def update_ticket(
    id: uuid.UUID,
    payload: TicketUpdate,
    subject_session: tuple[Subject, AsyncSession] = Depends(require_capability("ticket.update")),
    ticket_service: TicketService = Depends(get_ticket_service),
) -> Ticket:
    _subject, _session = subject_session
    ticket = None
    if payload.subject is not None or payload.priority is not None or payload.category is not None:
        priority = _parse_priority(payload.priority)
        ticket = await ticket_service.update_fields(
            id, subject=payload.subject, priority=priority, category=payload.category
        )
    if payload.csat is not None:
        ticket = await ticket_service.set_csat(id, payload.csat)
    if ticket is None:
        ticket = await ticket_service.get(id)
    return _to_schema(ticket)


@router.post("/{id}/transition")
async def transition_ticket(
    id: uuid.UUID,
    payload: TicketTransitionRequest,
    subject_session: tuple[Subject, AsyncSession] = Depends(
        require_capability("ticket.transition")
    ),
    ticket_service: TicketService = Depends(get_ticket_service),
) -> Ticket:
    _subject, _session = subject_session
    ticket = await ticket_service.transition(id, _parse_status(payload.status))
    return _to_schema(ticket)


@router.post("/{id}/assign")
async def assign_ticket(
    id: uuid.UUID,
    payload: TicketAssignRequest,
    subject_session: tuple[Subject, AsyncSession] = Depends(require_capability("ticket.assign")),
    ticket_service: TicketService = Depends(get_ticket_service),
    notification_service: NotificationService = Depends(get_notification_service),
) -> Ticket:
    subject, session = subject_session
    assignee_tenant_id: uuid.UUID | None = None
    if payload.assignee_id is not None:
        membership = await SqlAlchemyUserTenantMembershipRepository(session).get(
            payload.assignee_id, subject.tenant_id
        )
        if membership is not None:
            assignee_tenant_id = subject.tenant_id
    ticket = await ticket_service.assign(id, payload.assignee_id, assignee_tenant_id)

    recipients: set[uuid.UUID] = {
        recipient
        for recipient in ({payload.assignee_id} - {subject.id, None})
        if recipient is not None
    }
    for recipient_id in recipients:
        try:
            await notification_service.emit(
                subject.tenant_id,
                recipient_id,
                NotificationType.ticket_assigned,
                {"ticket_id": str(id)},
            )
        except PortError:
            _logger.warning(
                "notification_emit_failed", ticket_id=str(id), recipient_id=str(recipient_id)
            )

    return _to_schema(ticket)
