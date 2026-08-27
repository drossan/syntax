"""Tests de integración de la migración 0002 (backend-routers-core-01) — Postgres real.

1:1 con el `## Scenarios (Gherkin)` de la tarea: la migración aplica limpia sobre el esquema de
`database-foundation`, `user` pierde `tenant_id`/`status` (email único global), `user_tenant` existe
con status por membership + unicidad (user_id, tenant_id) + cascada al borrar el user, `refresh_session`
exige `tenant_id`, `tenant.auto_approve` por defecto `false`, downgrade revierte limpio, y los modelos
no divergen del schema (`compare_metadata`).
"""

import uuid

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from app.infra.db.base import Base
from sqlalchemy import CheckConstraint, MetaData, text
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


async def _insert_user(conn: object, *, email: str | None = None) -> uuid.UUID:
    email = email or f"u-{uuid.uuid4()}@example.com"
    result = await conn.execute(  # type: ignore[attr-defined]
        text(
            'INSERT INTO "user" (id, email, created_at, updated_at) '
            "VALUES (gen_random_uuid(), :email, now(), now()) RETURNING id"
        ),
        {"email": email},
    )
    return result.scalar()  # type: ignore[no-any-return]


async def test_user_has_no_tenant_id_nor_status_and_email_is_globally_unique(
    superuser_engine: AsyncEngine,
) -> None:
    """user ya no tiene tenant_id ni status, y el email es único global."""
    async with superuser_engine.connect() as conn:
        columns = await conn.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_name = 'user'")
        )
        names = {row[0] for row in columns}
        assert "tenant_id" not in names
        assert "status" not in names

        constraints = await conn.execute(
            text(
                "SELECT conname FROM pg_constraint WHERE conrelid = 'user'::regclass "
                "AND contype = 'u'"
            )
        )
        assert "uq_user_email" in {row[0] for row in constraints}


async def test_email_is_unique_globally_not_per_tenant(superuser_engine: AsyncEngine) -> None:
    """Un segundo User con el mismo email falla por el UniqueConstraint(email) global."""
    email = f"dup-{uuid.uuid4()}@example.com"
    async with superuser_engine.connect() as conn:
        await _insert_user(conn, email=email)
        with pytest.raises(IntegrityError):
            await _insert_user(conn, email=email)
        await conn.rollback()


async def test_user_tenant_persists_and_is_queryable_by_user_or_tenant(
    superuser_engine: AsyncEngine,
) -> None:
    """user_tenant existe con status por membership, consultable por user_id o por tenant_id."""
    async with superuser_engine.connect() as conn:
        user_id = await _insert_user(conn)
        tenant_id = await _insert_tenant(conn)
        await conn.execute(
            text(
                "INSERT INTO user_tenant (user_id, tenant_id, status, created_at) "
                "VALUES (:u, :t, 'active', now())"
            ),
            {"u": user_id, "t": tenant_id},
        )
        by_user = (
            await conn.execute(
                text("SELECT tenant_id FROM user_tenant WHERE user_id = :u"), {"u": user_id}
            )
        ).scalar()
        by_tenant = (
            await conn.execute(
                text("SELECT user_id FROM user_tenant WHERE tenant_id = :t"), {"t": tenant_id}
            )
        ).scalar()
        assert by_user == tenant_id
        assert by_tenant == user_id
        await conn.rollback()


async def test_a_user_cannot_have_two_memberships_to_the_same_tenant(
    superuser_engine: AsyncEngine,
) -> None:
    """Insertar una segunda membership del mismo usuario al mismo tenant falla por unicidad (PK)."""
    async with superuser_engine.connect() as conn:
        user_id = await _insert_user(conn)
        tenant_id = await _insert_tenant(conn)
        insert = text(
            "INSERT INTO user_tenant (user_id, tenant_id, status, created_at) "
            "VALUES (:u, :t, 'active', now())"
        )
        await conn.execute(insert, {"u": user_id, "t": tenant_id})
        with pytest.raises(IntegrityError):
            await conn.execute(insert, {"u": user_id, "t": tenant_id})
        await conn.rollback()


async def test_deleting_a_user_cascades_its_memberships(superuser_engine: AsyncEngine) -> None:
    """Borrar un User elimina en cascada sus filas user_tenant (ON DELETE CASCADE)."""
    async with superuser_engine.connect() as conn:
        user_id = await _insert_user(conn)
        tenant_id = await _insert_tenant(conn)
        await conn.execute(
            text(
                "INSERT INTO user_tenant (user_id, tenant_id, status, created_at) "
                "VALUES (:u, :t, 'active', now())"
            ),
            {"u": user_id, "t": tenant_id},
        )
        await conn.execute(text('DELETE FROM "user" WHERE id = :u'), {"u": user_id})
        remaining = (
            await conn.execute(
                text("SELECT count(*) FROM user_tenant WHERE user_id = :u"), {"u": user_id}
            )
        ).scalar()
        assert remaining == 0
        await conn.rollback()


