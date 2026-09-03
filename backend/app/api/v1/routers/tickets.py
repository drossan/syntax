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

`create_ticket` + `tenant.ai_auto_draft`: el disparo del draft IA corre en `BackgroundTasks`, NUNCA
`await`eado dentro del handler — medido en vivo, el ciclo real `classify→retrieve→grade→generate→
decide` contra OpenAI tarda **~10s**; esperarlo aquí dejaría "crear un ticket" colgado ese tiempo por
cada ticket. La tarea de fondo abre su PROPIA sesión (`get_sessionmaker()` + `tenant_scope`, no la del
request — ya cerrada cuando esto corre) y reconstruye a mano la misma cadena de dependencias que
`get_agent_service` (todas son funciones planas con `Depends(...)` como default inerte fuera de
FastAPI — llamarlas directo con argumentos explícitos es válido y no duplica la lógica de ensamblado).
"""

import uuid

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.common import Page
from app.api.v1.schemas.tickets import (
    Ticket,
    TicketAssignRequest,
    TicketCreate,
    TicketTransitionRequest,
    TicketUpdate,
)
from app.core.config import get_settings
from app.core.deps import (
    get_agent_service,
    get_chat_model_port,
    get_embeddings_port,
    get_notification_service,
    get_retriever_port,
    get_ticket_service,
    require_capability,
)
from app.domain.entities.business import Ticket as TicketEntity
from app.domain.entities.enums import KbDomain, NotificationType, TicketPriority, TicketStatus
from app.domain.entities.identity import Subject
from app.domain.errors import DomainError, PortError, Validation
from app.domain.ports.repositories import TICKET_SORT_FIELDS
from app.domain.services.notification_service import NotificationService
from app.domain.services.ticket_service import TicketService
from app.infra.db.repositories import (
    SqlAlchemyTenantRepository,
    SqlAlchemyUserRepository,
    SqlAlchemyUserTenantMembershipRepository,
)
from app.infra.db.session import get_sessionmaker, tenant_scope

router = APIRouter(prefix="/tickets", tags=["tickets"])

_logger = structlog.get_logger()


async def _trigger_ai_draft_in_background(tenant_id: uuid.UUID, ticket_id: uuid.UUID) -> None:
    """Dispara `agent.trigger` FUERA del ciclo request/response — ver docstring del módulo. Best-effort
    (mismo criterio que la notificación de `assign_ticket`): un `DomainError` (rate-limit, proveedor
    caído) se loguea; ya no hay ninguna respuesta HTTP a la que afectar."""
    settings = get_settings()
    try:
        async with get_sessionmaker()() as session, tenant_scope(session, tenant_id):
            chat_model = get_chat_model_port(settings=settings)
            embeddings = get_embeddings_port(settings=settings)
            retriever = get_retriever_port(
                session=session, settings=settings, embeddings=embeddings
            )
            agent_service = get_agent_service(
                session=session, settings=settings, chat_model=chat_model, retriever=retriever
            )
            await agent_service.trigger(tenant_id, ticket_id)
    except DomainError:
        _logger.warning("ai_auto_draft_trigger_failed", ticket_id=str(ticket_id))


def _to_schema(ticket: TicketEntity, *, assignee_email: str | None = None) -> Ticket:
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
        assignee_email=assignee_email,
        sla_due=ticket.sla_due,
        csat=ticket.csat,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
    )


async def _assignee_email(session: AsyncSession, ticket: TicketEntity) -> str | None:
    """Resuelve el email del responsable actual -- `None` si no hay `assignee_id` o si el usuario ya
    no existe. Una consulta por ticket individual (`get`); `list_tickets` usa `list_by_ids` en lote."""
    if ticket.assignee_id is None:
        return None
    user = await SqlAlchemyUserRepository(session).get(ticket.assignee_id)
    return user.email if user is not None else None


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
    subject, session = subject_session
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
    assignee_ids = {t.assignee_id for t in result.items if t.assignee_id is not None}
    users = await SqlAlchemyUserRepository(session).list_by_ids(list(assignee_ids))
    email_by_assignee_id = {user.id: user.email for user in users}
    return Page(
        items=[
            _to_schema(
                t, assignee_email=email_by_assignee_id.get(t.assignee_id) if t.assignee_id else None
            )
            for t in result.items
        ],
        page=page,
        page_size=page_size,
        total=result.total,
    )


@router.post("", status_code=201)
async def create_ticket(
    payload: TicketCreate,
    background_tasks: BackgroundTasks,
    subject_session: tuple[Subject, AsyncSession] = Depends(require_capability("ticket.create")),
    ticket_service: TicketService = Depends(get_ticket_service),
) -> Ticket:
    subject, session = subject_session
    priority = _parse_priority(payload.priority)
    ticket = await ticket_service.create(
        tenant_id=subject.tenant_id,
        requester_id=subject.id,
        subject=payload.subject,
        body=payload.body,
        priority=priority,
    )

    tenant = await SqlAlchemyTenantRepository(session).get(subject.tenant_id)
    if tenant is not None and tenant.ai_auto_draft:
        # Commit EXPLÍCITO aquí (no basta esperar al de `get_db_session` al final del request):
        # `_trigger_ai_draft_in_background` abre su PROPIA sesión/conexión — reproducido en vivo, sin
        # este commit ve el ticket como inexistente (`NotFound`) porque la transacción de ESTA sesión
        # (la del request) todavía no era visible para otra conexión cuando el background task corrió
        # (`BackgroundTasks` de Starlette se ejecuta ANTES del commit de salida de `get_db_session`).
        await session.commit()
        # En background: ver docstring del módulo — el ciclo real de OpenAI (~10s+) no debe
        # bloquear esta respuesta.
        background_tasks.add_task(_trigger_ai_draft_in_background, subject.tenant_id, ticket.id)

    return _to_schema(ticket)


@router.get("/{id}")
async def get_ticket(
    id: uuid.UUID,
    subject_session: tuple[Subject, AsyncSession] = Depends(require_capability("ticket.read")),
    ticket_service: TicketService = Depends(get_ticket_service),
) -> Ticket:
    _subject, session = subject_session
    ticket = await ticket_service.get(id)
    return _to_schema(ticket, assignee_email=await _assignee_email(session, ticket))


@router.patch("/{id}")
async def update_ticket(
    id: uuid.UUID,
    payload: TicketUpdate,
    subject_session: tuple[Subject, AsyncSession] = Depends(require_capability("ticket.update")),
    ticket_service: TicketService = Depends(get_ticket_service),
) -> Ticket:
    _subject, session = subject_session
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
    return _to_schema(ticket, assignee_email=await _assignee_email(session, ticket))


@router.post("/{id}/transition")
async def transition_ticket(
    id: uuid.UUID,
    payload: TicketTransitionRequest,
    subject_session: tuple[Subject, AsyncSession] = Depends(
        require_capability("ticket.transition")
    ),
    ticket_service: TicketService = Depends(get_ticket_service),
) -> Ticket:
    _subject, session = subject_session
    ticket = await ticket_service.transition(id, _parse_status(payload.status))
    return _to_schema(ticket, assignee_email=await _assignee_email(session, ticket))


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

    return _to_schema(ticket, assignee_email=await _assignee_email(session, ticket))


@router.post("/{id}/reopen")
async def reopen_ticket(
    id: uuid.UUID,
    subject_session: tuple[Subject, AsyncSession] = Depends(require_capability("ticket.reopen")),
    ticket_service: TicketService = Depends(get_ticket_service),
) -> Ticket:
    """`resolved/closed → reopened` (CU-BE-06 4e-4g). Capacidad DEDICADA, distinta de
    `ticket.transition`: acotada por `TicketService.reopen()` a ese único destino — ningún otro
    salto es alcanzable con ella (endpoint separado de `POST /{id}/transition` a propósito). El
    `actor_id` del audit log es el `Subject` real que decide reabrir (a diferencia del camino auto de
    `respond.py`, que usa `actor_id=None`)."""
    subject, session = subject_session
    ticket = await ticket_service.reopen(id, actor_id=subject.id)
    return _to_schema(ticket, assignee_email=await _assignee_email(session, ticket))
