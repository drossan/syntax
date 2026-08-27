"""app.agents.checkpointer — `PostgresSaver` del grafo (ADR-0007).

Pool `psycopg` singleton perezoso por proceso (mismo patrón que
`app.infra.db.session.get_engine()`/`get_sessionmaker()`; sin efectos en import). DSN derivado de
`settings.database_url` quitándole `+asyncpg` — `psycopg` no entiende ese driver (es el de `asyncpg`,
el runtime del resto de la app).

La migración Alembic `0005_agent_checkpoint_tables` (DSN superuser) crea las 4 tablas de checkpoint y
otorga a `syntax_app` (rol runtime, SIN `CREATE`) solo `SELECT`/`INSERT`/`UPDATE`. Por eso este módulo
**NUNCA llama a `AsyncPostgresSaver.setup()`**: `syntax_app` no tiene privilegio para el `CREATE TABLE
IF NOT EXISTS` que `.setup()` intenta — la migración es la única fuente de verdad del schema.

⚠️ Riesgo (ver la migración `0005`): el DDL de las tablas es un detalle interno no-público de
`langgraph-checkpoint-postgres`. Re-verificar en cualquier bump de la dependencia.
"""

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool

from app.core.config import get_settings

_pool: AsyncConnectionPool[AsyncConnection[DictRow]] | None = None


def _checkpointer_dsn(database_url: str) -> str:
    """`postgresql+asyncpg://...` → `postgresql://...` (`psycopg` no entiende el driver `+asyncpg`)."""
    return database_url.replace("+asyncpg", "")


def get_checkpointer_pool() -> AsyncConnectionPool[AsyncConnection[DictRow]]:
    """Pool `psycopg` singleton por proceso, creado una vez y perezosamente (`open=False`: la
    conexión real se abre en el primer uso, no aquí — sin efectos en import)."""
    global _pool
    if _pool is None:
        dsn = _checkpointer_dsn(get_settings().database_url)
        _pool = AsyncConnectionPool[AsyncConnection[DictRow]](
            dsn,
            open=False,
            kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        )
    return _pool


def get_checkpointer() -> AsyncPostgresSaver:
    """`AsyncPostgresSaver` construido sobre el pool singleton — NO llama a `.setup()` (ver arriba)."""
    return AsyncPostgresSaver(get_checkpointer_pool())
