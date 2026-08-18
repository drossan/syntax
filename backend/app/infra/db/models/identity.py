"""app.infra.db.models.identity — modelos ORM de identidad/RBAC (data-model.md §4.1).

Grupo **cross-tenant de sistema**: NO usa ``TenantMixin`` (no RLS de fila). ``user``/``role``/
``user_role`` llevan una columna ``tenant_id`` normal (para unicidad/ámbito), pero su aislamiento
lo gobierna el RBAC (02), no RLS. FKs/cascadas de §7; unicidades de §9. Sin efectos en import.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.db.base import Base, TimestampMixin
from app.infra.db.models.enums import (
    AuthTokenKind,
    CapabilityScope,
    RefreshSessionStatus,
    RoleKind,
    TenantStatus,
    UserStatus,
    pg_enum,
)


class Tenant(TimestampMixin, Base):
    """Cliente = dominio. No se hard-borra (soft-disable por ``status``, §7)."""

    __tablename__ = "tenant"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String, unique=True)
    name: Mapped[str] = mapped_column(String)
    status: Mapped[TenantStatus] = mapped_column(pg_enum(TenantStatus, "tenant_status"))


class User(TimestampMixin, Base):
    """Usuario de un tenant. ``password_hash`` argon2 nullable (aún ``invited`` sin clave)."""

    __tablename__ = "user"
    __table_args__ = (UniqueConstraint("tenant_id", "email"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="RESTRICT"))
    email: Mapped[str] = mapped_column(String)
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[UserStatus] = mapped_column(pg_enum(UserStatus, "user_status"))
    sso_subject: Mapped[str | None] = mapped_column(String, nullable=True)


class Capability(Base):
    """Catálogo de capacidades RBAC (semilla; no editable por tenants)."""

    __tablename__ = "capability"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, unique=True)
    scope: Mapped[CapabilityScope] = mapped_column(pg_enum(CapabilityScope, "capability_scope"))
    description: Mapped[str | None] = mapped_column(String, nullable=True)


class Role(TimestampMixin, Base):
    """Rol: ``system`` (inmutable, ``tenant_id`` NULL) o ``tenant`` (custom). Único (tenant_id, name)."""

    __tablename__ = "role"
    __table_args__ = (UniqueConstraint("tenant_id", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String)
    kind: Mapped[RoleKind] = mapped_column(pg_enum(RoleKind, "role_kind"))
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=True
    )
    description: Mapped[str | None] = mapped_column(String, nullable=True)


class RoleCapability(Base):
    """Unión role×capability. PK compuesta (role_id, capability_id)."""

    __tablename__ = "role_capability"

    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("role.id", ondelete="CASCADE"), primary_key=True
    )
    capability_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("capability.id", ondelete="CASCADE"), primary_key=True
    )


class UserRole(Base):
    """Unión user×role, con el ``tenant_id`` del ámbito de asignación. PK (user_id, role_id)."""

    __tablename__ = "user_role"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("role.id", ondelete="CASCADE"), primary_key=True
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=True
    )


class RefreshSession(Base):
    """Token store del refresh: rotación por ``family_id``/``parent_id`` + reuse-detection (A1.5)."""

    __tablename__ = "refresh_session"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String, unique=True)
    family_id: Mapped[uuid.UUID] = mapped_column()
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("refresh_session.id"), nullable=True
    )
    status: Mapped[RefreshSessionStatus] = mapped_column(
        pg_enum(RefreshSessionStatus, "refresh_session_status")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String, nullable=True)
    ip: Mapped[str | None] = mapped_column(String, nullable=True)


class AuthToken(Base):
    """Token de un solo uso: password-reset o invitación (B.3). Email en stub en Fase 1."""

    __tablename__ = "auth_token"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    kind: Mapped[AuthTokenKind] = mapped_column(pg_enum(AuthTokenKind, "auth_token_kind"))
    token_hash: Mapped[str] = mapped_column(String, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
