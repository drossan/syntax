"""Tests de integración de la migración inicial (tarea 06) — Postgres real (fixture test-DB).

Cubre: aplica limpia + extensión, 18 tablas, RLS solo en negocio, policy tenant_isolation,
drift (compare_metadata), vector(1536), fallo claro si db caída, idempotencia de upgrade,
downgrade→upgrade + rol preservado, rol no-superuser, GRANTs CRUD, MIGRATION_DATABASE_URL
ausente, meta-test de drift (dim de vector), reutilización de syntax_test y CHECK de rango.

Sin psycopg (no hay libpq): el acceso de mantenimiento usa asyncpg vía asyncio.run.
"""

import asyncio

import asyncpg
import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from app.infra.db.alembic_url import MIGRATION_DATABASE_URL_ENV, get_migration_database_url
from app.infra.db.base import Base
from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, Column, DateTime, MetaData, String, Table, Uuid, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

_IDENTITY = (
    "tenant",
    "user",
    "capability",
    "role",
    "role_capability",
    "user_role",
    "refresh_session",
    "auth_token",
)
_BUSINESS = (
    "ticket",
    "message",
    "attachment",
    "approval_task",
    "agent_run",
    "audit_log",
    "notification",
)
_KB = ("kb_document", "kb_chunk", "embedding")
_ALL_18 = _IDENTITY + _BUSINESS + _KB
_NON_BUSINESS = _IDENTITY + _KB


async def _scalar(engine: AsyncEngine, sql: str, **params: object) -> object:
    async with engine.connect() as conn:
        result = await conn.execute(text(sql), params)
        return result.scalar()


async def _count_public_tables(dsn: str, names: tuple[str, ...]) -> int:
    conn = await asyncpg.connect(dsn=dsn)
    try:
        return await conn.fetchval(
            "SELECT count(*) FROM pg_tables WHERE schemaname = 'public' AND tablename = ANY($1::text[])",
            list(names),
        )
    finally:
        await conn.close()


async def _role_count(dsn: str) -> int:
    conn = await asyncpg.connect(dsn=dsn)
    try:
        return await conn.fetchval("SELECT count(*) FROM pg_roles WHERE rolname = 'syntax_app'")
    finally:
        await conn.close()


async def test_migration_installs_vector_extension(superuser_engine: AsyncEngine) -> None:
    """La migración aplica limpia y deja la extensión vector instalada."""
    installed = await _scalar(
        superuser_engine, "SELECT count(*) FROM pg_extension WHERE extname = 'vector'"
    )
    assert installed == 1


async def test_all_18_tables_created(superuser_engine: AsyncEngine) -> None:
    """Se crean las 18 entidades de data-model."""
    async with superuser_engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
        tables = {row[0] for row in rows}
    assert set(_ALL_18) <= tables


async def test_rls_enabled_only_on_business_tables(superuser_engine: AsyncEngine) -> None:
    """relrowsecurity = true en las 7 de negocio y false en KB e identidad/RBAC."""
    async with superuser_engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT relname, relrowsecurity FROM pg_class WHERE relname = ANY(:names)"),
            {"names": list(_ALL_18)},
        )
        rls = dict(rows.all())
    for table in _BUSINESS:
        assert rls[table] is True, table
    for table in _NON_BUSINESS:
        assert rls[table] is False, table


async def test_business_tables_have_tenant_isolation_policy(superuser_engine: AsyncEngine) -> None:
    """Cada tabla de negocio tiene una policy tenant_isolation; ninguna KB/identidad la tiene."""
    async with superuser_engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT tablename FROM pg_policies WHERE policyname = 'tenant_isolation'")
        )
        with_policy = {row[0] for row in rows}
    assert set(_BUSINESS) <= with_policy
    assert with_policy.isdisjoint(_NON_BUSINESS)


async def test_embedding_column_is_vector_1536(superuser_engine: AsyncEngine) -> None:
    """La columna de embeddings es vector(1536)."""
    formatted = await _scalar(
        superuser_engine,
        "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
        "WHERE attrelid = 'embedding'::regclass AND attname = 'vector'",
    )
    assert formatted == "vector(1536)"


