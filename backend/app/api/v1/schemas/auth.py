"""app.api.v1.schemas.auth — DTOs del router `auth` (1:1 con `api-contract.yaml`)."""

import uuid

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """`email` es `str` (no `EmailStr`: el proyecto no depende de `email-validator`) — la validación
    de forma vive en el dominio/DB, no en el schema de transporte."""

    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 — tipo de token OAuth2, no un secreto
    expires_in: int | None = None


class TenantChoice(BaseModel):
    id: uuid.UUID
    slug: str
    name: str


class LoginTenantSelection(BaseModel):
    identity_token: str
    tenants: list[TenantChoice]


class SelectTenantRequest(BaseModel):
    identity_token: str
    tenant_id: uuid.UUID


class SwitchTenantRequest(BaseModel):
    tenant_id: uuid.UUID


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class CapabilityGrant(BaseModel):
    capability: str
    scope: str


class MeUser(BaseModel):
    """Recorte de `User` (contrato) para `/auth/me`: `status` es el de la MEMBRESÍA del tenant
    activo (no un atributo global); `roles` queda vacío — no existe aún un puerto que liste
    nombres de rol por (user, tenant) (`RoleRepository` solo resuelve capacidades efectivas)."""

    id: uuid.UUID
    email: str
    status: str
    roles: list[str] = []


class Me(BaseModel):
    user: MeUser
    capabilities: list[CapabilityGrant]
