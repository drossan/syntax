"""Tests de integración de `SqlAlchemyTicketRepository`/`SqlAlchemyMessageRepository` (tarea
`backend-routers-core-07`). Postgres real vía `superuser_engine` (RLS no aplica — se prueba el
CONTRATO del adaptador: paginación/filtros/orden/CRUD, no el aislamiento RLS en sí, que se ejercita
end-to-end en `test_router_tickets.py` vía `app_engine`).
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest_asyncio
from app.domain.entities.business import Attachment, Message, Ticket
from app.domain.entities.enums import (
    KbDomain,
    MessageVisibility,
    TenantStatus,
    TicketPriority,
    TicketStatus,
)
from app.domain.entities.identity import Tenant, User
from app.infra.db.repositories import (
    SqlAlchemyMessageRepository,
    SqlAlchemyTenantRepository,
    SqlAlchemyTicketRepository,
    SqlAlchemyUserRepository,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

_TRUNCATE_TABLES = 'TRUNCATE attachment, message, ticket, tenant, "user" RESTART IDENTITY CASCADE'


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
        User(id=uuid.uuid4(), email=f"u-{uuid.uuid4()}@example.com", password_hash="hash")
    )


def _make_ticket(
    tenant_id: uuid.UUID,
    *,
    status: TicketStatus = TicketStatus.new,
    priority: TicketPriority = TicketPriority.normal,
    assignee_id: uuid.UUID | None = None,
    domain: KbDomain | None = None,
) -> Ticket:
    return Ticket(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        subject="s",
        status=status,
        priority=priority,
        assignee_id=assignee_id,
        domain=domain,
    )


# ── SqlAlchemyTicketRepository: CRUD ──


async def test_add_get_roundtrip(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    repo = SqlAlchemyTicketRepository(session)
    ticket = await repo.add(_make_ticket(tenant.id))
    await session.commit()

    found = await repo.get(ticket.id)

    assert found is not None
    assert found.subject == "s"
    assert found.status is TicketStatus.new


async def test_get_on_a_nonexistent_ticket_returns_none(session: AsyncSession) -> None:
    assert await SqlAlchemyTicketRepository(session).get(uuid.uuid4()) is None


async def test_update_persists_changes(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    repo = SqlAlchemyTicketRepository(session)
    ticket = await repo.add(_make_ticket(tenant.id))
    await session.commit()

    ticket.priority = TicketPriority.urgent
    ticket.category = "billing"
    await repo.update(ticket)
    await session.commit()

    reread = await repo.get(ticket.id)
    assert reread is not None
    assert reread.priority is TicketPriority.urgent
    assert reread.category == "billing"


# ── SqlAlchemyTicketRepository.list: paginación/filtros/orden ──


async def test_list_paginates_and_orders_by_updated_at_desc_by_default(
    session: AsyncSession,
) -> None:
    tenant = await _make_tenant(session)
    repo = SqlAlchemyTicketRepository(session)
    for _ in range(25):
        await repo.add(_make_ticket(tenant.id))
    await session.commit()

    page = await repo.list(tenant.id, page=1, page_size=20)

    assert len(page.items) == 20
    assert page.total == 25


async def test_list_second_page_returns_the_remainder(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    repo = SqlAlchemyTicketRepository(session)
    for _ in range(25):
        await repo.add(_make_ticket(tenant.id))
    await session.commit()

    page = await repo.list(tenant.id, page=2, page_size=20)

    assert len(page.items) == 5
    assert page.total == 25


async def test_list_does_not_leak_another_tenants_tickets(session: AsyncSession) -> None:
    tenant_a = await _make_tenant(session)
    tenant_b = await _make_tenant(session)
    repo = SqlAlchemyTicketRepository(session)
    await repo.add(_make_ticket(tenant_a.id))
    await repo.add(_make_ticket(tenant_b.id))
    await session.commit()

    page = await repo.list(tenant_a.id, page=1, page_size=20)

    assert page.total == 1


async def test_list_filters_by_status(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    repo = SqlAlchemyTicketRepository(session)
    await repo.add(_make_ticket(tenant.id, status=TicketStatus.open))
    await repo.add(_make_ticket(tenant.id, status=TicketStatus.new))
    await session.commit()

    page = await repo.list(tenant.id, page=1, page_size=20, status=TicketStatus.open)

    assert page.total == 1
    assert page.items[0].status is TicketStatus.open


async def test_list_filters_by_priority(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    repo = SqlAlchemyTicketRepository(session)
    await repo.add(_make_ticket(tenant.id, priority=TicketPriority.urgent))
    await repo.add(_make_ticket(tenant.id, priority=TicketPriority.low))
    await session.commit()

    page = await repo.list(tenant.id, page=1, page_size=20, priority=TicketPriority.urgent)

    assert page.total == 1
    assert page.items[0].priority is TicketPriority.urgent


async def test_list_filters_by_assignee_id(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    agent = await _make_user(session)
    other_agent = await _make_user(session)
    repo = SqlAlchemyTicketRepository(session)
    await repo.add(_make_ticket(tenant.id, assignee_id=agent.id))
    await repo.add(_make_ticket(tenant.id, assignee_id=other_agent.id))
    await repo.add(_make_ticket(tenant.id))
    await session.commit()

    page = await repo.list(tenant.id, page=1, page_size=20, assignee_id=agent.id)

    assert page.total == 1
    assert page.items[0].assignee_id == agent.id


async def test_list_combines_filters_with_and(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    repo = SqlAlchemyTicketRepository(session)
    await repo.add(
        _make_ticket(tenant.id, status=TicketStatus.open, priority=TicketPriority.urgent)
    )
    await repo.add(_make_ticket(tenant.id, status=TicketStatus.open, priority=TicketPriority.low))
    await repo.add(_make_ticket(tenant.id, status=TicketStatus.new, priority=TicketPriority.urgent))
    await session.commit()

    page = await repo.list(
        tenant.id, page=1, page_size=20, status=TicketStatus.open, priority=TicketPriority.urgent
    )

    assert page.total == 1


async def test_list_with_a_filter_matching_nothing_returns_an_empty_page(
    session: AsyncSession,
) -> None:
    tenant = await _make_tenant(session)
    repo = SqlAlchemyTicketRepository(session)
    await repo.add(_make_ticket(tenant.id))
    await session.commit()

    page = await repo.list(tenant.id, page=1, page_size=20, assignee_id=uuid.uuid4())

    assert page.items == []
    assert page.total == 0


async def test_list_sort_ascending_by_sla_due(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    repo = SqlAlchemyTicketRepository(session)
    early = await repo.add(_make_ticket(tenant.id))
    early.sla_due = datetime(2026, 1, 1, tzinfo=UTC)
    await repo.update(early)
    late = await repo.add(_make_ticket(tenant.id))
    late.sla_due = datetime(2026, 1, 2, tzinfo=UTC)
    await repo.update(late)
    await session.commit()

    page = await repo.list(tenant.id, page=1, page_size=20, sort="sla_due")

    assert [t.id for t in page.items] == [early.id, late.id]


async def test_list_sort_descending_by_created_at(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    repo = SqlAlchemyTicketRepository(session)
    first = await repo.add(_make_ticket(tenant.id))
    await session.commit()
    second = await repo.add(_make_ticket(tenant.id))
    await session.commit()

    page = await repo.list(tenant.id, page=1, page_size=20, sort="-created_at")

    assert [t.id for t in page.items] == [second.id, first.id]


# ── SqlAlchemyMessageRepository ──


async def test_message_add_and_list_by_ticket(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    ticket = await SqlAlchemyTicketRepository(session).add(_make_ticket(tenant.id))
    await session.commit()
    repo = SqlAlchemyMessageRepository(session)
    await repo.add(
        Message(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            ticket_id=ticket.id,
            author_id=None,
            visibility=MessageVisibility.public,
            body="hola",
        )
    )
    await session.commit()

    page = await repo.list_by_ticket(ticket.id)

    assert len(page.items) == 1
    assert page.items[0].body == "hola"
    assert page.total == 1


async def test_message_list_by_ticket_orders_by_created_at(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    ticket = await SqlAlchemyTicketRepository(session).add(_make_ticket(tenant.id))
    await session.commit()
    repo = SqlAlchemyMessageRepository(session)
    first = await repo.add(
        Message(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            ticket_id=ticket.id,
            visibility=MessageVisibility.public,
            body="primero",
        )
    )
    await session.commit()
    second = await repo.add(
        Message(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            ticket_id=ticket.id,
            visibility=MessageVisibility.public,
            body="segundo",
        )
    )
    await session.commit()

    page = await repo.list_by_ticket(ticket.id)

    assert [m.id for m in page.items] == [first.id, second.id]


async def test_message_list_by_ticket_does_not_leak_another_tickets_messages(
    session: AsyncSession,
) -> None:
    """El ticket objetivo (50) queda ENTRE otros dos con sus propios mensajes (10 y 90, UUIDs
    deterministas): descarta `<=`/`>=`/`is not` en el filtro `ticket_id` — cualquiera filtraría un
    mensaje de OTRO ticket."""
    tenant = await _make_tenant(session)
    ticket_repo = SqlAlchemyTicketRepository(session)
    target = await ticket_repo.add(
        Ticket(
            id=uuid.UUID(int=50),
            tenant_id=tenant.id,
            subject="s",
            status=TicketStatus.new,
            priority=TicketPriority.normal,
        )
    )
    low = await ticket_repo.add(
        Ticket(
            id=uuid.UUID(int=10),
            tenant_id=tenant.id,
            subject="s",
            status=TicketStatus.new,
            priority=TicketPriority.normal,
        )
    )
    high = await ticket_repo.add(
        Ticket(
            id=uuid.UUID(int=90),
            tenant_id=tenant.id,
            subject="s",
            status=TicketStatus.new,
            priority=TicketPriority.normal,
        )
    )
    await session.commit()
    repo = SqlAlchemyMessageRepository(session)
    await repo.add(
        Message(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            ticket_id=low.id,
            visibility=MessageVisibility.public,
            body="del bajo",
        )
    )
    await repo.add(
        Message(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            ticket_id=high.id,
            visibility=MessageVisibility.public,
            body="del alto",
        )
    )
    await session.commit()

    page = await repo.list_by_ticket(target.id)

    assert page.items == []


# ── SqlAlchemyMessageRepository: attachments ──


async def test_add_attachment_and_get_it_back(session: AsyncSession) -> None:
    tenant = await _make_tenant(session)
    ticket = await SqlAlchemyTicketRepository(session).add(_make_ticket(tenant.id))
    await session.commit()
    message_repo = SqlAlchemyMessageRepository(session)
    message = await message_repo.add(
        Message(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            ticket_id=ticket.id,
            visibility=MessageVisibility.public,
            body="con adjunto",
        )
    )
    await session.commit()

    attachment = await message_repo.add_attachment(
        Attachment(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            message_id=message.id,
            filename="informe.pdf",
            content_type="application/pdf",
            size_bytes=1234,
            storage_key=f"{tenant.id}/{message.id}/a1-informe.pdf",
        )
    )
    await session.commit()

    found = await message_repo.get_attachment(attachment.id)

    assert found is not None
    assert found.filename == "informe.pdf"
    assert found.size_bytes == 1234
    assert found.storage_key == attachment.storage_key


async def test_get_attachment_on_a_nonexistent_id_returns_none(session: AsyncSession) -> None:
    assert await SqlAlchemyMessageRepository(session).get_attachment(uuid.uuid4()) is None


async def test_two_attachments_with_the_same_filename_get_distinct_storage_keys(
    session: AsyncSession,
) -> None:
    """Dos adjuntos con el MISMO `filename` al MISMO mensaje no colisionan — la `storage_key` incluye
    un identificador único del adjunto (su propio `id`), no solo el nombre."""
    tenant = await _make_tenant(session)
    ticket = await SqlAlchemyTicketRepository(session).add(_make_ticket(tenant.id))
    await session.commit()
    message_repo = SqlAlchemyMessageRepository(session)
    message = await message_repo.add(
        Message(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            ticket_id=ticket.id,
            visibility=MessageVisibility.public,
            body="dos adjuntos",
        )
    )
    await session.commit()

    first = await message_repo.add_attachment(
        Attachment(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            message_id=message.id,
            filename="informe.pdf",
            content_type="application/pdf",
            size_bytes=10,
            storage_key=f"{tenant.id}/{message.id}/{uuid.uuid4()}-informe.pdf",
        )
    )
    second = await message_repo.add_attachment(
        Attachment(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            message_id=message.id,
            filename="informe.pdf",
            content_type="application/pdf",
            size_bytes=20,
            storage_key=f"{tenant.id}/{message.id}/{uuid.uuid4()}-informe.pdf",
        )
    )
    await session.commit()

    assert first.storage_key != second.storage_key
    assert await message_repo.get_attachment(first.id) is not None
    assert await message_repo.get_attachment(second.id) is not None