def _flatten(diff: list[object]) -> list[object]:
    """Aplana el diff de compare_metadata (agrupa los cambios de columna en sublistas)."""
    flat: list[object] = []
    for entry in diff:
        if isinstance(entry, list):
            flat.extend(entry)
        else:
            flat.append(entry)
    return flat


def _is_check_constraint_diff(entry: object) -> bool:
    """True si el diff es sobre un CHECK (viven SOLO en la migración, no en los modelos)."""
    return (
        isinstance(entry, tuple)
        and len(entry) == 2
        and entry[0] in ("add_constraint", "remove_constraint")
        and isinstance(entry[1], CheckConstraint)
    )


def _diff_against(sync_conn: object, metadata: MetaData) -> list[object]:
    context = MigrationContext.configure(sync_conn, opts={"compare_type": True})
    return _flatten(compare_metadata(context, metadata))


async def test_models_do_not_drift_from_schema(superuser_engine: AsyncEngine) -> None:
    """Los modelos no divergen del schema migrado (compare_metadata → diff vacío).

    Los CHECK de rango se excluyen: viven solo en la migración (decisión owner), no tienen
    representación en los modelos, así que no pueden 'divergir'. El gate cubre tablas,
    columnas, tipos (incl. dim de vector), índices, unicidades y FKs.
    """
    async with superuser_engine.connect() as conn:
        diff = await conn.run_sync(lambda c: _diff_against(c, Base.metadata))
    structural = [entry for entry in diff if not _is_check_constraint_diff(entry)]
    assert structural == [], f"drift inesperado: {structural}"


async def test_drift_gate_detects_vector_dim_change(superuser_engine: AsyncEngine) -> None:
    """El gate de drift detecta un cambio de dimensión de vector (sin falso negativo, H3)."""
    alt = MetaData()
    Table(
        "embedding",
        alt,
        Column("id", Uuid, primary_key=True),
        Column("chunk_id", Uuid),
        Column("model", String),
        Column("vector", Vector(768)),  # ≠ 1536 en la DB migrada
        Column("created_at", DateTime(timezone=True)),
    )
    async with superuser_engine.connect() as conn:
        diff = await conn.run_sync(lambda c: _diff_against(c, alt))
    modified_type_columns = [
        entry[3]
        for entry in diff
        if isinstance(entry, tuple) and entry and entry[0] == "modify_type"
    ]
    assert "vector" in modified_type_columns, f"no detectó el cambio de dim: {diff}"


def test_unreachable_db_fails_with_clear_error(check_reachable: object) -> None:
    """Si docker db no es alcanzable, la fixture falla con un error claro (no se salta)."""
    with pytest.raises(RuntimeError, match="no alcanzable"):
        check_reachable("postgresql://x:y@localhost:59999/postgres")  # type: ignore[operator]


def test_migration_url_missing_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """MIGRATION_DATABASE_URL ausente da un error claro (no un KeyError críptico)."""
    monkeypatch.delenv(MIGRATION_DATABASE_URL_ENV, raising=False)
    with pytest.raises(RuntimeError, match=MIGRATION_DATABASE_URL_ENV):
        get_migration_database_url()


def test_upgrade_head_is_idempotent(alembic_config: object) -> None:
    """upgrade head sobre una DB ya en head es no-op y no falla."""
    command.upgrade(alembic_config, "head")  # type: ignore[arg-type]


def test_downgrade_then_upgrade_reproduces_and_keeps_role(
    alembic_config: object, test_db_dsn: str, maintenance_dsn: str
) -> None:
    """downgrade base → tablas fuera pero rol vivo; re-upgrade head → schema reproducido."""
    command.downgrade(alembic_config, "base")  # type: ignore[arg-type]
    assert asyncio.run(_count_public_tables(test_db_dsn, _ALL_18)) == 0
    assert asyncio.run(_role_count(maintenance_dsn)) == 1  # el rol se gestiona fuera de Alembic
    command.upgrade(alembic_config, "head")  # type: ignore[arg-type]
    assert asyncio.run(_count_public_tables(test_db_dsn, _ALL_18)) == len(_ALL_18)


async def test_app_role_is_not_superuser_nor_bypass(superuser_engine: AsyncEngine) -> None:
    """El rol syntax_app no es superusuario ni bypassa RLS (premisa de ADR-0016)."""
    async with superuser_engine.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'syntax_app'")
            )
        ).one()
    assert row == (False, False)


