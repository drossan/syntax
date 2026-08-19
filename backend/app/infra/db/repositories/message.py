"""app.infra.db.repositories.message — adaptador SQLAlchemy de `MessageRepository`.

Solo `add`/`list_by_ticket` (el contrato completo del puerto hoy) — necesario para que
`TicketService.create` (tarea 07) persista el primer mensaje del ticket. Adjuntos/`Storage` y el
router `messages` son la tarea 08; este adaptador se amplía ahí si el puerto lo necesita.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.business import Message
from app.domain.entities.enums import MessageVisibility
from app.domain.errors import PortError
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

    async def list_by_ticket(self, ticket_id: uuid.UUID) -> list[Message]:
        try:
            rows = (
                await self._session.execute(
                    select(MessageModel)
                    .where(MessageModel.ticket_id == ticket_id)
                    .order_by(MessageModel.created_at)
                )
            ).scalars()
        except Exception as exc:
            raise PortError("fallo al listar messages") from exc
        return [_to_domain(row) for row in rows]
