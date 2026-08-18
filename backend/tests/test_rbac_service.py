"""Tests de app.domain.services.rbac_service.authorize (tarea backend-domain-services-03).

Nivel unit. Traza a CU-BE-03. `authorize` DEVUELVE Allow|Deny(reason) — nunca lanza (decisión de
grilling: el "no" es el camino esperado, no un error).
"""

import uuid

import pytest
from app.domain.entities.business import Resource
from app.domain.entities.identity import Subject
from app.domain.errors import Validation
from app.domain.services.rbac_service import (
    Allow,
    Deny,
    DenyReason,
    authorize,
    validate_role_composition,
)

_TENANT_A = uuid.UUID(int=1)
_TENANT_B = uuid.UUID(int=2)


def _subject(capabilities: set[tuple[str, str]], tenant_id: uuid.UUID = _TENANT_A) -> Subject:
    return Subject(id=uuid.uuid4(), tenant_id=tenant_id, capabilities=capabilities)


def test_allowed_action_within_tenant() -> None:
    """Acción permitida dentro del tenant (CU-BE-03: sujeto con ticket.reply en su tenant)."""
    subject = _subject({("ticket.reply", "tenant")})
    resource = Resource(tenant_id=_TENANT_A)
    result = authorize(subject, "ticket.reply", "tenant", resource)
    assert isinstance(result, Allow)


def test_action_without_required_capability_is_denied() -> None:
    """Sin la capacidad requerida → Deny(no_capability) (CU-BE-03, mapeo futuro 403)."""
    subject = _subject(set())
    resource = Resource(tenant_id=_TENANT_A)
    result = authorize(subject, "ticket.transition", "tenant", resource)
    assert isinstance(result, Deny)
    assert result.reason is DenyReason.no_capability


def test_subject_without_any_role_is_deny_all() -> None:
    """Sujeto sin ningún rol → deny-all (capabilities vacío, cualquier capacidad se deniega)."""
    subject = _subject(set())
    resource = Resource(tenant_id=_TENANT_A)
    result = authorize(subject, "kb.read", "tenant", resource)
    assert isinstance(result, Deny)
    assert result.reason is DenyReason.no_capability


def test_cross_tenant_resource_is_not_revealed() -> None:
    """Recurso de OTRO tenant (sin ámbito global) → Deny(out_of_scope), mapeo futuro 404."""
    subject = _subject({("ticket.read", "tenant")}, tenant_id=_TENANT_A)
    resource = Resource(tenant_id=_TENANT_B)
    result = authorize(subject, "ticket.read", "tenant", resource)
    assert isinstance(result, Deny)
    assert result.reason is DenyReason.out_of_scope


def test_support_operates_cross_tenant_with_global_scope() -> None:
    """Sujeto de Soporte con capacidad de ámbito global opera cross-tenant."""
    subject = _subject({("ticket.reply", "global")}, tenant_id=_TENANT_A)
    resource = Resource(tenant_id=_TENANT_B)
    result = authorize(subject, "ticket.reply", "global", resource)
    assert isinstance(result, Allow)


def test_unresolvable_capabilities_fail_closed() -> None:
    """Capacidades no resolubles (representadas como conjunto vacío) → deny-all fail-closed."""
    subject = _subject(set())
    resource = Resource(tenant_id=_TENANT_A)
    result = authorize(subject, "analytics.read", "tenant", resource)
    assert isinstance(result, Deny)
    assert result.reason is DenyReason.no_capability


def test_kb_global_resource_does_not_require_tenant_match() -> None:
    """kb.read no exige coincidencia de tenant en el recurso (RN-3, resource.tenant_id=None)."""
    subject = _subject({("kb.read", "tenant")}, tenant_id=_TENANT_A)
    resource = Resource(tenant_id=None)
    result = authorize(subject, "kb.read", "tenant", resource)
    assert isinstance(result, Allow)


def test_decision_never_looks_at_role_name() -> None:
    """authorize decide por capacidad+ámbito: Subject no tiene ningún campo 'role_name' que consultar."""
    assert "role_name" not in Subject.model_fields
    assert "role" not in Subject.model_fields


def test_custom_role_cannot_grant_global_scope() -> None:
    """Componer un rol custom no puede conceder ámbito global (rbac.md §4)."""
    composer_capabilities = {("ticket.reply", "tenant"), ("ticket.reply", "global")}
    with pytest.raises(Validation):
        validate_role_composition(composer_capabilities, {("ticket.reply", "global")})


