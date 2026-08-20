"""Tests de integración de la migración 0003 (backend-routers-flujo-ia-01) — Postgres real.

Índice único parcial `ix_agent_run_active_per_ticket` en `agent_run(ticket_id)` `WHERE status IN
('queued', 'running')` — CAS real contra dos runs concurrentes para el mismo ticket (`design-review`
#1 del plan). Sin este índice, el check-then-act de `agent_service.trigger()` no es una garantía
atómica bajo concurrencia.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine


async def _insert_tenant(conn: object, *, slug: str | None = None) -> uuid.UUID:
    slug = slug or f"t-{uuid.uuid4()}"
    result = await conn.execute(  # type: ignore[attr-defined]
        text(
            "INSERT INTO tenant (id, slug, name, status, created_at, updated_at) "
            "VALUES (gen_random_uuid(), :slug, 'chk', 'active', now(), now()) RETURNING id"
        ),
        {"slug": slug},
    )
    return result.scalar()  # type: ignore[no-any-return]


async def _insert_ticket(conn: object, tenant_id: uuid.UUID) -> uuid.UUID:
    result = await conn.execute(  # type: ignore[attr-defined]
        text(
            "INSERT INTO ticket (id, tenant_id, subject, status, priority, created_at, updated_at) "
            "VALUES (gen_random_uuid(), :t, 'subj', 'new', 'normal', now(), now()) RETURNING id"
        ),
        {"t": tenant_id},
    )
    return result.scalar()  # type: ignore[no-any-return]


async def _insert_agent_run(
    conn: object, *, tenant_id: uuid.UUID, ticket_id: uuid.UUID, status: str, thread: str
) -> None:
    await conn.execute(  # type: ignore[attr-defined]
        text(
            "INSERT INTO agent_run "
            "(id, tenant_id, ticket_id, langgraph_thread_id, run_seq, status, escalated, created_at) "
            "VALUES (gen_random_uuid(), :t, :ticket, :thread, 1, :status, false, now())"
        ),
        {"t": tenant_id, "ticket": ticket_id, "status": status, "thread": thread},
    )


async def test_index_exists_unique_and_partial(superuser_engine: AsyncEngine) -> None:
    async with superuser_engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE indexname = 'ix_agent_run_active_per_ticket'"
                )
            )
        ).scalar_one()
    assert "UNIQUE" in row
    assert "WHERE" in row
    assert "queued" in row
    assert "running" in row


@pytest.mark.parametrize("second_status", ["queued", "running"])
async def test_a_second_active_run_for_the_same_ticket_is_rejected(
    superuser_engine: AsyncEngine, second_status: str
) -> None:
    """Dos runs no-terminales (queued/running) para el MISMO ticket violan el índice único."""
    async with superuser_engine.connect() as conn:
        tenant_id = await _insert_tenant(conn)
        ticket_id = await _insert_ticket(conn, tenant_id)
        await _insert_agent_run(
            conn, tenant_id=tenant_id, ticket_id=ticket_id, status="queued", thread="t1"
        )
        with pytest.raises(IntegrityError):
            await _insert_agent_run(
                conn, tenant_id=tenant_id, ticket_id=ticket_id, status=second_status, thread="t2"
            )
        await conn.rollback()


@pytest.mark.parametrize("terminal_status", ["succeeded", "failed"])
async def test_a_terminal_run_does_not_block_a_new_active_run_for_the_same_ticket(
    superuser_engine: AsyncEngine, terminal_status: str
) -> None:
    """Un run YA terminal (succeeded/failed) no cuenta para el índice: uno nuevo queued sí puede
    coexistir (reopen/run_seq siguiente)."""
    async with superuser_engine.connect() as conn:
        tenant_id = await _insert_tenant(conn)
        ticket_id = await _insert_ticket(conn, tenant_id)
        await _insert_agent_run(
            conn, tenant_id=tenant_id, ticket_id=ticket_id, status=terminal_status, thread="t1"
        )
        await _insert_agent_run(
            conn, tenant_id=tenant_id, ticket_id=ticket_id, status="queued", thread="t2"
        )
        await conn.rollback()


async def test_two_different_tickets_can_each_have_an_active_run(
    superuser_engine: AsyncEngine,
) -> None:
    """El índice es por ticket_id: dos tickets distintos pueden tener cada uno un run activo."""
    async with superuser_engine.connect() as conn:
        tenant_id = await _insert_tenant(conn)
        ticket_a = await _insert_ticket(conn, tenant_id)
        ticket_b = await _insert_ticket(conn, tenant_id)
        await _insert_agent_run(
            conn, tenant_id=tenant_id, ticket_id=ticket_a, status="queued", thread="t1"
        )
        await _insert_agent_run(
            conn, tenant_id=tenant_id, ticket_id=ticket_b, status="queued", thread="t2"
        )
        await conn.rollback()
