"""app.infra.db.repositories.base — repositorio base tenant-aware (CRUD app-level).

`BaseRepository` aporta la **1ª línea de defensa** del aislamiento: filtra por `tenant_id`
**explícitamente** en cada lectura/borrado, POR ENCIMA de la RLS (que es defensa en profundidad).
Anti-patrón: confiar solo en RLS. NOTA (design-review L5): primitiva **especulativa** — los repos
concretos que implementan los puertos de dominio nacen en el plan 10 y pueden remodelar esta base.
"""

import uuid
from typing import Protocol

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped


class TenantScoped(Protocol):
    """Modelo de negocio: tiene `id` y `tenant_id` (lo satisfacen las 7 tablas con TenantMixin)."""

    id: Mapped[uuid.UUID]
    tenant_id: Mapped[uuid.UUID]


class BaseRepository[T: TenantScoped]:
    """CRUD genérico filtrado por `tenant_id` sobre un modelo de negocio.

    :param session: sesión async (el llamante gestiona la transacción/commit).
    :param model: la clase ORM (p.ej. `Ticket`).
    """

    def __init__(self, session: AsyncSession, model: type[T]) -> None:
        self._session = session
        self._model = model

    async def get(self, entity_id: uuid.UUID, tenant_id: uuid.UUID) -> T | None:
        """Devuelve la fila `entity_id` **solo si** pertenece a `tenant_id`; si no, None."""
        stmt = select(self._model).where(
            self._model.id == entity_id, self._model.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list(self, tenant_id: uuid.UUID) -> list[T]:
        """Todas las filas de `tenant_id`, en orden determinista por `id` (contrato asertado)."""
        stmt = (
            select(self._model).where(self._model.tenant_id == tenant_id).order_by(self._model.id)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def add(self, entity: T) -> T:
        """Persiste `entity` (flush → surfacea IntegrityError); el commit lo hace el llamante."""
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity_id: uuid.UUID, tenant_id: uuid.UUID) -> bool:
        """Borra `entity_id` **solo dentro de** `tenant_id`. True si borró una fila, False si no."""
        stmt = (
            sql_delete(self._model)
            .where(self._model.id == entity_id, self._model.tenant_id == tenant_id)
            .returning(self._model.id)
        )
        deleted_id = (await self._session.execute(stmt)).scalar_one_or_none()
        return deleted_id is not None
