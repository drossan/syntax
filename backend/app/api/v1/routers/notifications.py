"""app.api.v1.routers.notifications — notificaciones in-app por HTTP (contrato 06/12).

Sin capacidad dedicada: cualquier subject autenticado accede a SUS PROPIAS notificaciones (nunca las de
otro, nunca un `user_id` de query). Al no haber capacidad que evaluar, el scope de tenant se abre
directamente con `tenant_scope(session, subject.tenant_id)` (sin pasar por `require_capability`/
`get_tenant_context`, que exigen una capacidad concreta). `PATCH /{id}/read` primero resuelve
`notification_service.get(id, subject.id)` (404 si no existe o no es del subject) y SOLO ENTONCES llama
a `mark_read` — ese orden es lo que distingue 404 de 200 idempotente (marcar una ya leída).
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.common import Page
from app.api.v1.schemas.notifications import Notification as NotificationSchema
from app.core.deps import get_current_subject, get_db_session, get_notification_service
from app.domain.entities.business import Notification as NotificationEntity
from app.domain.entities.identity import Subject
from app.domain.services.notification_service import NotificationService
from app.infra.db.session import tenant_scope

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _to_schema(notification: NotificationEntity) -> NotificationSchema:
    return NotificationSchema(
        id=notification.id,
        type=notification.type.value,
        payload=notification.payload,
        read_at=notification.read_at,
        created_at=notification.created_at,
    )


@router.get("")
async def list_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    unread: bool | None = Query(None),
    subject: Subject = Depends(get_current_subject),
    session: AsyncSession = Depends(get_db_session),
    notification_service: NotificationService = Depends(get_notification_service),
) -> Page[NotificationSchema]:
    async with tenant_scope(session, subject.tenant_id):
        result = await notification_service.list_for_user(
            subject.id, unread=unread, page=page, page_size=page_size
        )
    return Page(
        items=[_to_schema(n) for n in result.items],
        page=page,
        page_size=page_size,
        total=result.total,
    )


@router.patch("/{id}/read")
async def mark_notification_read(
    id: uuid.UUID,
    subject: Subject = Depends(get_current_subject),
    session: AsyncSession = Depends(get_db_session),
    notification_service: NotificationService = Depends(get_notification_service),
) -> NotificationSchema:
    async with tenant_scope(session, subject.tenant_id):
        await notification_service.get(id, subject.id)
        await notification_service.mark_read(id, subject.id)
        updated = await notification_service.get(id, subject.id)
    return _to_schema(updated)
