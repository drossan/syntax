"""app.core.deps — dependencias FastAPI comunes (punto de composición de la capa API).

En esta fase (plan de capa DB) solo se materializa `get_db_session` (cede una `AsyncSession` por
request). El resto del guión —`get_tenant_context`, `get_current_subject`, `require_capability`
(RBAC)— nace en el plan de dominio (10). Anti-patrón: resolver permisos desde el JWT; abrir sesiones
DB fuera del ciclo de request; capturar el tenant en estado global compartido entre requests.
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db.session import get_session


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Dependency que cede una `AsyncSession` por request y la cierra (delega en `session.py`).

    El contexto de tenant para RLS (`tenant_scope`) lo aplicará `get_tenant_context` (plan 10);
    aquí solo se provee la sesión.
    """
    async for session in get_session():
        yield session
