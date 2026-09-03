"""app.api.v1.routers.messages — mensajes de ticket + adjuntos (contrato 06/08).

La capacidad de escritura depende del `visibility` del mensaje (`ticket.reply` para `public`,
`note.internal.write` para `internal`), decidido en RUNTIME por el payload/mensaje — no es fija como
en el resto de routers, así que no se puede declarar con `Depends(require_capability(...))` (capacidad
fija en tiempo de definición). En su lugar: se abre el scope con `ticket.read` (TODO rol que escribe
mensajes también lee tickets, `rbac.md`) y se comprueba la capacidad de escritura/lectura específica a
mano contra `subject.capabilities`, lanzando `AuthorizationDenied` igual que `require_capability`.

Adjuntos: el binario vive fuera de Postgres (puerto `Storage`, filesystem local en esta fase). Un
fichero de 0 bytes se ACEPTA (adjunto vacío válido, decisión explícita — no un 500 ni un rechazo sin
justificar). El límite de tamaño (`settings.max_upload_bytes`) se aplica leyendo el `UploadFile` antes
de tocar `Storage.save` — por encima, 413 vía `fastapi.HTTPException` directa (no hay ninguna
`DomainError` para "payload demasiado grande", y el proyecto ya soporta ese patrón en `app.core.deps`).
`Message.attachments` (contrato ampliado esta tarea) es lo que hace DESCUBRIBLE lo ya subido: antes
solo se podía subir y descargar-si-ya-sabes-el-id, sin ninguna forma de listar — `list_messages` los
trae en UNA consulta por página (`list_by_messages`, evita N+1) en vez de uno por mensaje.

`create_message` cierra FR-038 (tarea 12) para mensajes `public`: notifica a `{ticket.requester_id,
ticket.assignee_id} - {subject.id, None}` (resta de conjuntos, sin `if` ad-hoc — cubre autor=assignee,
autor=requester y un tercer agente que notifica a ambos). Mensajes `internal` no notifican.
`notification_service.emit()` es best-effort: un `PortError` se loguea y no tumba el 201 ya confirmado.
"""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AuthorizationDenied
from app.api.v1.schemas.common import Page
from app.api.v1.schemas.messages import Attachment as AttachmentSchema
from app.api.v1.schemas.messages import Message as MessageSchema
from app.api.v1.schemas.messages import MessageCreate
from app.core.config import Settings, get_settings
from app.core.deps import (
    get_current_subject,
    get_db_session,
    get_notification_service,
    get_storage,
    get_tenant_context,
    get_ticket_service,
    require_capability,
)
from app.domain.entities.business import Attachment as AttachmentEntity
from app.domain.entities.business import Message as MessageEntity
from app.domain.entities.enums import MessageVisibility, NotificationType
from app.domain.entities.identity import Subject
from app.domain.errors import NotFound, PortError, Validation
from app.domain.ports.storage import Storage
from app.domain.services.notification_service import NotificationService
from app.domain.services.rbac_service import Deny, DenyReason
from app.domain.services.ticket_service import TicketService
from app.infra.db.repositories import SqlAlchemyMessageRepository, SqlAlchemyUserRepository

router = APIRouter(tags=["messages"])

_READ_CAPABILITY = "ticket.read"
_INTERNAL_READ_CAPABILITY = "note.internal.read"

_logger = structlog.get_logger()


def _to_message_schema(
    message: MessageEntity,
    attachments: list[AttachmentEntity] | None = None,
    *,
    author_email: str | None = None,
) -> MessageSchema:
    return MessageSchema(
        id=message.id,
        ticket_id=message.ticket_id,
        author_id=message.author_id,
        author_email=author_email,
        visibility=message.visibility.value,
        is_ai_draft=message.is_ai_draft,
        body=message.body,
        created_at=message.created_at,
        attachments=[_to_attachment_schema(a) for a in (attachments or [])],
    )


def _to_attachment_schema(attachment: AttachmentEntity) -> AttachmentSchema:
    return AttachmentSchema(
        id=attachment.id,
        message_id=attachment.message_id,
        filename=attachment.filename,
        content_type=attachment.content_type,
        size_bytes=attachment.size_bytes,
    )


def _parse_visibility(value: str) -> MessageVisibility:
    try:
        return MessageVisibility(value)
    except ValueError as exc:
        raise Validation(
            f"visibility no admitida: {value}",
            code="message.invalid_visibility",
            details={"field": "visibility", "message": f"visibility no admitida: {value}"},
        ) from exc


def _capability_for_visibility(visibility: MessageVisibility) -> str:
    return "note.internal.write" if visibility is MessageVisibility.internal else "ticket.reply"


def _has_capability(subject: Subject, capability: str) -> bool:
    return (capability, "tenant") in subject.capabilities or (
        capability,
        "global",
    ) in subject.capabilities


def _require_capability(subject: Subject, capability: str) -> None:
    if not _has_capability(subject, capability):
        raise AuthorizationDenied(Deny(DenyReason.no_capability))


