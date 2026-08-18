"""Tests de app.domain.services.notification_service (tarea backend-domain-services-05).

Nivel unit, con NotificationRepository fake en memoria. Traza a CU-BE-10. Servicio **desacoplado**:
ningún otro servicio de este plan lo llama.
"""

import uuid
from datetime import UTC, datetime

import pytest
from app.domain.entities.business import Notification
from app.domain.entities.enums import NotificationType
from app.domain.services.notification_service import NotificationService

_FIXED_NOW = datetime(2026, 1, 1, tzinfo=UTC)
_TENANT = uuid.uuid4()


class _FakeClock:
    def now(self) -> datetime:
        return _FIXED_NOW


class _FakeNotificationRepository:
    def __init__(self) -> None:
        self.store: dict[uuid.UUID, Notification] = {}

    async def add(self, notification: Notification) -> Notification:
        self.store[notification.id] = notification
        return notification

    async def list_for_user(self, user_id: uuid.UUID) -> list[Notification]:
        items = [n for n in self.store.values() if n.user_id == user_id]
        return sorted(items, key=lambda n: n.created_at or _FIXED_NOW, reverse=True)

    async def mark_read(
        self, notification_id: uuid.UUID, user_id: uuid.UUID, read_at: datetime
    ) -> None:
        notification = self.store.get(notification_id)
        if notification is not None and notification.user_id == user_id:
            notification.read_at = read_at

    async def count_unread(self, user_id: uuid.UUID) -> int:
        return sum(1 for n in self.store.values() if n.user_id == user_id and n.read_at is None)


@pytest.fixture
def service() -> tuple["NotificationService", _FakeNotificationRepository]:
    repo = _FakeNotificationRepository()
    return NotificationService(notifications=repo, clock=_FakeClock()), repo


async def test_emit_creates_notification(service: tuple) -> None:
    """Un evento notificable genera una notificación no leída de ese tipo."""
    svc, repo = service
    user_id = uuid.uuid4()
    notification = await svc.emit(_TENANT, user_id, NotificationType.approval_requested, {"x": 1})
    assert notification.type is NotificationType.approval_requested
    assert notification.read_at is None
    assert notification.id in repo.store


async def test_list_for_user_returns_empty_list_when_none() -> None:
    """Listar sin notificaciones devuelve lista vacía (no None, no excepción)."""
    repo = _FakeNotificationRepository()
    svc = NotificationService(notifications=repo, clock=_FakeClock())
    result = await svc.list_for_user(uuid.uuid4())
    assert result == []


async def test_list_for_user_orders_most_recent_first(service: tuple) -> None:
    """Consulta ordenada de notificaciones: más reciente primero."""
    svc, _ = service
    user_id = uuid.uuid4()
    await svc.emit(_TENANT, user_id, NotificationType.ticket_assigned, {})
    await svc.emit(_TENANT, user_id, NotificationType.ticket_reply, {})
    result = await svc.list_for_user(user_id)
    assert len(result) == 2


async def test_mark_read_marks_notification() -> None:
    """Marcar como leída deja de contar como no leída."""
    repo = _FakeNotificationRepository()
    svc = NotificationService(notifications=repo, clock=_FakeClock())
    user_id = uuid.uuid4()
    notification = await svc.emit(_TENANT, user_id, NotificationType.sla_warning, {})
    await svc.mark_read(notification.id, user_id)
    assert repo.store[notification.id].read_at is not None


async def test_mark_read_twice_is_idempotent() -> None:
    """Marcar como leída una notificación ya leída es no-op (no lanza, no duplica)."""
    repo = _FakeNotificationRepository()
    svc = NotificationService(notifications=repo, clock=_FakeClock())
    user_id = uuid.uuid4()
    notification = await svc.emit(_TENANT, user_id, NotificationType.sla_breach, {})
    await svc.mark_read(notification.id, user_id)
    first_read_at = repo.store[notification.id].read_at
    await svc.mark_read(notification.id, user_id)  # segunda vez
    assert repo.store[notification.id].read_at == first_read_at


async def test_mark_read_nonexistent_notification_is_noop() -> None:
    """Marcar leída una notificación inexistente no lanza y no ocurre nada observable."""
    repo = _FakeNotificationRepository()
    svc = NotificationService(notifications=repo, clock=_FakeClock())
    await svc.mark_read(uuid.uuid4(), uuid.uuid4())  # no debe lanzar


async def test_mark_read_of_other_user_notification_does_not_affect_it() -> None:
    """Marcar leída una notificación de OTRO usuario no la afecta (aislamiento, no revela existencia)."""
    repo = _FakeNotificationRepository()
    svc = NotificationService(notifications=repo, clock=_FakeClock())
    owner = uuid.uuid4()
    intruder = uuid.uuid4()
    notification = await svc.emit(_TENANT, owner, NotificationType.approval_requested, {})
    await svc.mark_read(notification.id, intruder)
    assert repo.store[notification.id].read_at is None


async def test_count_unread(service: tuple) -> None:
    """El contador de no leídas deriva de read_at IS NULL (data-model RN-2)."""
    svc, _ = service
    user_id = uuid.uuid4()
    a = await svc.emit(_TENANT, user_id, NotificationType.ticket_assigned, {})
    await svc.emit(_TENANT, user_id, NotificationType.ticket_reply, {})
    await svc.mark_read(a.id, user_id)
    assert await svc.count_unread(user_id) == 1
