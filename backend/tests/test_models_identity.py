"""Tests de los modelos ORM de identidad/RBAC (tarea 03) — nivel metadata, unit.

Grupo cross-tenant de sistema: NO usa TenantMixin (no RLS de fila). Verifica registro,
enums (conjunto exacto), PKs compuestas, unicidades, cascadas y la self-FK de rotación.
"""

import uuid

import pytest
from app.infra.db.base import Base, TenantMixin
from app.infra.db.models import (
    AuthToken,
    Capability,
    RefreshSession,
    Role,
    RoleCapability,
    Tenant,
    User,
    UserRole,
)
from app.infra.db.models.enums import (
    AuthTokenKind,
    CapabilityScope,
    RefreshSessionStatus,
    RoleKind,
    TenantStatus,
    UserStatus,
)
from sqlalchemy import UniqueConstraint

_IDENTITY_TABLES = {
    "tenant",
    "user",
    "capability",
    "role",
    "role_capability",
    "user_role",
    "refresh_session",
    "auth_token",
}

_IDENTITY_MODELS = [
    Tenant,
    User,
    Capability,
    Role,
    RoleCapability,
    UserRole,
    RefreshSession,
    AuthToken,
]


def _unique_column_sets(model: type) -> list[frozenset[str]]:
    """Conjuntos de columnas de cada UniqueConstraint del modelo."""
    return [
        frozenset(col.name for col in constraint.columns)
        for constraint in model.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    ]


def test_eight_identity_tables_registered() -> None:
    """Las 8 tablas de identidad/RBAC están registradas en Base.metadata."""
    assert set(Base.metadata.tables) >= _IDENTITY_TABLES


def test_no_identity_table_uses_tenant_mixin() -> None:
    """Ningún modelo de identidad hereda TenantMixin (no son tablas de negocio con RLS)."""
    for model in _IDENTITY_MODELS:
        assert not issubclass(model, TenantMixin), model.__name__


@pytest.mark.parametrize(
    ("model", "columns"),
    [
        (RoleCapability, {"role_id", "capability_id"}),
        (UserRole, {"user_id", "role_id"}),
    ],
)
def test_join_tables_have_composite_pk(model: type, columns: set[str]) -> None:
    """Las tablas de unión tienen PK compuesta de sus dos FKs."""
    pk_columns = {col.name for col in model.__table__.primary_key.columns}
    assert pk_columns == columns


@pytest.mark.parametrize(
    ("model", "attr", "expected"),
    [
        (RefreshSession, "status", {"active", "rotated", "revoked"}),
        (AuthToken, "kind", {"password_reset", "invitation"}),
        (User, "status", {"invited", "active", "disabled"}),
        (Tenant, "status", {"active", "disabled"}),
        (Role, "kind", {"system", "tenant"}),
        (Capability, "scope", {"tenant", "global"}),
    ],
)
def test_enum_has_exact_value_set(model: type, attr: str, expected: set[str]) -> None:
    """Cada enum nativo tiene EXACTAMENTE su conjunto de valores (ni más ni menos)."""
    column = model.__table__.c[attr]
    assert set(column.type.enums) == expected


def test_user_tenant_fk_uses_restrict() -> None:
    """La FK user.tenant_id → tenant usa ON DELETE RESTRICT (un tenant no se hard-borra, §7)."""
    fk = next(iter(User.__table__.c["tenant_id"].foreign_keys))
    assert fk.target_fullname == "tenant.id"
    assert fk.ondelete == "RESTRICT"


@pytest.mark.parametrize(
    ("model", "columns"),
    [
        (User, {"tenant_id", "email"}),
        (Role, {"tenant_id", "name"}),
        (Capability, {"name"}),
        (RefreshSession, {"token_hash"}),
        (AuthToken, {"token_hash"}),
    ],
)
def test_unique_constraints_declared(model: type, columns: set[str]) -> None:
    """La unicidad de negocio de cada modelo está declarada (data-model §9)."""
    assert frozenset(columns) in _unique_column_sets(model)


def test_refresh_session_parent_is_nullable_self_fk() -> None:
    """refresh_session.parent_id es FK nullable a refresh_session.id (cadena de rotación)."""
    parent = RefreshSession.__table__.c["parent_id"]
    assert parent.nullable is True
    fk = next(iter(parent.foreign_keys))
    assert fk.target_fullname == "refresh_session.id"


def test_user_role_and_refresh_cascade_on_user_delete() -> None:
    """user → refresh_session / auth_token: CASCADE (limpieza al borrar el usuario, §7)."""
    for model in (RefreshSession, AuthToken):
        fk = next(iter(model.__table__.c["user_id"].foreign_keys))
        assert fk.ondelete == "CASCADE", model.__name__


def test_enum_python_classes_have_string_values() -> None:
    """Los enums Python exponen los valores del contrato como strings (values_callable)."""
    assert {m.value for m in CapabilityScope} == {"tenant", "global"}
    assert {m.value for m in RoleKind} == {"system", "tenant"}
    assert {m.value for m in UserStatus} == {"invited", "active", "disabled"}
    assert {m.value for m in TenantStatus} == {"active", "disabled"}
    assert {m.value for m in RefreshSessionStatus} == {"active", "rotated", "revoked"}
    assert {m.value for m in AuthTokenKind} == {"password_reset", "invitation"}


def test_user_has_tenant_id_but_no_rls_marker() -> None:
    """user tiene columna tenant_id (para unicidad/ámbito) SIN heredar TenantMixin (sin RLS)."""
    assert "tenant_id" in User.__table__.c
    assert not issubclass(User, TenantMixin)


def test_pk_is_uuid_on_first_class_entities() -> None:
    """Las entidades de primera clase tienen PK id de tipo UUID."""
    for model in (Tenant, User, Capability, Role, RefreshSession, AuthToken):
        pk = list(model.__table__.primary_key.columns)
        assert len(pk) == 1
        assert pk[0].name == "id"
        assert pk[0].type.python_type is uuid.UUID
