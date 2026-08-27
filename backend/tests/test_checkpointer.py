"""Tests de app.agents.checkpointer (tarea backend-agent-graph-07) — Postgres real (fixture test-DB).

**Integración OBLIGATORIA** (HOW-TO-START-A-TASK.md): checkpointer/HITL no se mockea. Usa la migración
`0005` (fixture `migrated_database`, ya aplicada por `conftest.py`) y el rol runtime `syntax_app`
(`app_db_url`) — el mismo rol con el que corre la app real, sin privilegios de superuser.

Los tests de roundtrip/aislamiento construyen su PROPIO pool apuntando a `syntax_test` (vía
`_checkpointer_dsn(app_db_url)`), en vez de pasar por el singleton `get_checkpointer_pool()`: ese
singleton es perezoso y process-wide (mismo criterio que `get_engine()` en `test_session.py`) — su
propio test de memoización usa la config por defecto, sin necesitar una conexión real.
"""

import uuid

import pytest
from app.agents.checkpointer import _checkpointer_dsn, get_checkpointer, get_checkpointer_pool
from app.core.config import get_settings
from langgraph.checkpoint.base import empty_checkpoint
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool, PoolTimeout


def test_dsn_translates_asyncpg_driver_to_plain_postgresql() -> None:
    dsn = "postgresql+asyncpg://syntax_app:syntax_app@localhost:5432/syntax"
    result = _checkpointer_dsn(dsn)

    assert "+asyncpg" not in result
    assert result == "postgresql://syntax_app:syntax_app@localhost:5432/syntax"


def test_dsn_without_the_asyncpg_driver_is_left_unchanged() -> None:
    dsn = "postgresql://syntax_app:syntax_app@localhost:5432/syntax"
    assert _checkpointer_dsn(dsn) == dsn


def test_checkpointer_pool_is_a_singleton_per_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dos llamadas sucesivas devuelven el MISMO objeto (no se abre una segunda conexión)."""
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()

    import app.agents.checkpointer as checkpointer_module

    checkpointer_module._pool = None
    try:
        pool_a = get_checkpointer_pool()
        pool_b = get_checkpointer_pool()
        assert pool_a is not None
        assert pool_a is pool_b
    finally:
        checkpointer_module._pool = None
        get_settings.cache_clear()


def test_checkpointer_pool_is_built_with_autocommit_and_dict_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El pool usa `autocommit=True`, `prepare_threshold=0` y `row_factory=dict_row` — mismos
    parámetros que `AsyncPostgresSaver.from_conn_string` (verificado contra el SDK instalado)."""
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()

    import app.agents.checkpointer as checkpointer_module

    checkpointer_module._pool = None
    try:
        pool = get_checkpointer_pool()
        assert pool.kwargs["autocommit"] is True
        assert pool.kwargs["prepare_threshold"] == 0
        assert pool.kwargs["row_factory"] is dict_row
    finally:
        checkpointer_module._pool = None
        get_settings.cache_clear()


async def test_get_checkpointer_returns_an_async_postgres_saver_over_the_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()

    import app.agents.checkpointer as checkpointer_module

    checkpointer_module._pool = None
    try:
        saver = get_checkpointer()
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        assert isinstance(saver, AsyncPostgresSaver)
        assert saver.conn is get_checkpointer_pool()
    finally:
        checkpointer_module._pool = None
        get_settings.cache_clear()


async def _open_pool(app_db_url: str) -> AsyncConnectionPool:
    dsn = _checkpointer_dsn(app_db_url)
    pool = AsyncConnectionPool(
        dsn,
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    await pool.open()
    return pool


async def test_a_persisted_checkpoint_is_recovered_intact(app_db_url: str) -> None:
    """Un checkpoint guardado y recuperado por su `thread_id` es idéntico al guardado — sobre las
    tablas creadas por la migración `0005`, con el rol runtime `syntax_app` (sin `.setup()`)."""
    pool = await _open_pool(app_db_url)
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        saver = AsyncPostgresSaver(pool)
        thread_id = f"test-{uuid.uuid4()}"
        config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
        checkpoint = empty_checkpoint()

        await saver.aput(config, checkpoint, {}, {})
        tup = await saver.aget_tuple(config)

        assert tup is not None
        assert tup.checkpoint["id"] == checkpoint["id"]
    finally:
        await pool.close()


async def test_two_different_threads_do_not_mix_their_checkpoints(app_db_url: str) -> None:
    pool = await _open_pool(app_db_url)
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        saver = AsyncPostgresSaver(pool)
        thread_a = f"test-a-{uuid.uuid4()}"
        thread_b = f"test-b-{uuid.uuid4()}"
        config_a = {"configurable": {"thread_id": thread_a, "checkpoint_ns": ""}}
        config_b = {"configurable": {"thread_id": thread_b, "checkpoint_ns": ""}}
        checkpoint_a = empty_checkpoint()
        checkpoint_b = empty_checkpoint()

        await saver.aput(config_a, checkpoint_a, {}, {})
        await saver.aput(config_b, checkpoint_b, {}, {})

        tup_a = await saver.aget_tuple(config_a)

        assert tup_a is not None
        assert tup_a.checkpoint["id"] == checkpoint_a["id"]
        assert tup_a.checkpoint["id"] != checkpoint_b["id"]
    finally:
        await pool.close()


async def test_syntax_app_can_read_and_write_but_not_delete_or_create(app_db_url: str) -> None:
    """`syntax_app` puede INSERT/UPDATE/SELECT sobre las tablas de checkpoint, pero un DELETE o un
    CREATE TABLE adicional falla por permisos (least-privilege, migración `0005`)."""
    pool = await _open_pool(app_db_url)
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        saver = AsyncPostgresSaver(pool)
        thread_id = f"test-perms-{uuid.uuid4()}"
        config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
        await saver.aput(config, empty_checkpoint(), {}, {})  # INSERT/UPDATE ya cubiertos

        async with pool.connection() as conn:
            with pytest.raises(Exception, match="permission denied"):
                await conn.execute("DELETE FROM checkpoints WHERE thread_id = %s", (thread_id,))
            await conn.rollback()
            with pytest.raises(Exception, match="permission denied"):
                await conn.execute("CREATE TABLE checkpoint_intruso (x INT)")
            await conn.rollback()
    finally:
        await pool.close()


async def test_unreachable_postgres_fails_with_a_clear_error() -> None:
    """Un DSN de checkpointer que apunta a un Postgres inalcanzable falla con un error controlado
    (`PoolTimeout`, mensaje explícito), no una excepción críptica del driver."""
    pool = AsyncConnectionPool(
        "postgresql://syntax:syntax@localhost:59999/syntax",
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        timeout=1.0,
    )
    try:
        with pytest.raises(PoolTimeout):
            await pool.open(wait=True, timeout=1.0)
    finally:
        await pool.close()
