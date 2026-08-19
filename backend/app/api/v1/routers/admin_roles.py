"""app.api.v1.routers.admin_roles — catálogo de capacidades + role builder (contrato 06).

El `scope` de cada capacidad solicitada en `RoleCreate.capabilities` (solo nombres, sin `scope` propio
en el contrato) se resuelve del CATÁLOGO (`Capability.scope`, el ámbito MÁXIMO permitido para esa
capacidad) — no lo elige el cliente: si el catálogo declara una capacidad como `global` (p.ej.
`tenant.manage`), un rol `tenant` (custom, siempre `RoleKind.tenant`) nunca puede incluirla, y
`rbac_service.validate_role_composition` lo rechaza. Roles `system` son inmutables (403/409, RN de
CU-BE-09) — no se validan invariantes de composición para ellos, ni se les permite `PATCH`/`DELETE`.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.admin import Capability, Role, RoleCreate
from app.core.deps import require_capability
from app.domain.entities.business import AuditLogEntry
from app.domain.entities.enums import RoleKind
from app.domain.entities.identity import Role as RoleEntity
from app.domain.entities.identity import Subject
from app.domain.errors import Conflict, NotFound, Validation
from app.domain.services.rbac_service import validate_role_composition
from app.infra.db.repositories import SqlAlchemyAuditLogRepository, SqlAlchemyRoleRepository

router = APIRouter(prefix="/admin", tags=["admin"])

_CAPABILITY = "role.manage"


async def _to_schema(role_repo: SqlAlchemyRoleRepository, role: RoleEntity) -> Role:
    capabilities = await role_repo.list_capabilities(role.id)
    return Role(
        id=role.id,
        name=role.name,
        kind=role.kind.value,
        tenant_id=role.tenant_id,
        capabilities=[c.name for c in capabilities],
    )


async def _resolve_requested_capabilities(
    role_repo: SqlAlchemyRoleRepository, names: list[str]
) -> tuple[set[tuple[str, str]], list[uuid.UUID]]:
    """Resuelve `names` del catálogo a `{(name, scope)}` (para validar invariantes) + sus ids (para
    `set_capabilities`). Nombre desconocido → `Validation` (422), nunca un `KeyError` crudo."""
    catalog = {c.name: c for c in await role_repo.list_all_capabilities()}
    requested: set[tuple[str, str]] = set()
    capability_ids: list[uuid.UUID] = []
    for name in names:
        capability = catalog.get(name)
        if capability is None:
            raise Validation(
                f"capacidad desconocida: {name}",
                code="admin.unknown_capability",
                details={"field": "capabilities", "message": f"capacidad desconocida: {name}"},
            )
        requested.add((capability.name, capability.scope.value))
        capability_ids.append(capability.id)
    return requested, capability_ids


@router.get("/capabilities")
async def list_capabilities(
    subject_session: tuple[Subject, AsyncSession] = Depends(require_capability(_CAPABILITY)),
) -> list[Capability]:
    _subject, session = subject_session
    capabilities = await SqlAlchemyRoleRepository(session).list_all_capabilities()
    return [
        Capability(name=c.name, scope=c.scope.value, description=c.description)
        for c in capabilities
    ]


@router.get("/roles")
async def list_roles(
    subject_session: tuple[Subject, AsyncSession] = Depends(require_capability(_CAPABILITY)),
) -> list[Role]:
    subject, session = subject_session
    role_repo = SqlAlchemyRoleRepository(session)
    roles = await role_repo.list(subject.tenant_id)
    return [await _to_schema(role_repo, role) for role in roles]


@router.post("/roles", status_code=201)
async def create_role(
    payload: RoleCreate,
    subject_session: tuple[Subject, AsyncSession] = Depends(require_capability(_CAPABILITY)),
) -> Role:
    subject, session = subject_session
    role_repo = SqlAlchemyRoleRepository(session)
    requested, capability_ids = await _resolve_requested_capabilities(
        role_repo, payload.capabilities
    )
    validate_role_composition(subject.capabilities, requested)
    role = await role_repo.add(
        RoleEntity(
            id=uuid.uuid4(), name=payload.name, kind=RoleKind.tenant, tenant_id=subject.tenant_id
        )
    )
    await role_repo.set_capabilities(role.id, capability_ids)
    await SqlAlchemyAuditLogRepository(session).add(
        AuditLogEntry(
            tenant_id=subject.tenant_id,
            actor_id=subject.id,
            action="role.created",
            entity_type="role",
            entity_id=str(role.id),
            payload={"name": role.name, "capabilities": payload.capabilities},
        )
    )
    return await _to_schema(role_repo, role)


async def _get_editable_role(
    role_repo: SqlAlchemyRoleRepository, role_id: uuid.UUID, subject: Subject
) -> RoleEntity:
    """Un rol EDITABLE es un rol `tenant` (custom) del PROPIO tenant del subject.

    Orden de los checks importa: los roles `system` son VISIBLES a cualquier tenant vía
    `GET /admin/roles` (semilla + custom del tenant) — comprobar `kind is system` ANTES que el
    `tenant_id` da 409 (inmutable) para un rol que el cliente sabe que existe, en vez de un 404
    engañoso (`role.tenant_id` de un `system` role es `None`, que nunca coincidiría con
    `subject.tenant_id`). Un rol `tenant` de OTRO tenant sí es 404 — nunca revela su existencia."""
    role = await role_repo.get(role_id)
    if role is None:
        raise NotFound(f"role {role_id} no existe", code="role.not_found")
    if role.kind is RoleKind.system:
        raise Conflict("los roles system son inmutables", code="role.system_immutable")
    if role.tenant_id != subject.tenant_id:
        raise NotFound(f"role {role_id} no existe", code="role.not_found")
    return role


@router.patch("/roles/{id}")
async def update_role(
    id: uuid.UUID,
    payload: RoleCreate,
    subject_session: tuple[Subject, AsyncSession] = Depends(require_capability(_CAPABILITY)),
) -> Role:
    subject, session = subject_session
    role_repo = SqlAlchemyRoleRepository(session)
    role = await _get_editable_role(role_repo, id, subject)
    requested, capability_ids = await _resolve_requested_capabilities(
        role_repo, payload.capabilities
    )
    validate_role_composition(subject.capabilities, requested)
    role.name = payload.name
    role = await role_repo.update(role)
    await role_repo.set_capabilities(role.id, capability_ids)
    await SqlAlchemyAuditLogRepository(session).add(
        AuditLogEntry(
            tenant_id=subject.tenant_id,
            actor_id=subject.id,
            action="role.updated",
            entity_type="role",
            entity_id=str(role.id),
            payload={"name": role.name, "capabilities": payload.capabilities},
        )
    )
    return await _to_schema(role_repo, role)


@router.delete("/roles/{id}", status_code=204)
async def delete_role(
    id: uuid.UUID,
    subject_session: tuple[Subject, AsyncSession] = Depends(require_capability(_CAPABILITY)),
) -> None:
    subject, session = subject_session
    role_repo = SqlAlchemyRoleRepository(session)
    await _get_editable_role(role_repo, id, subject)
    await role_repo.delete(id)
    await SqlAlchemyAuditLogRepository(session).add(
        AuditLogEntry(
            tenant_id=subject.tenant_id,
            actor_id=subject.id,
            action="role.deleted",
            entity_type="role",
            entity_id=str(id),
            payload={},
        )
    )
