"""app.infra.db.models.business — modelos ORM de negocio (data-model.md §4.2).

Grupo con ``tenant_id`` (vía ``TenantMixin``): son las **únicas** tablas con RLS (§2/§6). Cascadas §7
(``SET NULL`` en actores para preservar histórico; ``CASCADE`` en el agregado del ticket y en la KB del
usuario) e índices compuestos §9. Los CHECK de rango (``csat`` 1..5, ``confidence`` 0..1) van en la
migración (06), no en el modelo. Sin efectos en import.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.db.base import Base, TenantMixin, TimestampMixin
from app.infra.db.models.enums import (
    AgentRunStatus,
    ApprovalStatus,
    KbDomain,
    MessageVisibility,
    NotificationType,
    TicketPriority,
    TicketStatus,
    pg_enum,
)


def _created_at() -> Mapped[datetime]:
    """Columna ``created_at`` timestamptz NOT NULL con ``server_default=now()`` (tablas sin updated_at)."""
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class Ticket(TenantMixin, TimestampMixin, Base):
    """Ticket de soporte. ``domain``/``priority`` los fija el clasificador (05)."""

    __tablename__ = "ticket"
    __table_args__ = (
        Index("ix_ticket_tenant_status", "tenant_id", "status"),
        Index("ix_ticket_tenant_assignee", "tenant_id", "assignee_id"),
        Index("ix_ticket_tenant_sla_due", "tenant_id", "sla_due"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    subject: Mapped[str] = mapped_column(Text)
    status: Mapped[TicketStatus] = mapped_column(pg_enum(TicketStatus, "ticket_status"))
    priority: Mapped[TicketPriority] = mapped_column(pg_enum(TicketPriority, "ticket_priority"))
    domain: Mapped[KbDomain | None] = mapped_column(pg_enum(KbDomain, "kb_domain"), nullable=True)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    requester_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    sla_due: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    csat: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)


class Message(TenantMixin, Base):
    """Mensaje de un ticket. ``author_id`` nullable (mensajes generados por IA sin autor humano)."""

    __tablename__ = "message"
    __table_args__ = (Index("ix_message_ticket_created", "ticket_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ticket_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ticket.id", ondelete="CASCADE"))
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    visibility: Mapped[MessageVisibility] = mapped_column(
        pg_enum(MessageVisibility, "message_visibility")
    )
    is_ai_draft: Mapped[bool] = mapped_column(default=False)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()


class Attachment(TenantMixin, Base):
    """Adjunto de un mensaje. El binario vive fuera de Postgres (``storage_key`` → puerto storage)."""

    __tablename__ = "attachment"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("message.id", ondelete="CASCADE"))
    filename: Mapped[str] = mapped_column(String)
    content_type: Mapped[str] = mapped_column(String)
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = _created_at()


class AgentRun(TenantMixin, Base):
    """Una ejecución del grafo LangGraph (``failed`` = fallo del LLM; ``sources`` = citas JSONB)."""

    __tablename__ = "agent_run"
    __table_args__ = (
        Index("ix_agent_run_ticket_seq", "ticket_id", "run_seq"),
        Index("ix_agent_run_thread", "langgraph_thread_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ticket_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ticket.id", ondelete="CASCADE"))
    langgraph_thread_id: Mapped[str] = mapped_column(String)
    run_seq: Mapped[int] = mapped_column(Integer)
    status: Mapped[AgentRunStatus] = mapped_column(pg_enum(AgentRunStatus, "agent_run_status"))
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    escalated: Mapped[bool] = mapped_column(default=False)
    sources: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    langsmith_trace_url: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = _created_at()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ApprovalTask(TenantMixin, Base):
    """Tarea HITL: draft del agente que un humano aprueba/edita/rechaza (idempotente si no-pending)."""

    __tablename__ = "approval_task"
    __table_args__ = (Index("ix_approval_task_tenant_status", "tenant_id", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ticket_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ticket.id", ondelete="CASCADE"))
    agent_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_run.id", ondelete="CASCADE"))
    status: Mapped[ApprovalStatus] = mapped_column(pg_enum(ApprovalStatus, "approval_status"))
    draft_body: Mapped[str] = mapped_column(Text)
    final_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    human_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created_at()


class AuditLog(TenantMixin, Base):
    """Auditoría append-only de mutaciones. ``actor_id`` SET NULL para no bloquear el borrado del actor."""

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String)
    entity_type: Mapped[str] = mapped_column(String)
    entity_id: Mapped[str] = mapped_column(String)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at()


class Notification(TenantMixin, Base):
    """Notificación in-app (entrega por polling en Fase 1)."""

    __tablename__ = "notification"
    __table_args__ = (Index("ix_notification_user_read", "user_id", "read_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    type: Mapped[NotificationType] = mapped_column(pg_enum(NotificationType, "notification_type"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created_at()
