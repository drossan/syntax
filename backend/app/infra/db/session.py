"""app.infra.db.session — engine/sessionmaker async (rol syntax_app) + contexto RLS.

El engine conecta como el rol runtime **`syntax_app`** (no-superuser → las políticas RLS
aplican de verdad, ADR-0016). `tenant_scope`/`global_scope` fijan el contexto de aislamiento
con **alcance transaccional** (`set_config(..., true)`) para evitar el **footgun** del pool:

  ⚠️ `SET app.tenant_id` a nivel de CONEXIÓN sobre un pool asyncpg **arrastra** el tenant a la
  siguiente request que reutilice la conexión → fuga cross-tenant. La mitigación es fijar el GUC
  con alcance **transaccional** (tercer arg `true` de `set_config`), que se descarta al COMMIT o
  ROLLBACK. `SET LOCAL` no admite bind params, de ahí `set_config('app.tenant_id', $1, true)`.

Sin efectos en import: el engine/sessionmaker se construyen perezosamente desde `get_settings()`.
RLS es defensa en profundidad; el filtro app-level de los repos (08) es la primera línea.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Engine async (rol runtime `syntax_app`), creado una vez y perezosamente."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """`async_sessionmaker(expire_on_commit=False)`, perezoso (los objetos sobreviven al commit)."""
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """Cede un `AsyncSession` por request (lo inyecta `deps.get_db_session`, tarea 09)."""
    async with get_sessionmaker()() as session:
        yield session


def _coerce_tenant_uuid(tenant_id: uuid.UUID | str) -> uuid.UUID:
    """Valida que `tenant_id` sea un UUID → error CONTROLADO (ValueError), no crudo de Postgres."""
    if isinstance(tenant_id, uuid.UUID):
        return tenant_id
    try:
        return uuid.UUID(str(tenant_id))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"tenant_id no es un UUID válido: {tenant_id!r}") from exc


@asynccontextmanager
async def tenant_scope(
    session: AsyncSession, tenant_id: uuid.UUID | str
) -> AsyncIterator[AsyncSession]:
    """Abre una transacción con `app.tenant_id` fijado → RLS filtra por ese tenant.

    :param session: sesión async sin transacción abierta.
    :param tenant_id: UUID del tenant (str o `uuid.UUID`); se valida antes de tocar la DB.
    :raises ValueError: si `tenant_id` no es un UUID válido (error controlado).

    El GUC se fija con `set_config(..., true)` (alcance transaccional): se descarta al cerrar la
    transacción (commit o rollback), de modo que la conexión reutilizada del pool **no** arrastra
    el contexto (footgun). Bind-safe: `SET LOCAL` no admite parámetros.
    """
    validated = _coerce_tenant_uuid(tenant_id)
    async with session.begin():
        await session.execute(
            text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(validated)}
        )
        yield session


@asynccontextmanager
async def global_scope(session: AsyncSession) -> AsyncIterator[AsyncSession]:
    """Abre una transacción con el bypass de RLS activado (ámbito `global` de Soporte).

    Fija `app.bypass_rls = 'on'` con alcance transaccional; el bypass **no** persiste en la
    conexión del pool. Solo el literal `'on'` activa el bypass (ver el predicado de la policy).
    La autorización (quién puede usar `global`) es del plan de dominio (10).
    """
    async with session.begin():
        await session.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        yield session
