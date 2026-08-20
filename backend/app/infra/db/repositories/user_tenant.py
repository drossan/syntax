"""app.infra.db.repositories.user_tenant — adaptador SQLAlchemy de `UserTenantMembershipRepository`.

PK compuesta natural (`user_id`, `tenant_id`) — `get`/`update` operan sobre esa clave, no un `id`
sintético. `list_by_tenant` pagina (lo usa `admin_users`, tarea 06); `list_by_user` no (el número de
tenants de un usuario es acotado).
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.enums import UserStatus
from app.domain.entities.identity import UserTenantMembership
from app.domain.errors import PortError
from app.domain.ports.repositories import PageResult
from app.infra.db.models import UserTenant as UserTenantModel
from app.infra.db.models.enums import UserStatus as UserStatusOrm
from app.infra.db.repositories._enum_bridge import to_domain, to_orm


def _to_domain(row: UserTenantModel) -> UserTenantMembership:
    return UserTenantMembership(
        user_id=row.user_id,
        tenant_id=row.tenant_id,
        status=to_domain(UserStatus, row.status),
        created_at=row.created_at,
    )


class SqlAlchemyUserTenantMembershipRepository:
    """Adaptador de `UserTenantMembershipRepository` (`app.domain.ports.repositories`)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: uuid.UUID, tenant_id: uuid.UUID) -> UserTenantMembership | None:
        try:
            row = await self._session.get(UserTenantModel, (user_id, tenant_id))
        except Exception as exc:
            raise PortError("fallo al leer membership") from exc
        return _to_domain(row) if row is not None else None

    async def list_by_user(self, user_id: uuid.UUID) -> list[UserTenantMembership]:
        try:
            rows = (
                await self._session.execute(
                    select(UserTenantModel).where(UserTenantModel.user_id == user_id)
                )
            ).scalars()
        except Exception as exc:
            raise PortError("fallo al listar membresías del usuario") from exc
        return [_to_domain(row) for row in rows]

    async def list_by_tenant(
        self, tenant_id: uuid.UUID, *, page: int, page_size: int
    ) -> PageResult[UserTenantMembership]:
        offset = (page - 1) * page_size
        try:
            total = (
                await self._session.execute(
                    select(func.count())
                    .select_from(UserTenantModel)
                    .where(UserTenantModel.tenant_id == tenant_id)
                )
            ).scalar_one()
            rows = (
                await self._session.execute(
                    select(UserTenantModel)
                    .where(UserTenantModel.tenant_id == tenant_id)
                    .order_by(UserTenantModel.created_at)
                    .offset(offset)
                    .limit(page_size)
                )
            ).scalars()
            items = [_to_domain(row) for row in rows]
        except Exception as exc:
            raise PortError("fallo al listar membresías del tenant") from exc
        return PageResult(items=items, total=total)

    async def add(self, membership: UserTenantMembership) -> UserTenantMembership:
        row = UserTenantModel(
            user_id=membership.user_id,
            tenant_id=membership.tenant_id,
            status=to_orm(UserStatusOrm, membership.status),
        )
        self._session.add(row)
        try:
            await self._session.flush()
        except Exception as exc:
            raise PortError("fallo al crear membership (¿ya existe?)") from exc
        return _to_domain(row)

    async def update(self, membership: UserTenantMembership) -> UserTenantMembership:
        try:
            row = await self._session.get(
                UserTenantModel, (membership.user_id, membership.tenant_id)
            )
        except Exception as exc:
            raise PortError("fallo al leer membership") from exc
        if row is None:
            raise PortError(f"membership ({membership.user_id}, {membership.tenant_id}) no existe")
        row.status = to_orm(UserStatusOrm, membership.status)
        try:
            await self._session.flush()
        except Exception as exc:
            raise PortError("fallo al actualizar membership") from exc
        return _to_domain(row)
