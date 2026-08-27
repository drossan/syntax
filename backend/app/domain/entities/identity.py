"""app.domain.entities.identity — entidades de identidad/RBAC (data-model.md §4.1) + Subject.

Grupo cross-tenant de sistema. `Subject` (`rbac.md §1`) no tiene equivalente ORM directo: es el sujeto
autenticado ya resuelto (capacidades efectivas), consumido por `rbac_service.authorize`.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.domain.entities.enums import (
    AuthTokenKind,
    CapabilityScope,
    RefreshSessionStatus,
    RoleKind,
    TenantStatus,
    UserStatus,
)


class Tenant(BaseModel):
    """Cliente = dominio. No se hard-borra (soft-disable por `status`)."""

    id: uuid.UUID
    slug: str
    name: str
    status: TenantStatus
    auto_approve: bool = False
    ai_auto_draft: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


class User(BaseModel):
    """Identidad global (email único, sin `tenant_id`/`status` propios — viven en
    `UserTenantMembership`). Una sola contraseña compartida entre todas sus membresías."""

    id: uuid.UUID
    email: str
    password_hash: str | None = None
    sso_subject: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class UserTenantMembership(BaseModel):
    """Membership `user`×`tenant`: el `status` (`invited`/`active`/`disabled`) vive AQUÍ, por tenant."""

    user_id: uuid.UUID
    tenant_id: uuid.UUID
    status: UserStatus
    created_at: datetime | None = None


class Capability(BaseModel):
    """Capacidad RBAC del catálogo (semilla; no editable por tenants)."""

    id: uuid.UUID
    name: str
    scope: CapabilityScope
    description: str | None = None


class Role(BaseModel):
    """Rol: `system` (inmutable) o `tenant` (custom)."""

    id: uuid.UUID
    name: str
    kind: RoleKind
    tenant_id: uuid.UUID | None = None
    description: str | None = None


class RefreshSession(BaseModel):
    """Sesión de refresh: rotación por `family_id`/`parent_id` + reuse-detection.

    `tenant_id`: una sesión de refresh es de un tenant concreto (el elegido en
    `select_tenant`/`switch_tenant` cuando el usuario tiene varias membresías)."""

    id: uuid.UUID
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    token_hash: str
    family_id: uuid.UUID
    parent_id: uuid.UUID | None = None
    status: RefreshSessionStatus
    expires_at: datetime
    created_at: datetime | None = None
    last_used_at: datetime | None = None


class AuthToken(BaseModel):
    """Token de un solo uso: password-reset o invitación."""

    id: uuid.UUID
    user_id: uuid.UUID
    kind: AuthTokenKind
    token_hash: str
    expires_at: datetime
    used_at: datetime | None = None


class Subject(BaseModel):
    """Sujeto autenticado con su conjunto efectivo de `(capability, scope)` ya resuelto (`rbac.md §1`)."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    capabilities: set[tuple[str, str]]
