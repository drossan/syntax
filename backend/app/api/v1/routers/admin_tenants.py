"""app.api.v1.routers.admin_tenants — gestión de tenants + `/admin/settings` (contrato 06).

`/admin/settings` decide de qué tenant habla por el ÁMBITO CONCEDIDO de `tenant.settings.manage` al
subject (no por un flag propio del router): en ámbito `tenant` usa `subject.tenant_id` (el query param
`tenant_id`, si llega, se ignora); en ámbito `global` (Soporte, sin tenant propio) `tenant_id` es
OBLIGATORIO — sin él no hay forma de saber a qué tenant se refiere (decisión de `scenario-coverage`).
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.admin import Tenant, TenantCreate, TenantSettings
from app.api.v1.schemas.common import Page
from app.core.deps import require_capability
from app.domain.entities.business import AuditLogEntry
from app.domain.entities.enums import TenantStatus
from app.domain.entities.identity import Subject
from app.domain.entities.identity import Tenant as TenantEntity
from app.domain.errors import NotFound, Validation
from app.infra.db.repositories import SqlAlchemyAuditLogRepository, SqlAlchemyTenantRepository

router = APIRouter(prefix="/admin", tags=["admin"])

_TENANTS_CAPABILITY = "tenant.manage"
_SETTINGS_CAPABILITY = "tenant.settings.manage"


def _to_schema(tenant: TenantEntity) -> Tenant:
    return Tenant(id=tenant.id, slug=tenant.slug, name=tenant.name, status=tenant.status.value)


def _has_global_scope(subject: Subject, capability: str) -> bool:
    return (capability, "global") in subject.capabilities


def _resolve_settings_tenant_id(subject: Subject, tenant_id: uuid.UUID | None) -> uuid.UUID:
    if _has_global_scope(subject, _SETTINGS_CAPABILITY):
        if tenant_id is None:
            raise Validation(
                "tenant_id es obligatorio en ámbito global", code="admin.tenant_id_required"
            )
        return tenant_id
    return subject.tenant_id


@router.get("/tenants")
async def list_tenants(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    subject_session: tuple[Subject, AsyncSession] = Depends(
        require_capability(_TENANTS_CAPABILITY)
    ),
) -> Page[Tenant]:
    _subject, session = subject_session
    result = await SqlAlchemyTenantRepository(session).list(page=page, page_size=page_size)
    return Page(
        items=[_to_schema(t) for t in result.items],
        page=page,
        page_size=page_size,
        total=result.total,
    )


@router.post("/tenants", status_code=201)
async def create_tenant(
    payload: TenantCreate,
    subject_session: tuple[Subject, AsyncSession] = Depends(
        require_capability(_TENANTS_CAPABILITY)
    ),
) -> Tenant:
    subject, session = subject_session
    tenant = await SqlAlchemyTenantRepository(session).add(
        TenantEntity(
            id=uuid.uuid4(), slug=payload.slug, name=payload.name, status=TenantStatus.active
        )
    )
    await SqlAlchemyAuditLogRepository(session).add(
        AuditLogEntry(
            tenant_id=tenant.id,
            actor_id=subject.id,
            action="tenant.created",
            entity_type="tenant",
            entity_id=str(tenant.id),
            payload={"slug": tenant.slug, "name": tenant.name},
        )
    )
    return _to_schema(tenant)


@router.get("/settings")
async def get_settings(
    tenant_id: uuid.UUID | None = Query(None),
    subject_session: tuple[Subject, AsyncSession] = Depends(
        require_capability(_SETTINGS_CAPABILITY)
    ),
) -> TenantSettings:
    subject, session = subject_session
    target_tenant_id = _resolve_settings_tenant_id(subject, tenant_id)
    tenant = await SqlAlchemyTenantRepository(session).get(target_tenant_id)
    if tenant is None:
        raise NotFound(f"tenant {target_tenant_id} no existe", code="tenant.not_found")
    return TenantSettings(auto_approve=tenant.auto_approve)


@router.patch("/settings")
async def update_settings(
    payload: TenantSettings,
    tenant_id: uuid.UUID | None = Query(None),
    subject_session: tuple[Subject, AsyncSession] = Depends(
        require_capability(_SETTINGS_CAPABILITY)
    ),
) -> TenantSettings:
    subject, session = subject_session
    target_tenant_id = _resolve_settings_tenant_id(subject, tenant_id)
    tenant_repo = SqlAlchemyTenantRepository(session)
    tenant = await tenant_repo.get(target_tenant_id)
    if tenant is None:
        raise NotFound(f"tenant {target_tenant_id} no existe", code="tenant.not_found")
    tenant.auto_approve = payload.auto_approve
    updated = await tenant_repo.update(tenant)
    await SqlAlchemyAuditLogRepository(session).add(
        AuditLogEntry(
            tenant_id=updated.id,
            actor_id=subject.id,
            action="tenant.settings_updated",
            entity_type="tenant",
            entity_id=str(updated.id),
            payload={"auto_approve": updated.auto_approve},
        )
    )
    return TenantSettings(auto_approve=updated.auto_approve)
