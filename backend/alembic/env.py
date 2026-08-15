"""alembic/env.py — entorno de migraciones (online async).

Resuelve la URL desde `MIGRATION_DATABASE_URL` (rol superuser) vía
`app.infra.db.alembic_url.get_migration_database_url` (fallo claro si falta). Importa
`app.infra.db.models` para registrar las 18 tablas en `Base.metadata` (target del
autogenerate y del drift-test). Corre síncrono sobre una conexión async (`run_sync`).
"""

import asyncio
from logging.config import fileConfig

import app.infra.db.models  # noqa: F401 — registra TODOS los modelos en Base.metadata
from alembic import context
from app.infra.db.alembic_url import get_migration_database_url
from app.infra.db.base import Base
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# La URL viene del entorno (no de alembic.ini): least-privilege + sin secretos en repo.
config.set_main_option("sqlalchemy.url", get_migration_database_url())

target_metadata = Base.metadata


def do_run_migrations(connection: Connection) -> None:
    """Configura el contexto y ejecuta las migraciones (sobre una conexión sync)."""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Modo online async: engine asyncpg + `run_sync` para correr Alembic (síncrono)."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_offline() -> None:
    """Modo offline: genera SQL sin conexión (URL literal)."""
    context.configure(
        url=get_migration_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
