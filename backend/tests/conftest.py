"""conftest.py — fixtures compartidas de pytest (árbol `tests/`).

Infra de test de INTEGRACIÓN contra el Postgres de docker-compose (`db`). Usa **asyncpg**
(el driver runtime del proyecto) para el mantenimiento — evita depender de `libpq`/psycopg.

- `migrated_database` (session): asegura el rol `syntax_app` (idempotente, espeja el init
  script), crea/reutiliza la DB `syntax_test` y corre `alembic upgrade head`. Si `db` no
  está alcanzable, **falla con un error claro** (no se salta en silencio).
- `superuser_engine`: engine async como superuser (RLS no aplica) para inspección de schema.
- `app_engine`: engine async como `syntax_app` (no-superuser → RLS aplica) para los tests de
  aislamiento (footgun, tarea 07).

La fixture reutiliza `syntax_test` entre ejecuciones (`upgrade head` es idempotente vía
`alembic_version`). El reset del cache de `get_settings()` vive en `test_config.py` (autouse local).
"""

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import NullPool
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

_BACKEND_ROOT = Path(__file__).resolve().parent.parent

_HOST = os.environ.get("TEST_DB_HOST", "localhost")
_PORT = int(os.environ.get("TEST_DB_PORT", "5432"))
_SUPERUSER = "syntax"
_SUPERUSER_PW = "syntax"
_APP_ROLE = "syntax_app"
_APP_ROLE_PW = "syntax_app"
_TEST_DB = "syntax_test"


def asyncpg_dsn(dbname: str, user: str = _SUPERUSER, password: str = _SUPERUSER_PW) -> str:
    """DSN para `asyncpg.connect` (sin sufijo +driver)."""
    return f"postgresql://{user}:{password}@{_HOST}:{_PORT}/{dbname}"


def sqlalchemy_url(dbname: str, user: str, password: str) -> str:
    """DSN asyncpg para SQLAlchemy (`create_async_engine`)."""
    return f"postgresql+asyncpg://{user}:{password}@{_HOST}:{_PORT}/{dbname}"


def superuser_test_url() -> str:
    """URL SQLAlchemy de `syntax_test` como superuser (RLS NO aplica)."""
    return sqlalchemy_url(_TEST_DB, _SUPERUSER, _SUPERUSER_PW)


def app_test_url() -> str:
    """URL SQLAlchemy de `syntax_test` como `syntax_app` (no-superuser → RLS aplica)."""
    return sqlalchemy_url(_TEST_DB, _APP_ROLE, _APP_ROLE_PW)


async def _try_connect(dsn: str) -> None:
    conn = await asyncpg.connect(dsn=dsn, timeout=3)
    await conn.close()


def assert_database_reachable(dsn: str) -> None:
    """Falla con un error CLARO si Postgres no está alcanzable (no se salta en silencio)."""
    try:
        asyncio.run(_try_connect(dsn))
    except (TimeoutError, OSError, asyncpg.PostgresError) as exc:
        raise RuntimeError(
            f"Postgres no alcanzable ({dsn}) — arranca la DB de test con "
            "`docker compose -f backend/docker-compose.yml up -d db`."
        ) from exc


async def _ensure_app_role() -> None:
    conn = await asyncpg.connect(dsn=asyncpg_dsn("postgres"))
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1", _APP_ROLE)
        if exists is None:
            await conn.execute(
                f"CREATE ROLE {_APP_ROLE} NOSUPERUSER NOBYPASSRLS LOGIN PASSWORD '{_APP_ROLE_PW}'"
            )
        else:
            await conn.execute(f"ALTER ROLE {_APP_ROLE} PASSWORD '{_APP_ROLE_PW}'")
    finally:
        await conn.close()


async def _create_test_database() -> None:
    conn = await asyncpg.connect(dsn=asyncpg_dsn("postgres"))
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", _TEST_DB)
        if exists is None:
            await conn.execute(f"CREATE DATABASE {_TEST_DB} OWNER {_SUPERUSER}")
    finally:
        await conn.close()


def run_migrations(target_db: str) -> None:
    """Corre `alembic upgrade head` contra `target_db` (env.py lee MIGRATION_DATABASE_URL)."""
    config = Config(str(_BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))
    os.environ["MIGRATION_DATABASE_URL"] = sqlalchemy_url(target_db, _SUPERUSER, _SUPERUSER_PW)
    command.upgrade(config, "head")


@pytest.fixture(scope="session")
def migrated_database() -> Iterator[str]:
    """DB `syntax_test` migrada a head (rol app + create + upgrade). Falla claro si `db` no está."""
    assert_database_reachable(asyncpg_dsn("postgres"))
    asyncio.run(_ensure_app_role())
    asyncio.run(_create_test_database())
    run_migrations(_TEST_DB)
    yield superuser_test_url()


@pytest.fixture(scope="session")
def maintenance_dsn() -> str:
    """DSN asyncpg a la DB de mantenimiento (postgres) como superuser."""
    return asyncpg_dsn("postgres")


@pytest.fixture(scope="session")
def test_db_dsn() -> str:
    """DSN asyncpg a `syntax_test` como superuser."""
    return asyncpg_dsn(_TEST_DB)


@pytest.fixture(scope="session")
def check_reachable() -> object:
    """Expone `assert_database_reachable` a los tests (evita importar el conftest)."""
    return assert_database_reachable


@pytest.fixture(scope="session")
def alembic_config(migrated_database: str) -> Config:
    """Config de Alembic apuntando a `syntax_test` (para tests de up/downgrade)."""
    config = Config(str(_BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))
    os.environ["MIGRATION_DATABASE_URL"] = superuser_test_url()
    return config


@pytest_asyncio.fixture
async def superuser_engine(migrated_database: str) -> AsyncIterator[AsyncEngine]:
    """Engine async como superuser sobre `syntax_test` (para inspección de schema; RLS no aplica)."""
    engine = create_async_engine(migrated_database, poolclass=NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()
