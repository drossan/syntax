"""Tests de app.domain.entities — entidades propias del dominio (tarea backend-domain-services-01).

Nivel unit, sin infra. Verifica: el dominio no importa infra/SQLAlchemy (hexagonal, NFR-003); los enums
propios tienen el MISMO conjunto de valores que app.infra.db.models.enums (test de drift, por valor, no
por nombre); las entidades nuevas (Subject/Resource/AuditLogEntry) tienen la forma que sus consumidores
necesitan; un valor de enum inválido es rechazado por Pydantic.
"""

import ast
import importlib
import pkgutil
import uuid
from pathlib import Path

import app.domain
import pytest
from app.domain.entities import business as domain_business
from app.domain.entities import enums as domain_enums
from app.domain.entities import identity as domain_identity
from app.infra.db.models import enums as orm_enums
from pydantic import ValidationError

_DOMAIN_ROOT = Path(app.domain.__file__).parent


def _iter_domain_modules() -> list[str]:
    """Nombres de todos los módulos bajo app.domain (recursivo)."""
    names = []
    for module_info in pkgutil.walk_packages([str(_DOMAIN_ROOT)], prefix="app.domain."):
        names.append(module_info.name)
    return names


def _imports_forbidden(module_name: str) -> list[str]:
    """Imports de nivel top prohibidos (app.infra / sqlalchemy) en el fichero fuente del módulo."""
    module = importlib.import_module(module_name)
    if module.__file__ is None:
        return []
    tree = ast.parse(Path(module.__file__).read_text())
    forbidden = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            forbidden.extend(
                alias.name
                for alias in node.names
                if alias.name.startswith(("app.infra", "sqlalchemy"))
            )
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith(("app.infra", "sqlalchemy"))
        ):
            forbidden.append(node.module)
    return forbidden


def test_domain_does_not_import_infra() -> None:
    """Ningún módulo de app.domain importa app.infra ni sqlalchemy."""
    offenders = {name: _imports_forbidden(name) for name in _iter_domain_modules()}
    offenders = {name: imports for name, imports in offenders.items() if imports}
    assert offenders == {}


_ENUM_PAIRS = [
    ("TicketStatus", "TicketStatus"),
    ("TicketPriority", "TicketPriority"),
    ("MessageVisibility", "MessageVisibility"),
    ("ApprovalStatus", "ApprovalStatus"),
    ("AgentRunStatus", "AgentRunStatus"),
    ("KbDomain", "KbDomain"),
    ("UserStatus", "UserStatus"),
    ("TenantStatus", "TenantStatus"),
    ("RoleKind", "RoleKind"),
    ("CapabilityScope", "CapabilityScope"),
    ("AuthTokenKind", "AuthTokenKind"),
    ("NotificationType", "NotificationType"),
    ("RefreshSessionStatus", "RefreshSessionStatus"),
]


@pytest.mark.parametrize(("domain_name", "orm_name"), _ENUM_PAIRS)
def test_enum_drift_by_value(domain_name: str, orm_name: str) -> None:
    """El enum de dominio y su equivalente ORM tienen el MISMO conjunto de valores (no de nombres)."""
    domain_enum = getattr(domain_enums, domain_name)
    orm_enum = getattr(orm_enums, orm_name)
    domain_values = {member.value for member in domain_enum}
    orm_values = {member.value for member in orm_enum}
    assert domain_values == orm_values


def test_subject_exposes_effective_capabilities() -> None:
    """Subject expone su conjunto efectivo de (capability, scope) consultable."""
    subject = domain_identity.Subject(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        capabilities={("ticket.reply", "tenant")},
    )
    assert ("ticket.reply", "tenant") in subject.capabilities


def test_resource_exposes_nullable_tenant_id() -> None:
    """Resource expone tenant_id, nullable para recursos globales (p.ej. KB)."""
    owned = domain_business.Resource(tenant_id=uuid.uuid4())
    assert owned.tenant_id is not None
    global_resource = domain_business.Resource(tenant_id=None)
    assert global_resource.tenant_id is None


def test_audit_log_entry_shape() -> None:
    """AuditLogEntry expone action, entity_type, entity_id, payload y actor_id (nullable)."""
    entry = domain_business.AuditLogEntry(
        tenant_id=uuid.uuid4(),
        action="ticket.created",
        entity_type="ticket",
        entity_id=str(uuid.uuid4()),
        payload={"status": "new"},
        actor_id=None,
    )
    assert entry.action == "ticket.created"
    assert entry.actor_id is None


def test_invalid_enum_value_is_rejected() -> None:
    """Un valor de enum inválido en un campo de entidad es rechazado por Pydantic."""
    with pytest.raises(ValidationError):
        domain_business.Ticket(
            id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            subject="s",
            status="not-a-real-status",  # type: ignore[arg-type]
            priority=domain_enums.TicketPriority.normal,
            domain=None,
            category=None,
            requester_id=None,
            assignee_id=None,
            sla_due=None,
            csat=None,
        )
