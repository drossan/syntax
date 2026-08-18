"""Tests de BaseRepository (tarea 08) — aislamiento app-level por tenant_id.

Integración contra Postgres real. Se usa `superuser_engine` (RLS NO aplica) a propósito: así el
ÚNICO filtro es el `WHERE tenant_id` del repo → se prueba la 1ª línea de defensa app-level de forma
independiente de la RLS (defensa en profundidad). Filas commiteadas + TRUNCATE en el teardown.
"""

import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from app.infra.db.models import Ticket
from app.infra.db.models.enums import TicketPriority, TicketStatus
from app.infra.db.repositories import BaseRepository
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

_INSERT_TICKET = text(
    "INSERT INTO ticket (id, tenant_id, subject, status, priority, created_at, updated_at) "
    "VALUES (:id, :t, 'subj', 'new', 'normal', now(), now())"
)


@pytest_asyncio.fixture
async def seeded(superuser_engine: AsyncEngine) -> SimpleNamespace:
    """Tenant A con 3 tickets (ids conocidos) y tenant B con 1, COMMITEADOS."""
    a, b = uuid.uuid4(), uuid.uuid4()
    a_tickets = sorted([uuid.uuid4(), uuid.uuid4(), uuid.uuid4()])
    b_ticket = uuid.uuid4()
    async with superuser_engine.begin() as conn:
        for tenant_id in (a, b):
            await conn.execute(
                text(
                    "INSERT INTO tenant (id, slug, name, status, created_at, updated_at) "
                    "VALUES (:id, :slug, 't', 'active', now(), now())"
                ),
                {"id": tenant_id, "slug": str(tenant_id)},
            )
        for ticket_id in a_tickets:
            await conn.execute(_INSERT_TICKET, {"id": ticket_id, "t": a})
        await conn.execute(_INSERT_TICKET, {"id": b_ticket, "t": b})
    yield SimpleNamespace(a=a, b=b, a_tickets=a_tickets, b_ticket=b_ticket)
    async with superuser_engine.begin() as conn:
        await conn.execute(text("TRUNCATE ticket, tenant CASCADE"))


def _repo(session: AsyncSession) -> BaseRepository[Ticket]:
    return BaseRepository(session, Ticket)


async def test_get_returns_own_tenant_row(
    superuser_engine: AsyncEngine, seeded: SimpleNamespace
) -> None:
    """get devuelve una fila del propio tenant."""
    async with async_sessionmaker(superuser_engine)() as session:
        row = await _repo(session).get(seeded.a_tickets[0], seeded.a)
    assert row is not None
    assert row.id == seeded.a_tickets[0]


async def test_get_other_tenant_returns_none(
    superuser_engine: AsyncEngine, seeded: SimpleNamespace
) -> None:
    """get de una fila de OTRO tenant devuelve None (filtro app-level, no revela la fila de B)."""
    async with async_sessionmaker(superuser_engine)() as session:
        row = await _repo(session).get(seeded.b_ticket, seeded.a)
    assert row is None


async def test_get_missing_id_returns_none(
    superuser_engine: AsyncEngine, seeded: SimpleNamespace
) -> None:
    """get de un id inexistente devuelve None (indistinguible de 'existe en otro tenant')."""
    async with async_sessionmaker(superuser_engine)() as session:
        row = await _repo(session).get(uuid.uuid4(), seeded.a)
    assert row is None


async def test_list_filters_by_tenant_in_deterministic_order(
    superuser_engine: AsyncEngine, seeded: SimpleNamespace
) -> None:
    """list solo devuelve filas del tenant y en orden determinista (por id, aserción explícita)."""
    async with async_sessionmaker(superuser_engine)() as session:
        rows = await _repo(session).list(seeded.a)
    assert [row.id for row in rows] == seeded.a_tickets  # a_tickets ya viene ordenado


async def test_list_empty_returns_empty_list(
    superuser_engine: AsyncEngine, seeded: SimpleNamespace
) -> None:
    """list sin filas del tenant devuelve [] (no None ni excepción)."""
    async with async_sessionmaker(superuser_engine)() as session:
        rows = await _repo(session).list(uuid.uuid4())
    assert rows == []


async def test_add_persists_and_is_retrievable(
    superuser_engine: AsyncEngine, seeded: SimpleNamespace
) -> None:
    """add persiste la entidad y queda recuperable por get."""
    async with async_sessionmaker(superuser_engine)() as session:
        repo = _repo(session)
        entity = Ticket(
            tenant_id=seeded.a,
            subject="nuevo",
            status=TicketStatus.new,
            priority=TicketPriority.normal,
        )
        added = await repo.add(entity)
        found = await repo.get(added.id, seeded.a)
    assert found is not None
    assert found.id == added.id


async def test_add_unique_violation_raises_integrity_error(
    superuser_engine: AsyncEngine, seeded: SimpleNamespace
) -> None:
    """add que viola una unicidad (PK duplicada) propaga IntegrityError (no se traga)."""
    async with async_sessionmaker(superuser_engine)() as session:
        repo = _repo(session)
        clash = Ticket(
            id=seeded.a_tickets[0],  # id ya existente
            tenant_id=seeded.a,
            subject="dup",
            status=TicketStatus.new,
            priority=TicketPriority.normal,
        )
        with pytest.raises(IntegrityError):
            await repo.add(clash)


async def test_delete_other_tenant_deletes_nothing(
    superuser_engine: AsyncEngine, seeded: SimpleNamespace
) -> None:
    """delete de una fila de OTRO tenant no borra nada y devuelve False."""
    async with async_sessionmaker(superuser_engine)() as session:
        repo = _repo(session)
        deleted = await repo.delete(seeded.b_ticket, seeded.a)
        await session.commit()
        still_there = await repo.get(seeded.b_ticket, seeded.b)
    assert deleted is False
    assert still_there is not None


async def test_delete_within_tenant_then_idempotent(
    superuser_engine: AsyncEngine, seeded: SimpleNamespace
) -> None:
    """delete propio borra y devuelve True; un segundo delete devuelve False sin excepción."""
    async with async_sessionmaker(superuser_engine)() as session:
        repo = _repo(session)
        first = await repo.delete(seeded.a_tickets[0], seeded.a)
        second = await repo.delete(seeded.a_tickets[0], seeded.a)
        await session.commit()
    assert first is True
    assert second is False
