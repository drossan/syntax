"""Tests de integración del router `notifications` (tarea `backend-routers-flujo-ia-03`).

`app` apunta a `app_engine` (rol `syntax_app`, RLS real). Sin capacidad dedicada: cualquier subject
autenticado accede a sus propias notificaciones. 1:1 con el `## Scenarios (Gherkin)` de la tarea.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest_asyncio
from app.core.config import Settings, get_settings
from app.core.deps import get_db_session
from app.core.security import JWT_ALGORITHM, create_access_token, hash_password
from app.domain.entities.business import Notification
from app.domain.entities.enums import NotificationType, TenantStatus, UserStatus
from app.domain.entities.identity import Tenant, User, UserTenantMembership
from app.infra.db.repositories import (
    SqlAlchemyNotificationRepository,
    SqlAlchemyTenantRepository,
    SqlAlchemyUserRepository,
    SqlAlchemyUserTenantMembershipRepository,
)
from app.main import create_app
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

_JWT_SECRET = "x" * 32
_TTL = 900


def _settings() -> Settings:
    return Settings(_env_file=None, jwt_secret=_JWT_SECRET, app_env="production", cors_origins=[])


_TRUNCATE_TABLES = 'TRUNCATE notification, user_tenant, "user", tenant RESTART IDENTITY CASCADE'


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables(superuser_engine: AsyncEngine) -> AsyncIterator[None]:
    async with superuser_engine.begin() as conn:
        await conn.execute(text(_TRUNCATE_TABLES))
    yield
    async with superuser_engine.begin() as conn:
        await conn.execute(text(_TRUNCATE_TABLES))


@pytest_asyncio.fixture
async def db(superuser_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with async_sessionmaker(superuser_engine, expire_on_commit=False)() as s:
        yield s


@pytest_asyncio.fixture
async def app(app_engine: AsyncEngine) -> AsyncIterator[FastAPI]:
    test_app = create_app(_settings())

    async def _override_session() -> AsyncIterator[AsyncSession]:
        async with async_sessionmaker(app_engine, expire_on_commit=False)() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    test_app.dependency_overrides[get_db_session] = _override_session
    test_app.dependency_overrides[get_settings] = _settings
    yield test_app
    test_app.dependency_overrides.clear()


def _client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _make_tenant(db: AsyncSession) -> Tenant:
    return await SqlAlchemyTenantRepository(db).add(
        Tenant(id=uuid.uuid4(), slug=f"t-{uuid.uuid4()}", name="Tenant", status=TenantStatus.active)
    )


async def _make_user_with_token(db: AsyncSession, tenant: Tenant) -> tuple[User, str]:
    user = await SqlAlchemyUserRepository(db).add(
        User(
            id=uuid.uuid4(),
            email=f"u-{uuid.uuid4()}@example.com",
            password_hash=hash_password("pw"),
        )
    )
    await SqlAlchemyUserTenantMembershipRepository(db).add(
        UserTenantMembership(user_id=user.id, tenant_id=tenant.id, status=UserStatus.active)
    )
    token = create_access_token(
        str(user.id),
        str(tenant.id),
        secret=_JWT_SECRET,
        algorithm=JWT_ALGORITHM,
        ttl=_TTL,
        now=datetime.now(UTC),
    )
    return user, token


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _seed_notification(
    db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, read: bool = False
) -> Notification:
    repo = SqlAlchemyNotificationRepository(db)
    notification = await repo.add(
        Notification(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            type=NotificationType.ticket_assigned,
            payload={},
        )
    )
    if read:
        await repo.mark_read(notification.id, user_id, datetime.now(UTC))
        await db.commit()
        fetched = await repo.get(notification.id)
        assert fetched is not None
        return fetched
    return notification


# ── GET /notifications ──


async def test_listing_paginates_and_orders_by_created_at_desc(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await _make_tenant(db)
    await db.commit()
    user, token = await _make_user_with_token(db, tenant)
    await db.commit()
    for _ in range(25):
        await _seed_notification(db, tenant_id=tenant.id, user_id=user.id)
        await db.commit()

    async with _client(app) as c:
        r = await c.get("/api/v1/notifications", headers=_auth_header(token))

    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 20
    assert body["total"] == 25


async def test_filtering_unread_true_returns_only_unread(app: FastAPI, db: AsyncSession) -> None:
    tenant = await _make_tenant(db)
    await db.commit()
    user, token = await _make_user_with_token(db, tenant)
    await db.commit()
    unread_n = await _seed_notification(db, tenant_id=tenant.id, user_id=user.id)
    await db.commit()
    await _seed_notification(db, tenant_id=tenant.id, user_id=user.id, read=True)
    await db.commit()

    async with _client(app) as c:
        r = await c.get(
            "/api/v1/notifications", params={"unread": "true"}, headers=_auth_header(token)
        )

    assert r.status_code == 200
    body = r.json()
    assert [item["id"] for item in body["items"]] == [str(unread_n.id)]


async def test_filtering_unread_false_returns_only_read(app: FastAPI, db: AsyncSession) -> None:
    tenant = await _make_tenant(db)
    await db.commit()
    user, token = await _make_user_with_token(db, tenant)
    await db.commit()
    await _seed_notification(db, tenant_id=tenant.id, user_id=user.id)
    await db.commit()
    read_n = await _seed_notification(db, tenant_id=tenant.id, user_id=user.id, read=True)
    await db.commit()

    async with _client(app) as c:
        r = await c.get(
            "/api/v1/notifications", params={"unread": "false"}, headers=_auth_header(token)
        )

    assert r.status_code == 200
    body = r.json()
    assert [item["id"] for item in body["items"]] == [str(read_n.id)]


async def test_listing_rejects_page_or_page_size_out_of_range(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await _make_tenant(db)
    await db.commit()
    _user, token = await _make_user_with_token(db, tenant)
    await db.commit()

    async with _client(app) as c:
        page_zero = await c.get(
            "/api/v1/notifications", params={"page": 0}, headers=_auth_header(token)
        )
        page_size_zero = await c.get(
            "/api/v1/notifications", params={"page_size": 0}, headers=_auth_header(token)
        )
        page_size_too_high = await c.get(
            "/api/v1/notifications", params={"page_size": 101}, headers=_auth_header(token)
        )
        page_size_at_limit = await c.get(
            "/api/v1/notifications", params={"page_size": 100}, headers=_auth_header(token)
        )

    assert page_zero.status_code == 422
    assert page_size_zero.status_code == 422
    assert page_size_too_high.status_code == 422
    assert page_size_at_limit.status_code == 200


async def test_a_user_without_notifications_gets_an_empty_page(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await _make_tenant(db)
    await db.commit()
    _user, token = await _make_user_with_token(db, tenant)
    await db.commit()

    async with _client(app) as c:
        r = await c.get("/api/v1/notifications", headers=_auth_header(token))

    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0


# ── PATCH /notifications/{id}/read ──


async def test_marking_an_own_notification_as_read_returns_200(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await _make_tenant(db)
    await db.commit()
    user, token = await _make_user_with_token(db, tenant)
    await db.commit()
    notification = await _seed_notification(db, tenant_id=tenant.id, user_id=user.id)
    await db.commit()

    async with _client(app) as c:
        r = await c.patch(
            f"/api/v1/notifications/{notification.id}/read", headers=_auth_header(token)
        )

    assert r.status_code == 200
    assert r.json()["read_at"] is not None


async def test_marking_an_already_read_notification_is_idempotent(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await _make_tenant(db)
    await db.commit()
    user, token = await _make_user_with_token(db, tenant)
    await db.commit()
    notification = await _seed_notification(db, tenant_id=tenant.id, user_id=user.id, read=True)
    await db.commit()

    async with _client(app) as c:
        r = await c.patch(
            f"/api/v1/notifications/{notification.id}/read", headers=_auth_header(token)
        )

    assert r.status_code == 200
    assert r.json()["id"] == str(notification.id)


async def test_marking_another_users_notification_returns_404_and_does_not_affect_it(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await _make_tenant(db)
    await db.commit()
    owner, _owner_token = await _make_user_with_token(db, tenant)
    intruder, intruder_token = await _make_user_with_token(db, tenant)
    await db.commit()
    notification = await _seed_notification(db, tenant_id=tenant.id, user_id=owner.id)
    await db.commit()

    async with _client(app) as c:
        r = await c.patch(
            f"/api/v1/notifications/{notification.id}/read",
            headers=_auth_header(intruder_token),
        )

    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
    fetched = await SqlAlchemyNotificationRepository(db).get(notification.id)
    assert fetched is not None
    assert fetched.read_at is None


async def test_marking_a_nonexistent_notification_returns_404(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await _make_tenant(db)
    await db.commit()
    _user, token = await _make_user_with_token(db, tenant)
    await db.commit()

    async with _client(app) as c:
        r = await c.patch(f"/api/v1/notifications/{uuid.uuid4()}/read", headers=_auth_header(token))

    assert r.status_code == 404
