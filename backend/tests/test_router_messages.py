"""Tests de integración del router `messages` (tarea `backend-routers-core-08`): hilo de mensajes
(filtro `internal` server-side) + adjuntos (`Storage` filesystem local). Mismo patrón que
`test_router_tickets.py`: `app_engine` (RLS real) para las requests, `db` (superuser) para sembrar.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
import pytest_asyncio
from app.core.config import Settings, get_settings
from app.core.deps import get_db_session, get_storage
from app.core.security import JWT_ALGORITHM, create_access_token, hash_password
from app.domain.entities.business import Message, Ticket
from app.domain.entities.enums import (
    MessageVisibility,
    NotificationType,
    RoleKind,
    TenantStatus,
    TicketPriority,
    TicketStatus,
    UserStatus,
)
from app.domain.entities.identity import Role, Tenant, User, UserTenantMembership
from app.domain.errors import PortError
from app.infra.db.repositories import (
    SqlAlchemyMessageRepository,
    SqlAlchemyNotificationRepository,
    SqlAlchemyRoleRepository,
    SqlAlchemyTenantRepository,
    SqlAlchemyTicketRepository,
    SqlAlchemyUserRepository,
    SqlAlchemyUserTenantMembershipRepository,
)
from app.main import create_app
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

_JWT_SECRET = "x" * 32
_TTL = 900


def _settings(*, storage_root: str, max_upload_bytes: int = 10 * 1024 * 1024) -> Settings:
    return Settings(
        _env_file=None,
        jwt_secret=_JWT_SECRET,
        app_env="production",
        cors_origins=[],
        storage_root=storage_root,
        max_upload_bytes=max_upload_bytes,
    )


_TRUNCATE_TABLES = (
    "TRUNCATE notification, attachment, message, ticket, audit_log, user_tenant, refresh_session, "
    'auth_token, user_role, role_capability, capability, "user", role, tenant RESTART IDENTITY CASCADE'
)


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
async def app(app_engine: AsyncEngine, tmp_path) -> AsyncIterator[FastAPI]:
    test_app = create_app(_settings(storage_root=str(tmp_path)))

    async def _override_session() -> AsyncIterator[AsyncSession]:
        async with async_sessionmaker(app_engine, expire_on_commit=False)() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    test_app.dependency_overrides[get_db_session] = _override_session
    test_app.dependency_overrides[get_settings] = lambda: _settings(storage_root=str(tmp_path))
    yield test_app
    test_app.dependency_overrides.clear()


def _client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _make_tenant() -> Tenant:
    return Tenant(
        id=uuid.uuid4(), slug=f"t-{uuid.uuid4()}", name="Tenant", status=TenantStatus.active
    )


def _make_ticket_entity(tenant_id: uuid.UUID) -> Ticket:
    return Ticket(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        subject="s",
        status=TicketStatus.new,
        priority=TicketPriority.normal,
    )


async def _make_user(db: AsyncSession) -> User:
    return await SqlAlchemyUserRepository(db).add(
        User(
            id=uuid.uuid4(),
            email=f"u-{uuid.uuid4()}@example.com",
            password_hash=hash_password("pw"),
        )
    )


async def _add_membership(db: AsyncSession, *, user_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    await SqlAlchemyUserTenantMembershipRepository(db).add(
        UserTenantMembership(user_id=user_id, tenant_id=tenant_id, status=UserStatus.active)
    )


async def _grant_capability(
    db: AsyncSession, *, user_id: uuid.UUID, tenant_id: uuid.UUID, capability: str
) -> None:
    role_repo = SqlAlchemyRoleRepository(db)
    role = await role_repo.add(
        Role(
            id=uuid.uuid4(), name=f"role-{uuid.uuid4()}", kind=RoleKind.tenant, tenant_id=tenant_id
        )
    )
    existing_capability_id = (
        await db.execute(text("SELECT id FROM capability WHERE name = :name"), {"name": capability})
    ).scalar_one_or_none()
    if existing_capability_id is None:
        capability_id = uuid.uuid4()
        await db.execute(
            text("INSERT INTO capability (id, name, scope) VALUES (:id, :name, 'tenant')"),
            {"id": capability_id, "name": capability},
        )
    else:
        capability_id = existing_capability_id
    await db.execute(
        text("INSERT INTO role_capability (role_id, capability_id) VALUES (:r, :c)"),
        {"r": role.id, "c": capability_id},
    )
    await role_repo.assign(user_id, role.id, tenant_id)
    await db.commit()


def _access_token(user_id: uuid.UUID, tenant_id: uuid.UUID) -> str:
    return create_access_token(
        str(user_id),
        str(tenant_id),
        secret=_JWT_SECRET,
        algorithm=JWT_ALGORITHM,
        ttl=_TTL,
        now=datetime.now(UTC),
    )


async def _agent_with_capabilities(
    db: AsyncSession, *, tenant: Tenant, capabilities: list[str]
) -> tuple[User, str]:
    agent = await _make_user(db)
    await _add_membership(db, user_id=agent.id, tenant_id=tenant.id)
    for capability in capabilities:
        await _grant_capability(db, user_id=agent.id, tenant_id=tenant.id, capability=capability)
    token = _access_token(agent.id, tenant.id)
    return agent, token


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── GET /tickets/{id}/messages ──


async def test_list_messages_hides_internal_from_a_subject_without_the_capability(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    await db.commit()
    message_repo = SqlAlchemyMessageRepository(db)
    await message_repo.add(
        Message(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            ticket_id=ticket.id,
            visibility=MessageVisibility.public,
            body="publico",
        )
    )
    await message_repo.add(
        Message(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            ticket_id=ticket.id,
            visibility=MessageVisibility.internal,
            body="interno",
        )
    )
    await db.commit()
    _agent, token = await _agent_with_capabilities(db, tenant=tenant, capabilities=["ticket.read"])

    async with _client(app) as c:
        r = await c.get(f"/api/v1/tickets/{ticket.id}/messages", headers=_auth_header(token))

    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert [m["body"] for m in body["items"]] == ["publico"]


async def test_list_messages_shows_internal_to_a_subject_with_the_capability(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    await db.commit()
    message_repo = SqlAlchemyMessageRepository(db)
    await message_repo.add(
        Message(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            ticket_id=ticket.id,
            visibility=MessageVisibility.public,
            body="publico",
        )
    )
    await message_repo.add(
        Message(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            ticket_id=ticket.id,
            visibility=MessageVisibility.internal,
            body="interno",
        )
    )
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.read", "note.internal.read"]
    )

    async with _client(app) as c:
        r = await c.get(f"/api/v1/tickets/{ticket.id}/messages", headers=_auth_header(token))

    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert {m["body"] for m in body["items"]} == {"publico", "interno"}


async def test_list_messages_on_a_ticket_with_none_returns_an_empty_page(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    await db.commit()
    _agent, token = await _agent_with_capabilities(db, tenant=tenant, capabilities=["ticket.read"])

    async with _client(app) as c:
        r = await c.get(f"/api/v1/tickets/{ticket.id}/messages", headers=_auth_header(token))

    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0


async def test_list_messages_paginates(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    await db.commit()
    message_repo = SqlAlchemyMessageRepository(db)
    for _ in range(25):
        await message_repo.add(
            Message(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                ticket_id=ticket.id,
                visibility=MessageVisibility.public,
                body="m",
            )
        )
    await db.commit()
    _agent, token = await _agent_with_capabilities(db, tenant=tenant, capabilities=["ticket.read"])

    async with _client(app) as c:
        r = await c.get(f"/api/v1/tickets/{ticket.id}/messages", headers=_auth_header(token))

    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 20
    assert body["total"] == 25


async def test_list_messages_rejects_page_size_out_of_range(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    await db.commit()
    _agent, token = await _agent_with_capabilities(db, tenant=tenant, capabilities=["ticket.read"])

    async with _client(app) as c:
        too_low = await c.get(
            f"/api/v1/tickets/{ticket.id}/messages",
            params={"page_size": 0},
            headers=_auth_header(token),
        )
        too_high = await c.get(
            f"/api/v1/tickets/{ticket.id}/messages",
            params={"page_size": 101},
            headers=_auth_header(token),
        )
        at_limit = await c.get(
            f"/api/v1/tickets/{ticket.id}/messages",
            params={"page_size": 100},
            headers=_auth_header(token),
        )

    assert too_low.status_code == 422
    assert too_high.status_code == 422
    assert at_limit.status_code == 200


# ── POST /tickets/{id}/messages ──


async def test_replying_public_requires_ticket_reply(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    await db.commit()
    _agent, token = await _agent_with_capabilities(db, tenant=tenant, capabilities=["ticket.read"])

    async with _client(app) as c:
        r = await c.post(
            f"/api/v1/tickets/{ticket.id}/messages",
            json={"body": "hola", "visibility": "public"},
            headers=_auth_header(token),
        )

    assert r.status_code == 403
    assert r.headers["content-type"].startswith("application/problem+json")


async def test_writing_an_internal_note_requires_note_internal_write(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.read", "ticket.reply"]
    )

    async with _client(app) as c:
        r = await c.post(
            f"/api/v1/tickets/{ticket.id}/messages",
            json={"body": "nota", "visibility": "internal"},
            headers=_auth_header(token),
        )

    assert r.status_code == 403
    assert r.headers["content-type"].startswith("application/problem+json")


async def test_replying_public_with_the_capability_succeeds(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.read", "ticket.reply"]
    )

    async with _client(app) as c:
        r = await c.post(
            f"/api/v1/tickets/{ticket.id}/messages",
            json={"body": "hola", "visibility": "public"},
            headers=_auth_header(token),
        )

    assert r.status_code == 201
    assert r.json()["body"] == "hola"
    assert r.json()["visibility"] == "public"


async def test_replying_public_returns_the_authors_email_not_just_its_id(
    app: FastAPI, db: AsyncSession
) -> None:
    """El frontend no puede resolver un UUID a un nombre por su cuenta -- `author_email` viaja en la
    respuesta del propio POST, no hace falta una segunda llamada."""
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    await db.commit()
    agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.read", "ticket.reply"]
    )

    async with _client(app) as c:
        r = await c.post(
            f"/api/v1/tickets/{ticket.id}/messages",
            json={"body": "hola", "visibility": "public"},
            headers=_auth_header(token),
        )

    assert r.json()["author_email"] == agent.email


async def test_list_messages_returns_each_authors_email(app: FastAPI, db: AsyncSession) -> None:
    """`list_messages` resuelve el email de CADA autor -- no solo el del propio subject (regresión
    del caso real: un mensaje de OTRO agente seguía mostrando su UUID)."""
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    await db.commit()
    author_a, token_a = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.read", "ticket.reply"]
    )
    author_b, token_b = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.read", "ticket.reply"]
    )

    async with _client(app) as c:
        await c.post(
            f"/api/v1/tickets/{ticket.id}/messages",
            json={"body": "de A", "visibility": "public"},
            headers=_auth_header(token_a),
        )
        await c.post(
            f"/api/v1/tickets/{ticket.id}/messages",
            json={"body": "de B", "visibility": "public"},
            headers=_auth_header(token_b),
        )
        r = await c.get(f"/api/v1/tickets/{ticket.id}/messages", headers=_auth_header(token_a))

    emails_by_body = {m["body"]: m["author_email"] for m in r.json()["items"]}
    assert emails_by_body == {"de A": author_a.email, "de B": author_b.email}


async def test_replying_with_an_empty_body_is_rejected(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.read", "ticket.reply"]
    )

    async with _client(app) as c:
        r = await c.post(
            f"/api/v1/tickets/{ticket.id}/messages",
            json={"body": "", "visibility": "public"},
            headers=_auth_header(token),
        )

    assert r.status_code == 422


async def test_replying_with_an_invalid_visibility_is_rejected(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.read", "ticket.reply"]
    )

    async with _client(app) as c:
        r = await c.post(
            f"/api/v1/tickets/{ticket.id}/messages",
            json={"body": "hola", "visibility": "no-es-una-visibilidad"},
            headers=_auth_header(token),
        )

    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")


# ── POST /tickets/{id}/messages: notifica ticket_reply (FR-038, tarea backend-routers-flujo-ia-04) ──


async def _notifications_for(db: AsyncSession, user_id: uuid.UUID) -> list[object]:
    result = await SqlAlchemyNotificationRepository(db).list_for_user(
        user_id, page=1, page_size=100
    )
    return list(result.items)


@pytest.mark.parametrize(
    ("author_role", "expected_recipient_role"),
    [("assignee", "requester"), ("requester", "assignee")],
)
async def test_replying_public_notifies_the_other_party(
    app: FastAPI, db: AsyncSession, author_role: str, expected_recipient_role: str
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    requester = await _make_user(db)
    assignee = await _make_user(db)
    await _add_membership(db, user_id=requester.id, tenant_id=tenant.id)
    await _add_membership(db, user_id=assignee.id, tenant_id=tenant.id)
    ticket = await SqlAlchemyTicketRepository(db).add(
        Ticket(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            subject="s",
            status=TicketStatus.new,
            priority=TicketPriority.normal,
            requester_id=requester.id,
            assignee_id=assignee.id,
        )
    )
    await db.commit()
    authors = {"requester": requester, "assignee": assignee}
    recipients = {"requester": requester, "assignee": assignee}
    author = authors[author_role]
    expected_recipient = recipients[expected_recipient_role]
    await _grant_capability(db, user_id=author.id, tenant_id=tenant.id, capability="ticket.read")
    await _grant_capability(db, user_id=author.id, tenant_id=tenant.id, capability="ticket.reply")
    token = _access_token(author.id, tenant.id)

    async with _client(app) as c:
        r = await c.post(
            f"/api/v1/tickets/{ticket.id}/messages",
            json={"body": "respuesta", "visibility": "public"},
            headers=_auth_header(token),
        )

    assert r.status_code == 201
    notifications = await _notifications_for(db, expected_recipient.id)
    assert len(notifications) == 1
    assert notifications[0].type is NotificationType.ticket_reply
    assert await _notifications_for(db, author.id) == []


async def test_a_third_agent_replying_notifies_both_requester_and_assignee(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    requester = await _make_user(db)
    assignee = await _make_user(db)
    await _add_membership(db, user_id=requester.id, tenant_id=tenant.id)
    await _add_membership(db, user_id=assignee.id, tenant_id=tenant.id)
    ticket = await SqlAlchemyTicketRepository(db).add(
        Ticket(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            subject="s",
            status=TicketStatus.new,
            priority=TicketPriority.normal,
            requester_id=requester.id,
            assignee_id=assignee.id,
        )
    )
    await db.commit()
    _third_agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.read", "ticket.reply"]
    )

    async with _client(app) as c:
        r = await c.post(
            f"/api/v1/tickets/{ticket.id}/messages",
            json={"body": "respuesta", "visibility": "public"},
            headers=_auth_header(token),
        )

    assert r.status_code == 201
    assert len(await _notifications_for(db, requester.id)) == 1
    assert len(await _notifications_for(db, assignee.id)) == 1


async def test_writing_an_internal_note_does_not_notify(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    requester = await _make_user(db)
    assignee = await _make_user(db)
    await _add_membership(db, user_id=requester.id, tenant_id=tenant.id)
    await _add_membership(db, user_id=assignee.id, tenant_id=tenant.id)
    ticket = await SqlAlchemyTicketRepository(db).add(
        Ticket(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            subject="s",
            status=TicketStatus.new,
            priority=TicketPriority.normal,
            requester_id=requester.id,
            assignee_id=assignee.id,
        )
    )
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.read", "note.internal.write", "note.internal.read"]
    )

    async with _client(app) as c:
        r = await c.post(
            f"/api/v1/tickets/{ticket.id}/messages",
            json={"body": "nota", "visibility": "internal"},
            headers=_auth_header(token),
        )

    assert r.status_code == 201
    assert await _notifications_for(db, requester.id) == []
    assert await _notifications_for(db, assignee.id) == []


# ── POST /messages/{id}/attachments · GET /messages/{id}/attachments/{attachment_id} ──


async def _seed_message(db: AsyncSession, tenant: Tenant) -> tuple[Ticket, Message]:
    ticket = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    await db.commit()
    message = await SqlAlchemyMessageRepository(db).add(
        Message(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            ticket_id=ticket.id,
            visibility=MessageVisibility.public,
            body="con adjunto",
        )
    )
    await db.commit()
    return ticket, message


async def test_uploading_an_attachment_persists_it_and_makes_it_retrievable(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    _ticket, message = await _seed_message(db, tenant)
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.read", "ticket.reply"]
    )

    async with _client(app) as c:
        upload = await c.post(
            f"/api/v1/messages/{message.id}/attachments",
            files={"file": ("informe.pdf", b"contenido-pdf", "application/pdf")},
            headers=_auth_header(token),
        )
        attachment_id = upload.json()["id"]
        download = await c.get(
            f"/api/v1/messages/{message.id}/attachments/{attachment_id}",
            headers=_auth_header(token),
        )

    assert upload.status_code == 201
    assert upload.json()["filename"] == "informe.pdf"
    assert download.status_code == 200
    assert download.content == b"contenido-pdf"
    assert download.headers["content-type"] == "application/pdf"


async def test_two_attachments_with_the_same_filename_do_not_overwrite_each_other(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    _ticket, message = await _seed_message(db, tenant)
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.read", "ticket.reply"]
    )

    async with _client(app) as c:
        first = await c.post(
            f"/api/v1/messages/{message.id}/attachments",
            files={"file": ("informe.pdf", b"primero", "application/pdf")},
            headers=_auth_header(token),
        )
        second = await c.post(
            f"/api/v1/messages/{message.id}/attachments",
            files={"file": ("informe.pdf", b"segundo", "application/pdf")},
            headers=_auth_header(token),
        )
        first_download = await c.get(
            f"/api/v1/messages/{message.id}/attachments/{first.json()['id']}",
            headers=_auth_header(token),
        )
        second_download = await c.get(
            f"/api/v1/messages/{message.id}/attachments/{second.json()['id']}",
            headers=_auth_header(token),
        )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first_download.content == b"primero"
    assert second_download.content == b"segundo"


async def test_uploading_an_attachment_exceeding_the_max_size_is_rejected(
    app: FastAPI, db: AsyncSession, tmp_path
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    _ticket, message = await _seed_message(db, tenant)
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.read", "ticket.reply"]
    )
    app.dependency_overrides[get_settings] = lambda: _settings(
        storage_root=str(tmp_path), max_upload_bytes=10
    )

    async with _client(app) as c:
        r = await c.post(
            f"/api/v1/messages/{message.id}/attachments",
            files={"file": ("big.bin", b"x" * 11, "application/octet-stream")},
            headers=_auth_header(token),
        )

    assert r.status_code == 413


async def test_uploading_an_attachment_at_exactly_the_max_size_is_accepted(
    app: FastAPI, db: AsyncSession, tmp_path
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    _ticket, message = await _seed_message(db, tenant)
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.read", "ticket.reply"]
    )
    app.dependency_overrides[get_settings] = lambda: _settings(
        storage_root=str(tmp_path), max_upload_bytes=10
    )

    async with _client(app) as c:
        r = await c.post(
            f"/api/v1/messages/{message.id}/attachments",
            files={"file": ("exact.bin", b"x" * 10, "application/octet-stream")},
            headers=_auth_header(token),
        )

    assert r.status_code == 201


async def test_uploading_an_empty_attachment_is_accepted(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    _ticket, message = await _seed_message(db, tenant)
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.read", "ticket.reply"]
    )

    async with _client(app) as c:
        r = await c.post(
            f"/api/v1/messages/{message.id}/attachments",
            files={"file": ("empty.bin", b"", "application/octet-stream")},
            headers=_auth_header(token),
        )

    assert r.status_code == 201
    assert r.json()["size_bytes"] == 0


async def test_uploading_an_attachment_to_a_nonexistent_message_returns_404(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.read", "ticket.reply"]
    )

    async with _client(app) as c:
        r = await c.post(
            f"/api/v1/messages/{uuid.uuid4()}/attachments",
            files={"file": ("x.bin", b"x", "application/octet-stream")},
            headers=_auth_header(token),
        )

    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")


async def test_a_storage_save_failure_becomes_a_controlled_502(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    _ticket, message = await _seed_message(db, tenant)
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.read", "ticket.reply"]
    )

    class _BrokenStorage:
        async def save(self, key: str, content: bytes, content_type: str) -> None:
            raise PortError("disco lleno")

        async def get_url_or_path(self, key: str) -> str:
            raise PortError("disco lleno")

    app.dependency_overrides[get_storage] = _BrokenStorage

    async with _client(app) as c:
        r = await c.post(
            f"/api/v1/messages/{message.id}/attachments",
            files={"file": ("x.bin", b"x", "application/octet-stream")},
            headers=_auth_header(token),
        )

    assert r.status_code == 502
    assert r.headers["content-type"].startswith("application/problem+json")


async def test_downloading_an_attachment_via_the_wrong_message_id_returns_404(
    app: FastAPI, db: AsyncSession
) -> None:
    """El `attachment_id` existe, pero pertenece a OTRO mensaje — la URL pide uno concreto, así que
    un `attachment_id` real cuyo `message_id` no coincide con el de la URL debe dar 404, no servir el
    contenido de un adjunto "vecino"."""
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    _ticket_a, message_a = await _seed_message(db, tenant)
    _ticket_b, message_b = await _seed_message(db, tenant)
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.read", "ticket.reply"]
    )

    async with _client(app) as c:
        upload = await c.post(
            f"/api/v1/messages/{message_a.id}/attachments",
            files={"file": ("a.bin", b"del mensaje a", "application/octet-stream")},
            headers=_auth_header(token),
        )
        mismatched = await c.get(
            f"/api/v1/messages/{message_b.id}/attachments/{upload.json()['id']}",
            headers=_auth_header(token),
        )

    assert upload.status_code == 201
    assert mismatched.status_code == 404
    assert mismatched.headers["content-type"].startswith("application/problem+json")


# ── Message.attachments (descubrir lo ya subido, GET /tickets/{id}/messages) ──


async def test_a_newly_created_message_has_no_attachments(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket = await SqlAlchemyTicketRepository(db).add(_make_ticket_entity(tenant.id))
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.read", "ticket.reply"]
    )

    async with _client(app) as c:
        r = await c.post(
            f"/api/v1/tickets/{ticket.id}/messages",
            json={"body": "sin adjuntos todavía", "visibility": "public"},
            headers=_auth_header(token),
        )

    assert r.status_code == 201
    assert r.json()["attachments"] == []


async def test_list_messages_includes_uploaded_attachments(
    app: FastAPI, db: AsyncSession
) -> None:
    """Antes de esta tarea no había forma de recuperar lo ya subido — solo subir y descargar-si-ya-
    sabes-el-id. Este es el test que cierra ese gap: lo que se sube aparece al listar el hilo."""
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    ticket, message_with_attachment = await _seed_message(db, tenant)
    message_repo = SqlAlchemyMessageRepository(db)
    message_without_attachment = await message_repo.add(
        Message(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            ticket_id=ticket.id,
            visibility=MessageVisibility.public,
            body="sin adjunto",
        )
    )
    await db.commit()
    _agent, token = await _agent_with_capabilities(
        db, tenant=tenant, capabilities=["ticket.read", "ticket.reply"]
    )

    async with _client(app) as c:
        await c.post(
            f"/api/v1/messages/{message_with_attachment.id}/attachments",
            files={"file": ("informe.pdf", b"contenido-pdf", "application/pdf")},
            headers=_auth_header(token),
        )
        r = await c.get(f"/api/v1/tickets/{ticket.id}/messages", headers=_auth_header(token))

    assert r.status_code == 200
    by_id = {m["id"]: m for m in r.json()["items"]}
    attached = by_id[str(message_with_attachment.id)]["attachments"]
    assert len(attached) == 1
    assert attached[0]["filename"] == "informe.pdf"
    assert attached[0]["content_type"] == "application/pdf"
    assert attached[0]["size_bytes"] == len(b"contenido-pdf")
    assert by_id[str(message_without_attachment.id)]["attachments"] == []