@router.get("/tickets/{id}/messages")
async def list_messages(
    id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    subject_session: tuple[Subject, AsyncSession] = Depends(require_capability(_READ_CAPABILITY)),
    ticket_service: TicketService = Depends(get_ticket_service),
) -> Page[MessageSchema]:
    subject, session = subject_session
    await ticket_service.get(id)
    visibilities = (
        None if _has_capability(subject, _INTERNAL_READ_CAPABILITY) else [MessageVisibility.public]
    )
    message_repo = SqlAlchemyMessageRepository(session)
    result = await message_repo.list_by_ticket(
        id, page=page, page_size=page_size, visibilities=visibilities
    )
    attachments_by_message = await message_repo.list_by_messages([m.id for m in result.items])
    author_ids = {m.author_id for m in result.items if m.author_id is not None}
    users = await SqlAlchemyUserRepository(session).list_by_ids(list(author_ids))
    email_by_author_id = {user.id: user.email for user in users}
    return Page(
        items=[
            _to_message_schema(
                m,
                attachments_by_message.get(m.id, []),
                author_email=email_by_author_id.get(m.author_id) if m.author_id else None,
            )
            for m in result.items
        ],
        page=page,
        page_size=page_size,
        total=result.total,
    )


@router.post("/tickets/{id}/messages", status_code=201)
async def create_message(
    id: uuid.UUID,
    payload: MessageCreate,
    subject: Subject = Depends(get_current_subject),
    session: AsyncSession = Depends(get_db_session),
    ticket_service: TicketService = Depends(get_ticket_service),
    notification_service: NotificationService = Depends(get_notification_service),
) -> MessageSchema:
    visibility = _parse_visibility(payload.visibility)
    async with get_tenant_context(session, subject, _capability_for_visibility(visibility)):
        ticket = await ticket_service.get(id)
        message = await SqlAlchemyMessageRepository(session).add(
            MessageEntity(
                id=uuid.uuid4(),
                tenant_id=subject.tenant_id,
                ticket_id=id,
                author_id=subject.id,
                visibility=visibility,
                body=payload.body,
            )
        )
        if visibility is MessageVisibility.public:
            recipients: set[uuid.UUID] = {
                recipient
                for recipient in ({ticket.requester_id, ticket.assignee_id} - {subject.id, None})
                if recipient is not None
            }
            for recipient_id in recipients:
                try:
                    await notification_service.emit(
                        subject.tenant_id,
                        recipient_id,
                        NotificationType.ticket_reply,
                        {"ticket_id": str(id)},
                    )
                except PortError:
                    _logger.warning(
                        "notification_emit_failed",
                        ticket_id=str(id),
                        recipient_id=str(recipient_id),
                    )
        author = await SqlAlchemyUserRepository(session).get(subject.id)
    return _to_message_schema(message, author_email=author.email if author is not None else None)


@router.post("/messages/{id}/attachments", status_code=201)
async def upload_attachment(
    id: uuid.UUID,
    file: UploadFile,
    subject: Subject = Depends(get_current_subject),
    session: AsyncSession = Depends(get_db_session),
    storage: Storage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
) -> AttachmentSchema:
    async with get_tenant_context(session, subject, _READ_CAPABILITY):
        message_repo = SqlAlchemyMessageRepository(session)
        message = await message_repo.get(id)
        if message is None:
            raise NotFound(f"message {id} no existe", code="message.not_found")
        _require_capability(subject, _capability_for_visibility(message.visibility))

        content = await file.read()
        if len(content) > settings.max_upload_bytes:
            raise HTTPException(status_code=413)

        attachment_id = uuid.uuid4()
        filename = file.filename or "unnamed"
        content_type = file.content_type or "application/octet-stream"
        key = f"{subject.tenant_id}/{message.id}/{attachment_id}-{filename}"
        await storage.save(key, content, content_type)
        attachment = await message_repo.add_attachment(
            AttachmentEntity(
                id=attachment_id,
                tenant_id=subject.tenant_id,
                message_id=message.id,
                filename=filename,
                content_type=content_type,
                size_bytes=len(content),
                storage_key=key,
            )
        )
    return _to_attachment_schema(attachment)


@router.get("/messages/{id}/attachments/{attachment_id}")
async def download_attachment(
    id: uuid.UUID,
    attachment_id: uuid.UUID,
    subject: Subject = Depends(get_current_subject),
    session: AsyncSession = Depends(get_db_session),
    storage: Storage = Depends(get_storage),
) -> FileResponse:
    async with get_tenant_context(session, subject, _READ_CAPABILITY):
        message_repo = SqlAlchemyMessageRepository(session)
        message = await message_repo.get(id)
        if message is None:
            raise NotFound(f"message {id} no existe", code="message.not_found")
        if message.visibility is MessageVisibility.internal:
            _require_capability(subject, _INTERNAL_READ_CAPABILITY)
        attachment = await message_repo.get_attachment(attachment_id)
        if attachment is None or attachment.message_id != message.id:
            raise NotFound(f"attachment {attachment_id} no existe", code="attachment.not_found")
        path = await storage.get_url_or_path(attachment.storage_key)
        content_type = attachment.content_type
        filename = attachment.filename
    return FileResponse(path, media_type=content_type, filename=filename)
