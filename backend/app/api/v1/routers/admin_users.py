"""app.api.v1.routers.admin_users — gestión/invitación de usuarios del tenant (contrato 06).

`{id}` de `PATCH /admin/users/{id}` es el `User.id` GLOBAL (identidad multi-tenant, tarea 01) — el
router cruza con `subject.tenant_id` para localizar la `UserTenantMembership`; si el `User` existe
pero no tiene membership en ESE tenant, 404 (nunca revela que existe en otro tenant, mismo patrón de
aislamiento cross-tenant que los tickets).
"""

import uuid
from typing import cast

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.admin import AdminUser, UserInvite, UserUpdate
from app.api.v1.schemas.common import Page
from app.core.deps import get_auth_service, require_capability
from app.domain.entities.business import AuditLogEntry
from app.domain.entities.enums import UserStatus
from app.domain.entities.identity import Subject, UserTenantMembership
from app.domain.entities.identity import User as UserEntity
from app.domain.errors import NotFound, Validation
from app.domain.services.auth_service import AuthService
from app.infra.db.repositories import (
    SqlAlchemyAuditLogRepository,
    SqlAlchemyRoleRepository,
    SqlAlchemyUserRepository,
    SqlAlchemyUserTenantMembershipRepository,
)

router = APIRouter(prefix="/admin", tags=["admin"])

_CAPABILITY = "user.manage"


async def _to_schema(
    session: AsyncSession, *, user_id: uuid.UUID, email: str, status: str, tenant_id: uuid.UUID
) -> AdminUser:
    roles = await SqlAlchemyRoleRepository(session).list_assigned(user_id, tenant_id)
    return AdminUser(id=user_id, email=email, status=status, roles=[r.name for r in roles])


@router.get("/users")
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    subject_session: tuple[Subject, AsyncSession] = Depends(require_capability(_CAPABILITY)),
) -> Page[AdminUser]:
    subject, session = subject_session
    user_repo = SqlAlchemyUserRepository(session)
    result = await SqlAlchemyUserTenantMembershipRepository(session).list_by_tenant(
        subject.tenant_id, page=page, page_size=page_size
    )
    items = []
    for membership in result.items:
        # invariante: toda membership referencia un User existente (FK) — narrowing puro.
        user = cast(UserEntity, await user_repo.get(membership.user_id))
        items.append(
            await _to_schema(
                session,
                user_id=user.id,
                email=user.email,
                status=membership.status.value,
                tenant_id=subject.tenant_id,
            )
        )
    return Page(items=items, page=page, page_size=page_size, total=result.total)


@router.post("/users", status_code=201)
async def invite_user(
    payload: UserInvite,
    subject_session: tuple[Subject, AsyncSession] = Depends(require_capability(_CAPABILITY)),
    auth_service: AuthService = Depends(get_auth_service),
) -> AdminUser:
    subject, session = subject_session
    await auth_service.invite(subject.tenant_id, payload.email)
    normalized_email = payload.email.strip().lower()
    # invariante: invite() acaba de crear/reusar el User y la membership — narrowing puro.
    user = cast(UserEntity, await SqlAlchemyUserRepository(session).get_by_email(normalized_email))
    membership = cast(
        UserTenantMembership,
        await SqlAlchemyUserTenantMembershipRepository(session).get(user.id, subject.tenant_id),
    )
    role_repo = SqlAlchemyRoleRepository(session)
    for role_id in payload.roles:
        await role_repo.assign(user.id, role_id, subject.tenant_id)
    await SqlAlchemyAuditLogRepository(session).add(
        AuditLogEntry(
            tenant_id=subject.tenant_id,
            actor_id=subject.id,
            action="user.invited",
            entity_type="user",
            entity_id=str(user.id),
            payload={"email": user.email, "roles": [str(r) for r in payload.roles]},
        )
    )
    return await _to_schema(
        session,
        user_id=user.id,
        email=user.email,
        status=membership.status.value,
        tenant_id=subject.tenant_id,
    )


@router.patch("/users/{id}")
async def update_user(
    id: uuid.UUID,
    payload: UserUpdate,
    subject_session: tuple[Subject, AsyncSession] = Depends(require_capability(_CAPABILITY)),
) -> AdminUser:
    subject, session = subject_session
    membership_repo = SqlAlchemyUserTenantMembershipRepository(session)
    membership = await membership_repo.get(id, subject.tenant_id)
    if membership is None:
        raise NotFound(f"user {id} no existe en este tenant", code="user.not_found")
    if payload.status is not None:
        try:
            membership.status = UserStatus(payload.status)
        except ValueError as exc:
            raise Validation(
                f"status desconocido: {payload.status}", code="admin.unknown_user_status"
            ) from exc
        membership = await membership_repo.update(membership)
    role_repo = SqlAlchemyRoleRepository(session)
    if payload.roles is not None:
        await role_repo.unassign_all(id, subject.tenant_id)
        for role_id in payload.roles:
            await role_repo.assign(id, role_id, subject.tenant_id)
    # invariante: la membership referencia un User existente (FK) — narrowing puro.
    user = cast(UserEntity, await SqlAlchemyUserRepository(session).get(id))
    await SqlAlchemyAuditLogRepository(session).add(
        AuditLogEntry(
            tenant_id=subject.tenant_id,
            actor_id=subject.id,
            action="user.updated",
            entity_type="user",
            entity_id=str(id),
            payload={"status": membership.status.value},
        )
    )
    return await _to_schema(
        session,
        user_id=user.id,
        email=user.email,
        status=membership.status.value,
        tenant_id=subject.tenant_id,
    )
