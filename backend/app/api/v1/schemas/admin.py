"""app.api.v1.schemas.admin — DTOs de los routers `admin_tenants`/`admin_users`/`admin_roles`
(1:1 con `api-contract.yaml`).

`AdminUser` mapea al componente `User` del contrato — renombrado para no colisionar con la entidad de
dominio `app.domain.entities.identity.User` cuando ambos se importan en el mismo router.
"""

import uuid

from pydantic import BaseModel, Field


class Tenant(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    status: str


class TenantCreate(BaseModel):
    slug: str
    name: str


class TenantSettings(BaseModel):
    auto_approve: bool = False
    ai_auto_draft: bool = True


class AdminUser(BaseModel):
    """`status` es el de la MEMBRESÍA del tenant consultado, no un atributo global del `User`."""

    id: uuid.UUID
    email: str
    status: str
    roles: list[str] = []


class UserInvite(BaseModel):
    email: str
    roles: list[uuid.UUID] = []


class UserUpdate(BaseModel):
    status: str | None = None
    roles: list[uuid.UUID] | None = None


class Capability(BaseModel):
    name: str
    scope: str
    description: str | None = None


class Role(BaseModel):
    id: uuid.UUID
    name: str
    kind: str
    tenant_id: uuid.UUID | None = None
    capabilities: list[str] = []


class RoleCreate(BaseModel):
    name: str
    capabilities: list[str] = Field(default_factory=list)
