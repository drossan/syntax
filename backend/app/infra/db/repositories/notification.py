"""app.infra.db.repositories.notification — adaptador SQLAlchemy de `NotificationRepository` (tarea 12).

Primer adaptador real de este puerto (nacido en `domain-services`, sin implementación hasta ahora).
`list_for_user` filtra `unread` vía `read_at IS NULL`/`IS NOT NULL` y pagina; orden `-created_at`
(contrato del puerto). `mark_read`/`count_unread` mismo patrón que el resto de adaptadores.
"""

import uuid
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.business import Notification
from app.domain.entities.enums import NotificationType
from app.domain.errors import PortError
from app.domain.ports.repositories import PageResult
from app.infra.db.models import Notification as NotificationModel
from app.infra.db.models.enums import NotificationType as NotificationTypeOrm
from app.infra.db.repositories._enum_bridge import to_domain, to_orm


def _to_domain(row: NotificationModel) -> Notification:
    return Notification(
        id=row.id,
        tenant_id=row.tenant_id,
        user_id=row.user_id,
        type=to_domain(NotificationType, row.type),
        payload=row.payload,
        read_at=row.read_at,
        created_at=row.created_at,
    )


class SqlAlchemyNotificationRepository:
    """Adaptador de `NotificationRepository` (`app.domain.ports.repositories`)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, notification: Notification) -> Notification:
        row = NotificationModel(
            id=notification.id,
            tenant_id=notification.tenant_id,
            user_id=notification.user_id,
            type=to_orm(NotificationTypeOrm, notification.type),
            payload=notification.payload,
            read_at=notification.read_at,
        )
        self._session.add(row)
        try:
            await self._session.flush()
        except Exception as exc:
            raise PortError("fallo al crear notification") from exc
        return _to_domain(row)

    async def get(self, notification_id: uuid.UUID) -> Notification | None:
        try:
            row = await self._session.get(NotificationModel, notification_id)
        except Exception as exc:
            raise PortError("fallo al leer notification") from exc
        return _to_domain(row) if row is not None else None

    async def list_for_user(
        self, user_id: uuid.UUID, *, unread: bool | None = None, page: int, page_size: int
    ) -> PageResult[Notification]:
        conditions = [NotificationModel.user_id == user_id]
        if unread is True:
            conditions.append(NotificationModel.read_at.is_(None))
        elif unread is False:
            conditions.append(NotificationModel.read_at.is_not(None))
        offset = (page - 1) * page_size
        try:
            total = (
                await self._session.execute(
                    select(func.count()).select_from(NotificationModel).where(*conditions)
                )
            ).scalar_one()
            rows = (
                await self._session.execute(
                    select(NotificationModel)
                    .where(*conditions)
                    .order_by(NotificationModel.created_at.desc())
                    .offset(offset)
                    .limit(page_size)
                )
            ).scalars()
            items = [_to_domain(row) for row in rows]
        except Exception as exc:
            raise PortError("fallo al listar notification") from exc
        return PageResult(items=items, total=total)

    async def mark_read(
        self, notification_id: uuid.UUID, user_id: uuid.UUID, read_at: datetime
    ) -> None:
        try:
            await self._session.execute(
                update(NotificationModel)
                .where(
                    NotificationModel.id == notification_id,
                    NotificationModel.user_id == user_id,
                    NotificationModel.read_at.is_(None),
                )
                .values(read_at=read_at)
            )
        except Exception as exc:
            raise PortError("fallo al marcar notification como leída") from exc

    async def count_unread(self, user_id: uuid.UUID) -> int:
        try:
            return (
                await self._session.execute(
                    select(func.count())
                    .select_from(NotificationModel)
                    .where(
                        NotificationModel.user_id == user_id, NotificationModel.read_at.is_(None)
                    )
                )
            ).scalar_one()
        except Exception as exc:
            raise PortError("fallo al contar notification no leídas") from exc