def test_custom_role_cannot_grant_capability_composer_lacks() -> None:
    """Componer un rol custom no puede conceder una capacidad que el propio componedor no posee."""
    composer_capabilities = {("ticket.reply", "tenant")}
    with pytest.raises(Validation):
        validate_role_composition(composer_capabilities, {("user.manage", "tenant")})


def test_custom_role_composition_within_invariants_succeeds() -> None:
    """Componer un rol custom con capacidades que el componedor sí posee, ámbito tenant, no lanza."""
    composer_capabilities = {("ticket.reply", "tenant"), ("ticket.read", "tenant")}
    validate_role_composition(composer_capabilities, {("ticket.reply", "tenant")})


def test_tenant_match_compares_by_value_not_identity() -> None:
    """El tenant_id del recurso se compara por VALOR, no por identidad de objeto (UUID reconstruido)."""
    subject = _subject({("ticket.reply", "tenant")}, tenant_id=_TENANT_A)
    same_value_different_object = uuid.UUID(str(_TENANT_A))
    assert same_value_different_object is not _TENANT_A  # misma UUID, objeto distinto
    resource = Resource(tenant_id=same_value_different_object)
    result = authorize(subject, "ticket.reply", "tenant", resource)
    assert isinstance(result, Allow)


def test_tenant_mismatch_compares_by_value_not_identity() -> None:
    """Un tenant_id de recurso con el MISMO valor que uno ajeno (objeto distinto) también deniega."""
    subject = _subject({("ticket.reply", "tenant")}, tenant_id=_TENANT_A)
    other_tenant_same_value = uuid.UUID(str(_TENANT_B))
    resource = Resource(tenant_id=other_tenant_same_value)
    result = authorize(subject, "ticket.reply", "tenant", resource)
    assert isinstance(result, Deny)
    assert result.reason is DenyReason.out_of_scope


def test_deny_is_immutable() -> None:
    """Deny es un dataclass frozen: reasignar `.reason` tras crearlo lanza (no se puede mutar)."""
    deny = Deny(DenyReason.no_capability)
    with pytest.raises(AttributeError):
        deny.reason = DenyReason.out_of_scope  # type: ignore[misc]


def test_allow_is_immutable() -> None:
    """Allow es un dataclass frozen: asignar un atributo nuevo tras crearlo lanza."""
    allow = Allow()
    with pytest.raises(AttributeError):
        allow.x = 1  # type: ignore[attr-defined]


def test_scope_other_than_tenant_or_global_never_matches_tenant_check() -> None:
    """Un scope arbitrario (ni 'tenant' ni 'global') no dispara la comparación de tenant como 'tenant' sí."""
    subject = _subject({("weird.action", "zzz")}, tenant_id=_TENANT_A)
    resource = Resource(tenant_id=_TENANT_B)  # cross-tenant, pero scope no es "tenant"
    result = authorize(subject, "weird.action", "zzz", resource)
    assert isinstance(result, Allow)  # "zzz" != "tenant" → no se compara tenant, se permite


@pytest.mark.parametrize(
    ("tenant_a", "tenant_b"),
    [
        (uuid.UUID(int=1), uuid.UUID(int=2)),  # subject < resource
        (uuid.UUID(int=2), uuid.UUID(int=1)),  # subject > resource
    ],
)
def test_tenant_mismatch_denies_in_both_orderings(tenant_a: uuid.UUID, tenant_b: uuid.UUID) -> None:
    """El mismatch de tenant deniega sin importar el orden relativo de los UUID."""
    subject = _subject({("ticket.reply", "tenant")}, tenant_id=tenant_a)
    resource = Resource(tenant_id=tenant_b)
    result = authorize(subject, "ticket.reply", "tenant", resource)
    assert isinstance(result, Deny)
    assert result.reason is DenyReason.out_of_scope


def test_custom_role_rejects_only_exact_global_scope() -> None:
    """validate_role_composition solo rechaza scope=='global' exacto, no un scope lexicográficamente menor."""
    composer_capabilities = {("ticket.reply", "aaa")}
    validate_role_composition(
        composer_capabilities, {("ticket.reply", "aaa")}
    )  # no lanza: no es global