async def test_app_role_creation_is_idempotent(superuser_engine: AsyncEngine) -> None:
    """Re-ejecutar el patrón del init script (CREATE ROLE idempotente) no falla."""
    idempotent = text(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'syntax_app') THEN "
        "CREATE ROLE syntax_app NOSUPERUSER NOBYPASSRLS LOGIN; END IF; END $$;"
    )
    async with superuser_engine.begin() as conn:
        await conn.execute(idempotent)
        await conn.execute(idempotent)
        count = (
            await conn.execute(text("SELECT count(*) FROM pg_roles WHERE rolname = 'syntax_app'"))
        ).scalar()
    assert count == 1


async def test_test_database_is_reused_not_duplicated(superuser_engine: AsyncEngine) -> None:
    """La fixture reutiliza syntax_test si ya existe (no falla por DuplicateDatabase)."""
    count = await _scalar(
        superuser_engine, "SELECT count(*) FROM pg_database WHERE datname = 'syntax_test'"
    )
    assert count == 1


async def test_app_role_has_crud_on_all_18_tables(superuser_engine: AsyncEngine) -> None:
    """syntax_app tiene SELECT/INSERT/UPDATE/DELETE en las 18 tablas."""
    async with superuser_engine.connect() as conn:
        for table in _ALL_18:
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                granted = await conn.execute(
                    text("SELECT has_table_privilege('syntax_app', :t, :p)"),
                    {"t": table, "p": privilege},
                )
                assert granted.scalar() is True, f"{table}/{privilege}"


async def _insert_tenant(conn: object) -> object:
    result = await conn.execute(  # type: ignore[attr-defined]
        text(
            "INSERT INTO tenant (id, slug, name, status, created_at, updated_at) "
            "VALUES (gen_random_uuid(), gen_random_uuid()::text, 'chk', 'active', now(), now()) "
            "RETURNING id"
        )
    )
    return result.scalar()


@pytest.mark.parametrize(("csat", "rejected"), [(5, False), (6, True)])
async def test_ticket_csat_check_range(
    superuser_engine: AsyncEngine, csat: int, rejected: bool
) -> None:
    """CHECK ck_ticket_csat_range: csat 1..5 se acepta, fuera de rango se rechaza."""
    insert = text(
        "INSERT INTO ticket (id, tenant_id, subject, status, priority, csat, created_at, updated_at) "
        "VALUES (gen_random_uuid(), :t, 'subj', 'new', 'normal', :csat, now(), now())"
    )
    async with superuser_engine.connect() as conn:
        tenant_id = await _insert_tenant(conn)
        if rejected:
            with pytest.raises(IntegrityError):
                await conn.execute(insert, {"t": tenant_id, "csat": csat})
        else:
            await conn.execute(insert, {"t": tenant_id, "csat": csat})
        await conn.rollback()


@pytest.mark.parametrize(("confidence", "rejected"), [(1.0, False), (1.5, True)])
async def test_agent_run_confidence_check_range(
    superuser_engine: AsyncEngine, confidence: float, rejected: bool
) -> None:
    """CHECK ck_agent_run_confidence_range: confidence 0..1 se acepta, fuera se rechaza."""
    async with superuser_engine.connect() as conn:
        tenant_id = await _insert_tenant(conn)
        ticket_id = (
            await conn.execute(
                text(
                    "INSERT INTO ticket (id, tenant_id, subject, status, priority, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :t, 'subj', 'new', 'normal', now(), now()) RETURNING id"
                ),
                {"t": tenant_id},
            )
        ).scalar()
        insert = text(
            "INSERT INTO agent_run "
            "(id, tenant_id, ticket_id, langgraph_thread_id, run_seq, status, confidence, escalated, created_at) "
            "VALUES (gen_random_uuid(), :t, :ticket, 'thread', 1, 'queued', :conf, false, now())"
        )
        if rejected:
            with pytest.raises(IntegrityError):
                await conn.execute(
                    insert, {"t": tenant_id, "ticket": ticket_id, "conf": confidence}
                )
        else:
            await conn.execute(insert, {"t": tenant_id, "ticket": ticket_id, "conf": confidence})
        await conn.rollback()
