"""app.infra.db.models.enums — enums nativos de Postgres (contrato: data-model.md §3).

Los **valores** string son el contrato literal (02/06 los referencian). Se usan como
etiquetas del tipo enum en Postgres vía :func:`pg_enum` (``values_callable``), no los
nombres de los miembros Python — necesario porque ``global`` es palabra reservada.
"""

import enum

from sqlalchemy import Enum


class TenantStatus(enum.Enum):
    """Estado de un tenant (soft-disable; no hard-delete)."""

    active = "active"
    disabled = "disabled"


class UserStatus(enum.Enum):
    """Estado de un usuario (soft-delete = ``disabled``; ``invited`` para el flujo B.3)."""

    invited = "invited"
    active = "active"
    disabled = "disabled"


class CapabilityScope(enum.Enum):
    """Ámbito de una capacidad RBAC (por tenant o global de Soporte)."""

    tenant = "tenant"
    global_ = "global"


class RoleKind(enum.Enum):
    """Tipo de rol: ``system`` (semilla inmutable) o ``tenant`` (custom por cliente)."""

    system = "system"
    tenant = "tenant"


class RefreshSessionStatus(enum.Enum):
    """Estado de una sesión de refresh (rotación + reuse-detection + logout server-side)."""

    active = "active"
    rotated = "rotated"
    revoked = "revoked"


class AuthTokenKind(enum.Enum):
    """Tipo de token de un solo uso (B.3)."""

    password_reset = "password_reset"  # noqa: S105 — etiqueta de enum, no un secreto
    invitation = "invitation"


def pg_enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    """Enum nativo de Postgres cuyas etiquetas son los VALUES del enum (no los names).

    :param enum_cls: la clase ``enum.Enum`` de origen.
    :param name: nombre del tipo enum en Postgres (contrato literal de data-model §3).
    :returns: un ``sqlalchemy.Enum`` listo para ``mapped_column``.
    """
    return Enum(enum_cls, name=name, values_callable=lambda members: [m.value for m in members])
