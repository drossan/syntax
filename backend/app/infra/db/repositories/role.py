"""app.infra.db.repositories.role — adaptador SQLAlchemy de `RoleRepository`.

`effective_capabilities(user_id, tenant_id)` resuelve vía join `user_role`→`role_capability`→
`capability`, incluyendo asignaciones de ámbito `tenant` (`user_role.tenant_id = tenant_id`) Y de
ámbito `global` (`user_role.tenant_id IS NULL` — Soporte, aplica en cualquier sesión). Acotar por
`tenant_id` es un fix de seguridad (scenario-coverage): sin él, un usuario con roles distintos en dos
tenants filtraría capacidades de un tenant a la sesión activa en otro.

El `scope` de cada tupla `(capability, scope)` efectiva se deriva de la ASIGNACIÓN
(`user_role.tenant_id IS NULL` → `"global"`, si no → `"tenant"`), **no** de `capability.scope`
(catálogo): el catálogo declara el ámbito MÁXIMO permitido para esa capacidad (lo valida
`rbac_service.validate_role_composition` al componer un rol custom), pero la MISMA capacidad puede
llegar a un subject por dos vías distintas (un rol `system` global y un rol `tenant`), y
`Subject.capabilities` necesita distinguir ambas — bug real encontrado en `backend-routers-core-05`
al conectar el router `auth`: leer `capability.scope` colapsaba ambas vías a un único valor fijo,
rompiendo la precedencia `global > tenant` de `get_tenant_context` cuando el subject tenía la misma
capacidad concedida en los dos ámbitos.
"""

import uuid

from sqlalchemy import delete, insert, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.enums import CapabilityScope, RoleKind
from app.domain.entities.identity import Capability, Role
from app.domain.errors import PortError
from app.infra.db.models import Capability as CapabilityModel
from app.infra.db.models import Role as RoleModel
from app.infra.db.models import RoleCapability as RoleCapabilityModel
from app.infra.db.models import UserRole as UserRoleModel
from app.infra.db.models.enums import RoleKind as RoleKindOrm
from app.infra.db.repositories._enum_bridge import to_domain, to_orm


def _role_to_domain(row: RoleModel) -> Role:
    return Role(
        id=row.id,
        name=row.name,
        kind=to_domain(RoleKind, row.kind),
        tenant_id=row.tenant_id,
        description=row.description,
    )


def _capability_to_domain(row: CapabilityModel) -> Capability:
    return Capability(
        id=row.id,
        name=row.name,
        scope=to_domain(CapabilityScope, row.scope),
        description=row.description,
    )