async def test_a_tenant_with_memberships_or_sessions_cannot_be_deleted(
    superuser_engine: AsyncEngine,
) -> None:
    """Un tenant con al menos una fila user_tenant no puede borrarse (ON DELETE RESTRICT)."""
    async with superuser_engine.connect() as conn:
        user_id = await _insert_user(conn)
        tenant_id = await _insert_tenant(conn)
        await conn.execute(
            text(
                "INSERT INTO user_tenant (user_id, tenant_id, status, created_at) "
                "VALUES (:u, :t, 'active', now())"
            ),
            {"u": user_id, "t": tenant_id},
        )
        with pytest.raises(IntegrityError):
            await conn.execute(text("DELETE FROM tenant WHERE id = :t"), {"t": tenant_id})
        await conn.rollback()


async def test_refresh_session_requires_tenant_id(superuser_engine: AsyncEngine) -> None:
    """Insertar una refresh_session sin tenant_id falla (NOT NULL)."""
    async with superuser_engine.connect() as conn:
        user_id = await _insert_user(conn)
        insert = text(
            "INSERT INTO refresh_session "
            "(id, user_id, token_hash, family_id, status, expires_at, created_at) "
            "VALUES (gen_random_uuid(), :u, :hash, gen_random_uuid(), 'active', now(), now())"
        )
        with pytest.raises(IntegrityError):
            await conn.execute(insert, {"u": user_id, "hash": str(uuid.uuid4())})
        await conn.rollback()


async def test_refresh_session_with_tenant_id_persists(superuser_engine: AsyncEngine) -> None:
    """Camino feliz: refresh_session con tenant_id se persiste sin error."""
    async with superuser_engine.connect() as conn:
        user_id = await _insert_user(conn)
        tenant_id = await _insert_tenant(conn)
        insert = text(
            "INSERT INTO refresh_session "
            "(id, user_id, tenant_id, token_hash, family_id, status, expires_at, created_at) "
            "VALUES (gen_random_uuid(), :u, :t, :hash, gen_random_uuid(), 'active', now(), now())"
        )
        await conn.execute(insert, {"u": user_id, "t": tenant_id, "hash": str(uuid.uuid4())})
        await conn.rollback()


async def test_tenant_auto_approve_defaults_to_false(superuser_engine: AsyncEngine) -> None:
    """Un tenant insertado sin especificar auto_approve lee auto_approve = false."""
    async with superuser_engine.connect() as conn:
        tenant_id = await _insert_tenant(conn)
        value = (
            await conn.execute(
                text("SELECT auto_approve FROM tenant WHERE id = :t"), {"t": tenant_id}
            )
        ).scalar()
        assert value is False
        await conn.rollback()


def test_downgrade_reverts_identity_migration_cleanly(alembic_config: object) -> None:
    """downgrade -1 revierte 0002: user recupera tenant_id/status/unique compuesto, y
    user_tenant/refresh_session.tenant_id/tenant.auto_approve desaparecen."""
    command.downgrade(alembic_config, "-1")  # type: ignore[arg-type]
    command.upgrade(alembic_config, "head")  # type: ignore[arg-type]


def _flatten(diff: list[object]) -> list[object]:
    flat: list[object] = []
    for entry in diff:
        if isinstance(entry, list):
            flat.extend(entry)
        else:
            flat.append(entry)
    return flat


def _is_check_constraint_diff(entry: object) -> bool:
    return (
        isinstance(entry, tuple)
        and len(entry) == 2
        and entry[0] in ("add_constraint", "remove_constraint")
        and isinstance(entry[1], CheckConstraint)
    )


def _is_checkpoint_table_diff(entry: object) -> bool:
    """True si el diff es sobre una tabla/índice `checkpoint*` (tarea `backend-agent-graph-07`).

    Mismo filtro que `test_migration.py::_is_checkpoint_table_diff` — este fichero mantiene su PROPIA
    copia del gate de drift (histórico, `database-foundation-06`), así que necesita el mismo allowlist:
    las 4 tablas de `langgraph-checkpoint-postgres` (migración `0005`) no tienen modelo ORM a propósito.
    """
    if not isinstance(entry, tuple) or len(entry) != 2:
        return False
    kind, obj = entry
    if kind == "remove_table":
        return bool(getattr(obj, "name", "").startswith("checkpoint"))
    if kind == "remove_index":
        table = getattr(obj, "table", None)
        return bool(table is not None and getattr(table, "name", "").startswith("checkpoint"))
    return False


def _diff_against(sync_conn: object, metadata: MetaData) -> list[object]:
    context = MigrationContext.configure(sync_conn, opts={"compare_type": True})
    return _flatten(compare_metadata(context, metadata))


async def test_models_do_not_drift_from_schema_after_identity_migration(
    superuser_engine: AsyncEngine,
) -> None:
    """Los modelos (User/UserTenant/RefreshSession/Tenant actualizados) no divergen del schema
    migrado tras 0002 (mismo gate de drift que database-foundation 06)."""
    async with superuser_engine.connect() as conn:
        diff = await conn.run_sync(lambda c: _diff_against(c, Base.metadata))
    structural = [
        entry
        for entry in diff
        if not _is_check_constraint_diff(entry) and not _is_checkpoint_table_diff(entry)
    ]
    assert structural == [], f"drift inesperado: {structural}"
