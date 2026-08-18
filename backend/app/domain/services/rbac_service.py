"""app.domain.services.rbac_service — autorización por capacidad + ámbito (materializa rbac.md).

`authorize` **devuelve** `Allow | Deny(reason)`, nunca lanza — el "no" es el camino esperado de la mitad
de las llamadas, no un error de dominio (decisión de grilling, a diferencia del resto de servicios de
este plan). `Deny.reason` es el discriminante que permite al router (11/12) elegir 403 (`no_capability`)
vs 404 (`out_of_scope`, "no revelar existencia" — FR-011/FR-014, CU-BE-03).
"""

import enum
from dataclasses import dataclass

from app.domain.entities.business import Resource
from app.domain.entities.identity import Subject
from app.domain.errors import Validation


class DenyReason(enum.Enum):
    """Motivo de la denegación (discriminante para el mapeo HTTP futuro)."""

    no_capability = "no_capability"
    """El sujeto no tiene la capacidad+ámbito solicitados (fail-closed). Mapeo futuro: 403."""

    out_of_scope = "out_of_scope"
    """El recurso pertenece a otro tenant y el sujeto no opera en ámbito global. Mapeo futuro: 404."""


@dataclass(frozen=True)
class Allow:
    """La acción procede."""


@dataclass(frozen=True)
class Deny:
    """La acción se deniega, con el motivo discriminado."""

    reason: DenyReason


Decision = Allow | Deny


def authorize(subject: Subject, capability: str, scope: str, resource: Resource) -> Decision:
    """Decide por **capacidad + ámbito** (`rbac.md §7`), nunca por nombre de rol — `Subject` no tiene
    ningún campo de rol que consultar, solo el conjunto efectivo `(capability, scope)` ya resuelto.

    Fail-closed: si `(capability, scope)` no está en `subject.capabilities` (incl. sujeto sin ningún rol,
    o capacidades no resolubles — ambos se representan como conjunto vacío) → `Deny(no_capability)`.

    Si la capacidad SÍ está concedida con `scope="tenant"` y `resource.tenant_id` no es `None` y no
    coincide con `subject.tenant_id` → `Deny(out_of_scope)` (no revela si el recurso existe). Un
    `resource.tenant_id=None` (recurso global, p.ej. KB) **no** se compara — RN-3 de CU-BE-03.
    """
    if (capability, scope) not in subject.capabilities:
        return Deny(DenyReason.no_capability)

    if (
        scope == "tenant"
        and resource.tenant_id is not None
        and resource.tenant_id != subject.tenant_id
    ):
        return Deny(DenyReason.out_of_scope)

    return Allow()


def validate_role_composition(
    composer_capabilities: set[tuple[str, str]], requested_capabilities: set[tuple[str, str]]
) -> None:
    """Valida los invariantes de componer un rol custom por tenant (`rbac.md §4`).

    :raises Validation: si se intenta conceder ámbito `global`, o una capacidad que el propio
        componedor no posee (no escalada de privilegios).
    """
    for capability, scope in requested_capabilities:
        if scope == "global":
            raise Validation(
                f"no se puede conceder la capacidad '{capability}' en ámbito global",
                code="rbac.custom_role_global_scope_forbidden",
                details={"capability": capability},
            )
        if (capability, scope) not in composer_capabilities:
            raise Validation(
                f"el componedor no posee la capacidad '{capability}' en ámbito '{scope}'",
                code="rbac.custom_role_privilege_escalation",
                details={"capability": capability, "scope": scope},
            )


__all__ = [
    "Allow",
    "Decision",
    "Deny",
    "DenyReason",
    "authorize",
    "validate_role_composition",
]