class SqlAlchemyRoleRepository:
    """Adaptador de `RoleRepository` (`app.domain.ports.repositories`)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, role_id: uuid.UUID) -> Role | None:
        try:
            row = await self._session.get(RoleModel, role_id)
        except Exception as exc:
            raise PortError("fallo al leer role") from exc
        return _role_to_domain(row) if row is not None else None

    async def add(self, role: Role) -> Role:
        row = RoleModel(
            id=role.id,
            name=role.name,
            kind=to_orm(RoleKindOrm, role.kind),
            tenant_id=role.tenant_id,
            description=role.description,
        )
        self._session.add(row)
        try:
            await self._session.flush()
        except Exception as exc:
            raise PortError("fallo al crear role") from exc
        return _role_to_domain(row)

    async def update(self, role: Role) -> Role:
        """Persiste `name`/`description` — `kind`/`tenant_id` son de identidad, no se reasignan."""
        try:
            row = await self._session.get(RoleModel, role.id)
        except Exception as exc:
            raise PortError("fallo al leer role") from exc
        if row is None:
            raise PortError(f"role {role.id} no existe")
        row.name = role.name
        row.description = role.description
        try:
            await self._session.flush()
        except Exception as exc:
            raise PortError("fallo al actualizar role") from exc
        return _role_to_domain(row)

    async def delete(self, role_id: uuid.UUID) -> bool:
        try:
            row = await self._session.get(RoleModel, role_id)
            if row is None:
                return False
            await self._session.delete(row)
            await self._session.flush()
        except Exception as exc:
            raise PortError("fallo al borrar role") from exc
        return True

    async def list_capabilities(self, role_id: uuid.UUID) -> list[Capability]:
        try:
            rows = (
                await self._session.execute(
                    select(CapabilityModel)
                    .join(
                        RoleCapabilityModel, RoleCapabilityModel.capability_id == CapabilityModel.id
                    )
                    .where(RoleCapabilityModel.role_id == role_id)
                )
            ).scalars()
        except Exception as exc:
            raise PortError("fallo al listar capabilities del role") from exc
        return [_capability_to_domain(row) for row in rows]

    async def list_all_capabilities(self) -> list[Capability]:
        try:
            rows = (await self._session.execute(select(CapabilityModel))).scalars()
        except Exception as exc:
            raise PortError("fallo al listar el catálogo de capabilities") from exc
        return [_capability_to_domain(row) for row in rows]

    async def assign(
        self, user_id: uuid.UUID, role_id: uuid.UUID, tenant_id: uuid.UUID | None
    ) -> None:
        stmt = (
            pg_insert(UserRoleModel)
            .values(user_id=user_id, role_id=role_id, tenant_id=tenant_id)
            .on_conflict_do_update(
                index_elements=[UserRoleModel.user_id, UserRoleModel.role_id],
                set_={"tenant_id": tenant_id},
            )
        )
        try:
            await self._session.execute(stmt)
        except Exception as exc:
            raise PortError("fallo al asignar role") from exc

    async def unassign_all(self, user_id: uuid.UUID, tenant_id: uuid.UUID | None) -> None:
        tenant_filter = (
            UserRoleModel.tenant_id.is_(None)
            if tenant_id is None
            else UserRoleModel.tenant_id == tenant_id
        )
        try:
            await self._session.execute(
                delete(UserRoleModel).where(UserRoleModel.user_id == user_id, tenant_filter)
            )
        except Exception as exc:
            raise PortError("fallo al retirar roles") from exc

    async def list_assigned(self, user_id: uuid.UUID, tenant_id: uuid.UUID) -> list[Role]:
        try:
            rows = (
                await self._session.execute(
                    select(RoleModel)
                    .join(UserRoleModel, UserRoleModel.role_id == RoleModel.id)
                    .where(UserRoleModel.user_id == user_id, UserRoleModel.tenant_id == tenant_id)
                )
            ).scalars()
        except Exception as exc:
            raise PortError("fallo al listar roles asignados") from exc
        return [_role_to_domain(row) for row in rows]

    async def set_capabilities(self, role_id: uuid.UUID, capability_ids: list[uuid.UUID]) -> None:
        try:
            await self._session.execute(
                delete(RoleCapabilityModel).where(RoleCapabilityModel.role_id == role_id)
            )
            if capability_ids:
                await self._session.execute(
                    insert(RoleCapabilityModel),
                    [{"role_id": role_id, "capability_id": cid} for cid in capability_ids],
                )
        except Exception as exc:
            raise PortError("fallo al fijar capabilities del role") from exc

    async def effective_capabilities(
        self, user_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> set[tuple[str, str]]:
        try:
            rows = await self._session.execute(
                select(CapabilityModel.name, UserRoleModel.tenant_id)
                .join(RoleCapabilityModel, RoleCapabilityModel.capability_id == CapabilityModel.id)
                .join(UserRoleModel, UserRoleModel.role_id == RoleCapabilityModel.role_id)
                .where(
                    UserRoleModel.user_id == user_id,
                    or_(UserRoleModel.tenant_id == tenant_id, UserRoleModel.tenant_id.is_(None)),
                )
                .distinct()
            )
        except Exception as exc:
            raise PortError("fallo al resolver capacidades efectivas") from exc
        return {
            (name, "global" if assignment_tenant_id is None else "tenant")
            for name, assignment_tenant_id in rows
        }

    async def list(self, tenant_id: uuid.UUID) -> list[Role]:
        try:
            rows = (
                await self._session.execute(
                    select(RoleModel).where(
                        or_(RoleModel.tenant_id == tenant_id, RoleModel.tenant_id.is_(None))
                    )
                )
            ).scalars()
        except Exception as exc:
            raise PortError("fallo al listar roles") from exc
        return [_role_to_domain(row) for row in rows]
