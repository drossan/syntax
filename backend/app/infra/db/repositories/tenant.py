"""app.infra.db.repositories.tenant — adaptador SQLAlchemy de `TenantRepository`.

`Tenant` no lleva `TenantMixin` (es la tabla RAÍZ del aislamiento, no una tabla de negocio con RLS) —
`BaseRepository` no aplica: no hay `tenant_id` propio que filtrar. Consultas directas sobre
`app.infra.db.models.Tenant`, envolviendo cualquier excepción de SQLAlchemy en `PortError` (nunca deja
pasar una excepción de infra cruda al dominio).
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.enums import TenantStatus
from app.domain.entities.identity import Tenant
from app.domain.errors import PortError
from app.domain.ports.repositories import PageResult
from app.infra.db.models import Tenant as TenantModel
from app.infra.db.models.enums import TenantStatus as TenantStatusOrm
from app.infra.db.repositories._enum_bridge import to_domain, to_orm


def _to_domain(row: TenantModel) -> Tenant:
    return Tenant(
        id=row.id,
        slug=row.slug,
        name=row.name,
        status=to_domain(TenantStatus, row.status),
        auto_approve=row.auto_approve,
        ai_auto_draft=row.ai_auto_draft,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyTenantRepository:
    """Adaptador de `TenantRepository` (`app.domain.ports.repositories`)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, tenant_id: uuid.UUID) -> Tenant | None:
        try:
            row = await self._session.get(TenantModel, tenant_id)
        except Exception as exc:
            raise PortError("fallo al leer tenant") from exc
        return _to_domain(row) if row is not None else None

    async def add(self, tenant: Tenant) -> Tenant:
        row = TenantModel(
            id=tenant.id,
            slug=tenant.slug,
            name=tenant.name,
            status=to_orm(TenantStatusOrm, tenant.status),
            auto_approve=tenant.auto_approve,
            ai_auto_draft=tenant.ai_auto_draft,
        )
        self._session.add(row)
        try:
            await self._session.flush()
        except Exception as exc:
            raise PortError("fallo al crear tenant") from exc
        return _to_domain(row)

    async def update(self, tenant: Tenant) -> Tenant:
        try:
            row = await self._session.get(TenantModel, tenant.id)
        except Exception as exc:
            raise PortError("fallo al leer tenant") from exc
        if row is None:
            raise PortError(f"tenant {tenant.id} no existe")
        row.slug = tenant.slug
        row.name = tenant.name
        row.status = to_orm(TenantStatusOrm, tenant.status)
        row.auto_approve = tenant.auto_approve
        row.ai_auto_draft = tenant.ai_auto_draft
        try:
            await self._session.flush()
            await self._session.refresh(row)
        except Exception as exc:
            raise PortError("fallo al actualizar tenant") from exc
        return _to_domain(row)

    async def list(self, *, page: int, page_size: int) -> PageResult[Tenant]:
        offset = (page - 1) * page_size
        try:
            total = (
                await self._session.execute(select(func.count()).select_from(TenantModel))
            ).scalar_one()
            rows = (
                await self._session.execute(
                    select(TenantModel).order_by(TenantModel.slug).offset(offset).limit(page_size)
                )
            ).scalars()
            items = [_to_domain(row) for row in rows]
        except Exception as exc:
            raise PortError("fallo al listar tenants") from exc
        return PageResult(items=items, total=total)
