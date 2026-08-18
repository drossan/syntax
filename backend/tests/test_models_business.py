"""Tests de los modelos ORM de negocio (tarea 04) — nivel metadata, unit.

Grupo con ``tenant_id`` (TenantMixin) → únicas con RLS (data-model §2/§6). Verifica registro,
tenant_id NOT NULL, enums (conjunto exacto contra §3), cascadas §7 e índices compuestos §9.
"""

import pytest
from app.infra.db.base import Base, TenantMixin
from app.infra.db.models import (
    AgentRun,
    ApprovalTask,
    Attachment,
    AuditLog,
    Message,
    Notification,
    Ticket,
)
from app.infra.db.models.enums import (
    AgentRunStatus,
    ApprovalStatus,
    MessageVisibility,
    NotificationType,
    TicketPriority,
    TicketStatus,
)

_BUSINESS_TABLES = {
    "ticket",
    "message",
    "attachment",
    "approval_task",
    "agent_run",
    "audit_log",
    "notification",
}

_BUSINESS_MODELS = [Ticket, Message, Attachment, ApprovalTask, AgentRun, AuditLog, Notification]


def _fk_ondelete(model: type, column: str) -> str | None:
    """ondelete de la (única) FK de una columna."""
    return next(iter(model.__table__.c[column].foreign_keys)).ondelete


def _index_column_tuples(model: type) -> list[tuple[str, ...]]:
    """Tuplas ordenadas de columnas de cada índice del modelo."""
    return [tuple(col.name for col in index.columns) for index in model.__table__.indexes]


def test_seven_business_tables_registered() -> None:
    """Las 7 tablas de negocio están registradas en Base.metadata."""
    assert set(Base.metadata.tables) >= _BUSINESS_TABLES


def test_every_business_model_uses_tenant_mixin() -> None:
    """Todo modelo de negocio hereda TenantMixin → tenant_id UUID NOT NULL FK tenant (marca RLS)."""
    for model in _BUSINESS_MODELS:
        assert issubclass(model, TenantMixin), model.__name__
        tenant_col = model.__table__.c["tenant_id"]
        assert tenant_col.nullable is False
        assert next(iter(tenant_col.foreign_keys)).target_fullname == "tenant.id"


def test_message_visibility_excludes_developer() -> None:
    """message_visibility NO incluye 'developer' en Fase 1."""
    assert "developer" not in Message.__table__.c["visibility"].type.enums


def test_agent_run_status_includes_failed() -> None:
    """agent_run_status incluye 'failed' (fallo del LLM a mitad de run)."""
    assert "failed" in AgentRun.__table__.c["status"].type.enums


@pytest.mark.parametrize(
    ("model", "column", "expected"),
    [
        (Ticket, "requester_id", "SET NULL"),
        (Ticket, "assignee_id", "SET NULL"),
        (Message, "ticket_id", "CASCADE"),
        (Message, "author_id", "SET NULL"),
        (Attachment, "message_id", "CASCADE"),
        (ApprovalTask, "decided_by", "SET NULL"),
        (AgentRun, "ticket_id", "CASCADE"),
        (AuditLog, "actor_id", "SET NULL"),
        (Notification, "user_id", "CASCADE"),
    ],
)
def test_fk_cascades_follow_data_model(model: type, column: str, expected: str) -> None:
    """Las cascadas de FK siguen data-model §7 (SET NULL en actores, CASCADE en el agregado)."""
    assert _fk_ondelete(model, column) == expected


@pytest.mark.parametrize(
    ("model", "attr", "expected"),
    [
        (Ticket, "status", {"new", "open", "pending", "resolved", "closed", "reopened"}),
        (Ticket, "priority", {"low", "normal", "high", "urgent"}),
        (ApprovalTask, "status", {"pending", "approved", "edited", "rejected"}),
        (
            Notification,
            "type",
            {"approval_requested", "ticket_assigned", "ticket_reply", "sla_breach", "sla_warning"},
        ),
        (Message, "visibility", {"public", "internal"}),
        (AgentRun, "status", {"queued", "running", "succeeded", "failed"}),
    ],
)
def test_business_enum_has_exact_value_set(model: type, attr: str, expected: set[str]) -> None:
    """Cada enum de negocio tiene EXACTAMENTE su conjunto de valores de data-model §3."""
    assert set(model.__table__.c[attr].type.enums) == expected


@pytest.mark.parametrize(
    ("model", "columns"),
    [
        (Ticket, ("tenant_id", "status")),
        (Ticket, ("tenant_id", "sla_due")),
        (Message, ("ticket_id", "created_at")),
        (ApprovalTask, ("tenant_id", "status")),
        (Notification, ("user_id", "read_at")),
    ],
)
def test_composite_indexes_exist(model: type, columns: tuple[str, ...]) -> None:
    """Los índices compuestos de data-model §9 están declarados en los modelos."""
    assert columns in _index_column_tuples(model)


def test_enum_python_values_match_spec() -> None:
    """Los enums Python de negocio exponen exactamente los valores del contrato §3."""
    assert {m.value for m in TicketStatus} == {
        "new",
        "open",
        "pending",
        "resolved",
        "closed",
        "reopened",
    }
    assert {m.value for m in TicketPriority} == {"low", "normal", "high", "urgent"}
    assert {m.value for m in MessageVisibility} == {"public", "internal"}
    assert {m.value for m in ApprovalStatus} == {"pending", "approved", "edited", "rejected"}
    assert {m.value for m in AgentRunStatus} == {"queued", "running", "succeeded", "failed"}
    assert {m.value for m in NotificationType} == {
        "approval_requested",
        "ticket_assigned",
        "ticket_reply",
        "sla_breach",
        "sla_warning",
    }
