"""app.domain.services.notification_service — notificaciones in-app (FR-038, CU-BE-10).

**Desacoplado**: ningún otro servicio de este plan lo llama (decisión de grilling — la notificación es
*best-effort*, no un acto atómico con lo que la dispara). La orquestación "tras aprobar/asignar, notifica"
es del plan de routers (11/12).
"""

import uuid

from app.domain.entities.business import Notification
from app.domain.entities.enums import NotificationType
from app.domain.ports.clock import Clock
from app.domain.ports.repositories import NotificationRepository


class NotificationService:
    """Emitir/listar/marcar-leída/contar-no-leídas. Puertos por inyección de constructor."""

    def __init__(self, notifications: NotificationRepository, clock: Clock) -> None:
        self._notifications = notifications
        self._clock = clock

    async def emit(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        notification_type: NotificationType,
        payload: dict[str, object],
    ) -> Notification:
        """Crea una notificación no leída para `user_id`."""
        notification = Notification(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            type=notification_type,
            payload=payload,
        )
        return await self._notifications.add(notification)

    async def list_for_user(self, user_id: uuid.UUID) -> list[Notification]:
        """Notificaciones de `user_id`, orden `-created_at` (contrato del puerto). Vacía si no hay."""
        return await self._notifications.list_for_user(user_id)

    async def mark_read(self, notification_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Marca como leída. Idempotente; no-op si no existe o no pertenece a `user_id` (no revela)."""
        await self._notifications.mark_read(notification_id, user_id, self._clock.now())

    async def count_unread(self, user_id: uuid.UUID) -> int:
        """Cuenta de no leídas, derivada de `read_at IS NULL` (data-model.md RN-2)."""
        return await self._notifications.count_unread(user_id)
