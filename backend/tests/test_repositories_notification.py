"""Tests de integración de `SqlAlchemyNotificationRepository` (tarea `backend-routers-flujo-ia-03`).

Postgres real vía `superuser_engine` (RLS no aplica). Primer adaptador real de este puerto.
"""

import uuid
from collections.abc import AsyncIterator

import pytest_asyncio
from app.core.security import hash_password
from app.domain.entities.business import Notification
from app.domain.entities.enums import NotificationType, TenantStatus
from app.domain.entities.identity import Tenant, User
from app.infra.db.repositories.notification import SqlAlchemyNotificationRepository
from app.infra.db.repositories.tenant import SqlAlchemyTenantRepository
from app.infra.db.repositories.user import SqlAlchemyUserRepository
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

_TRUNCATE_TABLES = 'TRUNCATE notification, tenant, "user" RESTART IDENTITY CASCADE'


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables(superuser_engine: AsyncEngine) -> AsyncIterator[None]:
    async with superuser_engine.begin() as conn:
        await conn.execute(text(_TRUNCATE_TABLES))
    yield
    async with superuser_engine.begin() as conn:
        await conn.execute(text(_TRUNCATE_TABLES))


@pytest_asyncio.fixture
async def session(superuser_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with async_sessionmaker(superuser_engine, expire_on_commit=False)() as s:
        yield s


async def _make_tenant(session: AsyncSession) -> Tenant:
    return await SqlAlchemyTenantRepository(session).add(
        Tenant(id=uuid.uuid4(), slug=f"t-{uuid.uuid4()}", name="T", status=TenantStatus.active)
    )


async def _make_user(session: AsyncSession) -> User:
    return await SqlAlchemyUserRepository(session).add(
        User(
            id=uuid.uuid4(),
            email=f"u-{uuid.uuid4()}@example.com",
            password_hash=hash_password("pw"),
        )
    )


def _make_notification(
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    notification_type: NotificationType = NotificationType.ticket_assigned,
) -> Notification:
    return Notification(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        type=notification_type,
        payload={"x": 1},
    )


async def test_add_persists_and_get_retrieves_it(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    user = await _make_user(session)
    await session.commit()
    repo = SqlAlchemyNotificationRepository(session)

    notification = await repo.add(_make_notification(tenant_id=tenant.id, user_id=user.id))
    await session.commit()

    fetched = await repo.get(notification.id)
    assert fetched is not None
    assert fetched.id == notification.id
    assert fetched.read_at is None


async def test_get_returns_none_when_missing(session: AsyncSession) -> None:
    repo = SqlAlchemyNotificationRepository(session)
    assert await repo.get(uuid.uuid4()) is None


async def test_list_for_user_orders_most_recent_first(session: AsyncSession) -> None:
    """`now()` es estable dentro de una misma transacción Postgres — cada `add()` se commitea aparte
    para que `created_at` avance de verdad entre ambas filas."""
    tenant = await _make_tenant(session)
    user = await _make_user(session)
    await session.commit()
    repo = SqlAlchemyNotificationRepository(session)
    first = await repo.add(_make_notification(tenant_id=tenant.id, user_id=user.id))
    await session.commit()
    second = await repo.add(_make_notification(tenant_id=tenant.id, user_id=user.id))
    await session.commit()

    result = await repo.list_for_user(user.id, page=1, page_size=20)

    assert [n.id for n in result.items] == [second.id, first.id]
    assert result.total == 2


async def test_list_for_user_returns_an_empty_page_without_any_notification(
    session: AsyncSession,
) -> None:
    repo = SqlAlchemyNotificationRepository(session)
    result = await repo.list_for_user(uuid.uuid4(), page=1, page_size=20)
    assert result.items == []
    assert result.total == 0


async def test_list_for_user_only_returns_that_users_notifications(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    owner = await _make_user(session)
    other = await _make_user(session)
    await session.commit()
    repo = SqlAlchemyNotificationRepository(session)
    mine = await repo.add(_make_notification(tenant_id=tenant.id, user_id=owner.id))
    await repo.add(_make_notification(tenant_id=tenant.id, user_id=other.id))
    await session.commit()

    result = await repo.list_for_user(owner.id, page=1, page_size=20)

    assert [n.id for n in result.items] == [mine.id]


async def test_list_for_user_filters_unread_true(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    user = await _make_user(session)
    await session.commit()
    repo = SqlAlchemyNotificationRepository(session)
    unread_n = await repo.add(_make_notification(tenant_id=tenant.id, user_id=user.id))
    read_n = await repo.add(_make_notification(tenant_id=tenant.id, user_id=user.id))
    await session.commit()
    await repo.mark_read(read_n.id, user.id, unread_n.created_at)
    await session.commit()

    result = await repo.list_for_user(user.id, unread=True, page=1, page_size=20)

    assert [n.id for n in result.items] == [unread_n.id]


async def test_list_for_user_filters_unread_false(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    user = await _make_user(session)
    await session.commit()
    repo = SqlAlchemyNotificationRepository(session)
    await repo.add(_make_notification(tenant_id=tenant.id, user_id=user.id))
    read_n = await repo.add(_make_notification(tenant_id=tenant.id, user_id=user.id))
    await session.commit()
    await repo.mark_read(read_n.id, user.id, read_n.created_at)
    await session.commit()

    result = await repo.list_for_user(user.id, unread=False, page=1, page_size=20)

    assert [n.id for n in result.items] == [read_n.id]


async def test_list_for_user_paginates(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    user = await _make_user(session)
    await session.commit()
    repo = SqlAlchemyNotificationRepository(session)
    for _ in range(25):
        await repo.add(_make_notification(tenant_id=tenant.id, user_id=user.id))
    await session.commit()

    result = await repo.list_for_user(user.id, page=1, page_size=20)

    assert len(result.items) == 20
    assert result.total == 25


async def test_list_for_user_offset_advances_correctly_across_pages(session: AsyncSession) -> None:
    """Mata mutantes aritméticos en el cálculo de `offset` (`(page - 1) * page_size`): con IDs
    deterministas (`created_at` distinto por `commit` separado) y `page_size=2`, comprueba las 3
    páginas exactas de 5 notificaciones — cualquier operador equivocado desplaza el offset y una
    página deja de coincidir con la esperada."""
    tenant = await _make_tenant(session)
    user = await _make_user(session)
    await session.commit()
    repo = SqlAlchemyNotificationRepository(session)
    ids = []
    for _ in range(5):
        n = await repo.add(_make_notification(tenant_id=tenant.id, user_id=user.id))
        await session.commit()
        ids.append(n.id)
    # `ids` en orden de creación (más antigua primero); la lista esperada es -created_at (más
    # reciente primero), es decir `ids` invertida.
    newest_first = list(reversed(ids))

    page_1 = await repo.list_for_user(user.id, page=1, page_size=2)
    page_2 = await repo.list_for_user(user.id, page=2, page_size=2)
    page_3 = await repo.list_for_user(user.id, page=3, page_size=2)

    assert [n.id for n in page_1.items] == newest_first[0:2]
    assert [n.id for n in page_2.items] == newest_first[2:4]
    assert [n.id for n in page_3.items] == newest_first[4:5]


async def test_mark_read_is_idempotent(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    user = await _make_user(session)
    await session.commit()
    repo = SqlAlchemyNotificationRepository(session)
    notification = await repo.add(_make_notification(tenant_id=tenant.id, user_id=user.id))
    await session.commit()

    await repo.mark_read(notification.id, user.id, notification.created_at)
    await repo.mark_read(notification.id, user.id, notification.created_at)
    await session.commit()

    fetched = await repo.get(notification.id)
    assert fetched is not None
    assert fetched.read_at is not None


async def test_mark_read_of_another_users_notification_does_not_affect_it(
    session: AsyncSession,
) -> None:
    tenant = await _make_tenant(session)
    owner = await _make_user(session)
    intruder = await _make_user(session)
    await session.commit()
    repo = SqlAlchemyNotificationRepository(session)
    notification = await repo.add(_make_notification(tenant_id=tenant.id, user_id=owner.id))
    await session.commit()

    await repo.mark_read(notification.id, intruder.id, notification.created_at)
    await session.commit()

    fetched = await repo.get(notification.id)
    assert fetched is not None
    assert fetched.read_at is None


async def test_count_unread(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    user = await _make_user(session)
    await session.commit()
    repo = SqlAlchemyNotificationRepository(session)
    unread_n = await repo.add(_make_notification(tenant_id=tenant.id, user_id=user.id))
    read_n = await repo.add(_make_notification(tenant_id=tenant.id, user_id=user.id))
    await session.commit()
    await repo.mark_read(read_n.id, user.id, unread_n.created_at)
    await session.commit()

    assert await repo.count_unread(user.id) == 1
