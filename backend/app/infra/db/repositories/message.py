"""app.infra.db.repositories.message — adaptador SQLAlchemy de `MessageRepository`.

`add`/`list_by_ticket` (mensajes) desde la tarea 07; `add_attachment`/`get_attachment` (tarea 08) —
solo el metadato del adjunto, el binario vive fuera de Postgres vía el puerto `Storage`.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.business import Attachment, Message
from app.domain.entities.enums import MessageVisibility
from app.domain.errors import PortError
from app.domain.ports.repositories import PageResult
from app.infra.db.models import Attachment as AttachmentModel
from app.infra.db.models import Message as MessageModel
from app.infra.db.models.enums import MessageVisibility as MessageVisibilityOrm
from app.infra.db.repositories._enum_bridge import to_domain, to_orm


def _to_domain(row: MessageModel) -> Message:
    return Message(
        id=row.id,
        tenant_id=row.tenant_id,
        ticket_id=row.ticket_id,
        author_id=row.author_id,
        visibility=to_domain(MessageVisibility, row.visibility),
        is_ai_draft=row.is_ai_draft,
        body=row.body,
        created_at=row.created_at,
    )


def _attachment_to_domain(row: AttachmentModel) -> Attachment:
    return Attachment(
        id=row.id,
        tenant_id=row.tenant_id,
        message_id=row.message_id,
        filename=row.filename,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        storage_key=row.storage_key,
        created_at=row.created_at,
    )


class SqlAlchemyMessageRepository:
    """Adaptador de `MessageRepository` (`app.domain.ports.repositories`)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, message: Message) -> Message:
        row = MessageModel(
            id=message.id,
            tenant_id=message.tenant_id,
            ticket_id=message.ticket_id,
            author_id=message.author_id,
            visibility=to_orm(MessageVisibilityOrm, message.visibility),
            is_ai_draft=message.is_ai_draft,
            body=message.body,
        )
        self._session.add(row)
        try:
            await self._session.flush()
        except Exception as exc:
            raise PortError("fallo al crear message") from exc
        return _to_domain(row)

    async def get(self, message_id: uuid.UUID) -> Message | None:
        try:
            row = await self._session.get(MessageModel, message_id)
        except Exception as exc:
            raise PortError("fallo al leer message") from exc
        return _to_domain(row) if row is not None else None

    async def list_by_ticket(
        self,
        ticket_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 20,
        visibilities: list[MessageVisibility] | None = None,
    ) -> PageResult[Message]:
        conditions = [MessageModel.ticket_id == ticket_id]
        if visibilities is not None:
            orm_visibilities = [to_orm(MessageVisibilityOrm, v) for v in visibilities]
            conditions.append(MessageModel.visibility.in_(orm_visibilities))
        offset = (page - 1) * page_size
        try:
            total = (
                await self._session.execute(
                    select(func.count()).select_from(MessageModel).where(*conditions)
                )
            ).scalar_one()
            rows = (
                await self._session.execute(
                    select(MessageModel)
                    .where(*conditions)
                    .order_by(MessageModel.created_at)
                    .offset(offset)
                    .limit(page_size)
                )
            ).scalars()
            items = [_to_domain(row) for row in rows]
        except Exception as exc:
            raise PortError("fallo al listar messages") from exc
        return PageResult(items=items, total=total)

    async def add_attachment(self, attachment: Attachment) -> Attachment:
        row = AttachmentModel(
            id=attachment.id,
            tenant_id=attachment.tenant_id,
            message_id=attachment.message_id,
            filename=attachment.filename,
            content_type=attachment.content_type,
            size_bytes=attachment.size_bytes,
            storage_key=attachment.storage_key,
        )
        self._session.add(row)
        try:
            await self._session.flush()
        except Exception as exc:
            raise PortError("fallo al crear attachment") from exc
        return _attachment_to_domain(row)

    async def get_attachment(self, attachment_id: uuid.UUID) -> Attachment | None:
        try:
            row = await self._session.get(AttachmentModel, attachment_id)
        except Exception as exc:
            raise PortError("fallo al leer attachment") from exc
        return _attachment_to_domain(row) if row is not None else None
