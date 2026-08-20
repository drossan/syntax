"""initial schema — extensión pgvector, 18 tablas, GRANTs a syntax_app y RLS multi-tenant.

Revision ID: 0001
Revises:
Create Date: 2026-08-16

**Congelada** (backend-routers-core-01, 2026-08-19): originalmente materializaba el schema desde
``Base.metadata`` (== los modelos ORM en vivo). Eso funcionaba mientras hubiera una sola migración,
pero rompía cualquier migración incremental posterior: al editar los modelos para `0002`, esta
revisión habría empezado a generar el schema NUEVO directamente, dejando a `0002` sin nada real que
alterar (footgun descubierto al implementar `0002`). Ahora define su propio ``MetaData`` con las 18
tablas **autocontenidas** (no importa `app.infra.db.models`/``Base``): reproduce el shape histórico
exacto de antes del rediseño de identidad (`user` con `tenant_id`/`status` propios, sin
`user_tenant`, `refresh_session` sin `tenant_id`, `tenant` sin `auto_approve`). Los enums (valores)
siguen viniendo de `app.infra.db.models.enums` — es un módulo de **contrato de valores** (data-model.md
§3), no de estructura de tablas, así que no está sujeto al mismo problema.
Escrita a mano (autogenerate no emite extensión, GRANTs ni RLS). Añade a mano:
  - `CREATE EXTENSION vector` (antes de crear tablas: `embedding.vector` la necesita).
  - CHECK de rango (fuera del modelo, decisión owner): csat 1..5, confidence 0..1, role system.
  - GRANTs DML al rol runtime `syntax_app` (creado fuera de Alembic — init script / ops).
  - RLS + `CREATE POLICY tenant_isolation` en las 7 tablas de negocio (bypass GUC + 2-arg, H2).
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from app.infra.db.models.enums import (
    AgentRunStatus,
    ApprovalStatus,
    AuthTokenKind,
    CapabilityScope,
    KbDomain,
    KbEstado,
    MessageVisibility,
    NotificationType,
    RefreshSessionStatus,
    RoleKind,
    TenantStatus,
    TicketPriority,
    TicketStatus,
    UserStatus,
    pg_enum,
)
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Las 7 tablas de NEGOCIO (data-model §2/§6): las únicas con RLS de tenant.
BUSINESS_TABLES: tuple[str, ...] = (
    "ticket",
    "message",
    "attachment",
    "approval_task",
    "agent_run",
    "audit_log",
    "notification",
)

# Predicado exacto de la policy (H2): bypass por GUC transaccional O match de tenant.
# `current_setting(..., true)` (2 args, missing_ok) → NULL si el GUC no está, pero tras un
# `SET LOCAL` previo sobre una conexión del pool reutilizada devuelve '' (cadena vacía), no NULL:
# el `NULLIF(..., '')` lo normaliza a NULL → `NULL::uuid` = NULL → 0 filas (fail-closed), en vez de
# `''::uuid` que lanzaría. El ámbito `global` activa `app.bypass_rls='on'` por transacción (07).
_POLICY_PREDICATE = (
    "current_setting('app.bypass_rls', true) = 'on' "
    "OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"
)

# ─────────────────────────── Schema congelado (shape histórico de 0001) ───────────────────────────

_NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
"""Copia literal de `app.infra.db.base.NAMING_CONVENTION` — mismo patrón, cero import de modelos."""

metadata = sa.MetaData(naming_convention=_NAMING_CONVENTION)


def _timestamp_columns() -> list[sa.Column[Any]]:
    """``created_at``/``updated_at`` timestamptz NOT NULL (equivalente a ``TimestampMixin``)."""
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    ]


def _created_at_column() -> sa.Column[Any]:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


# ── Identidad / RBAC (8) — shape ANTERIOR al rediseño multi-tenant de 0002 ──

sa.Table(
    "tenant",
    metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("slug", sa.String(), nullable=False),
    sa.Column("name", sa.String(), nullable=False),
    sa.Column("status", pg_enum(TenantStatus, "tenant_status"), nullable=False),
    *_timestamp_columns(),
    sa.UniqueConstraint("slug"),
)

sa.Table(
    "user",
    metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column(
        "tenant_id", sa.Uuid(), sa.ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False
    ),
    sa.Column("email", sa.String(), nullable=False),
    sa.Column("password_hash", sa.String(), nullable=True),
    sa.Column("status", pg_enum(UserStatus, "user_status"), nullable=False),
    sa.Column("sso_subject", sa.String(), nullable=True),
    *_timestamp_columns(),
    sa.UniqueConstraint("tenant_id", "email"),
)

sa.Table(
    "capability",
    metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("name", sa.String(), nullable=False),
    sa.Column("scope", pg_enum(CapabilityScope, "capability_scope"), nullable=False),
    sa.Column("description", sa.String(), nullable=True),
    sa.UniqueConstraint("name"),
)

sa.Table(
    "role",
    metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("name", sa.String(), nullable=False),
    sa.Column("kind", pg_enum(RoleKind, "role_kind"), nullable=False),
    sa.Column(
        "tenant_id", sa.Uuid(), sa.ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=True
    ),
    sa.Column("description", sa.String(), nullable=True),
    *_timestamp_columns(),
    sa.UniqueConstraint("tenant_id", "name"),
)

sa.Table(
    "role_capability",
    metadata,
    sa.Column("role_id", sa.Uuid(), sa.ForeignKey("role.id", ondelete="CASCADE"), primary_key=True),
    sa.Column(
        "capability_id",
        sa.Uuid(),
        sa.ForeignKey("capability.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

sa.Table(
    "user_role",
    metadata,
    sa.Column("user_id", sa.Uuid(), sa.ForeignKey("user.id", ondelete="CASCADE"), primary_key=True),
    sa.Column("role_id", sa.Uuid(), sa.ForeignKey("role.id", ondelete="CASCADE"), primary_key=True),
    sa.Column(
        "tenant_id", sa.Uuid(), sa.ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=True
    ),
)

sa.Table(
    "refresh_session",
    metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("user_id", sa.Uuid(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
    sa.Column("token_hash", sa.String(), nullable=False),
    sa.Column("family_id", sa.Uuid(), nullable=False),
    sa.Column("parent_id", sa.Uuid(), sa.ForeignKey("refresh_session.id"), nullable=True),
    sa.Column("status", pg_enum(RefreshSessionStatus, "refresh_session_status"), nullable=False),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    _created_at_column(),
    sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("user_agent", sa.String(), nullable=True),
    sa.Column("ip", sa.String(), nullable=True),
    sa.UniqueConstraint("token_hash"),
)

sa.Table(
    "auth_token",
    metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("user_id", sa.Uuid(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
    sa.Column("kind", pg_enum(AuthTokenKind, "auth_token_kind"), nullable=False),
    sa.Column("token_hash", sa.String(), nullable=False),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    _created_at_column(),
    sa.UniqueConstraint("token_hash"),
)

# ── Negocio (7) — TenantMixin (tenant_id NOT NULL FK→tenant, RESTRICT) ──

sa.Table(
    "ticket",
    metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column(
        "tenant_id", sa.Uuid(), sa.ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False
    ),
    sa.Column("subject", sa.Text(), nullable=False),
    sa.Column("status", pg_enum(TicketStatus, "ticket_status"), nullable=False),
    sa.Column("priority", pg_enum(TicketPriority, "ticket_priority"), nullable=False),
    sa.Column("domain", pg_enum(KbDomain, "kb_domain"), nullable=True),
    sa.Column("category", sa.String(), nullable=True),
    sa.Column(
        "requester_id", sa.Uuid(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    ),
    sa.Column(
        "assignee_id", sa.Uuid(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    ),
    sa.Column("sla_due", sa.DateTime(timezone=True), nullable=True),
    sa.Column("csat", sa.SmallInteger(), nullable=True),
    *_timestamp_columns(),
    sa.Index("ix_ticket_tenant_status", "tenant_id", "status"),
    sa.Index("ix_ticket_tenant_assignee", "tenant_id", "assignee_id"),
    sa.Index("ix_ticket_tenant_sla_due", "tenant_id", "sla_due"),
)

sa.Table(
    "message",
    metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column(
        "tenant_id", sa.Uuid(), sa.ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False
    ),
    sa.Column(
        "ticket_id", sa.Uuid(), sa.ForeignKey("ticket.id", ondelete="CASCADE"), nullable=False
    ),
    sa.Column("author_id", sa.Uuid(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
    sa.Column("visibility", pg_enum(MessageVisibility, "message_visibility"), nullable=False),
    sa.Column("is_ai_draft", sa.Boolean(), nullable=False, default=False),
    sa.Column("body", sa.Text(), nullable=False),
    _created_at_column(),
    sa.Index("ix_message_ticket_created", "ticket_id", "created_at"),
)

sa.Table(
    "attachment",
    metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column(
        "tenant_id", sa.Uuid(), sa.ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False
    ),
    sa.Column(
        "message_id", sa.Uuid(), sa.ForeignKey("message.id", ondelete="CASCADE"), nullable=False
    ),
    sa.Column("filename", sa.String(), nullable=False),
    sa.Column("content_type", sa.String(), nullable=False),
    sa.Column("size_bytes", sa.Integer(), nullable=False),
    sa.Column("storage_key", sa.String(), nullable=False),
    _created_at_column(),
)

sa.Table(
    "agent_run",
    metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column(
        "tenant_id", sa.Uuid(), sa.ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False
    ),
    sa.Column(
        "ticket_id", sa.Uuid(), sa.ForeignKey("ticket.id", ondelete="CASCADE"), nullable=False
    ),
    sa.Column("langgraph_thread_id", sa.String(), nullable=False),
    sa.Column("run_seq", sa.Integer(), nullable=False),
    sa.Column("status", pg_enum(AgentRunStatus, "agent_run_status"), nullable=False),
    sa.Column("confidence", sa.Float(), nullable=True),
    sa.Column("escalated", sa.Boolean(), nullable=False, default=False),
    sa.Column("sources", JSONB(), nullable=True),
    sa.Column("error", sa.Text(), nullable=True),
    sa.Column("langsmith_trace_url", sa.String(), nullable=True),
    _created_at_column(),
    sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    sa.Index("ix_agent_run_ticket_seq", "ticket_id", "run_seq"),
    sa.Index("ix_agent_run_thread", "langgraph_thread_id"),
)

sa.Table(
    "approval_task",
    metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column(
        "tenant_id", sa.Uuid(), sa.ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False
    ),
    sa.Column(
        "ticket_id", sa.Uuid(), sa.ForeignKey("ticket.id", ondelete="CASCADE"), nullable=False
    ),
    sa.Column(
        "agent_run_id", sa.Uuid(), sa.ForeignKey("agent_run.id", ondelete="CASCADE"), nullable=False
    ),
    sa.Column("status", pg_enum(ApprovalStatus, "approval_status"), nullable=False),
    sa.Column("draft_body", sa.Text(), nullable=False),
    sa.Column("final_body", sa.Text(), nullable=True),
    sa.Column("human_note", sa.Text(), nullable=True),
    sa.Column(
        "decided_by", sa.Uuid(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    ),
    sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    _created_at_column(),
    sa.Index("ix_approval_task_tenant_status", "tenant_id", "status"),
)

sa.Table(
    "audit_log",
    metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column(
        "tenant_id", sa.Uuid(), sa.ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False
    ),
    sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
    sa.Column("action", sa.String(), nullable=False),
    sa.Column("entity_type", sa.String(), nullable=False),
    sa.Column("entity_id", sa.String(), nullable=False),
    sa.Column("payload", JSONB(), nullable=False),
    _created_at_column(),
)

sa.Table(
    "notification",
    metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column(
        "tenant_id", sa.Uuid(), sa.ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False
    ),
    sa.Column("user_id", sa.Uuid(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
    sa.Column("type", pg_enum(NotificationType, "notification_type"), nullable=False),
    sa.Column("payload", JSONB(), nullable=False),
    sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    _created_at_column(),
    sa.Index("ix_notification_user_read", "user_id", "read_at"),
)

# ── KB (3) — global, sin tenant_id/RLS ──

sa.Table(
    "kb_document",
    metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("uc_id", sa.String(), nullable=False),
    sa.Column("domain", pg_enum(KbDomain, "kb_domain"), nullable=False),
    sa.Column("package", sa.String(), nullable=False),
    sa.Column("estado", pg_enum(KbEstado, "kb_estado"), nullable=False),
    sa.Column("title", sa.Text(), nullable=False),
    sa.Column("source_url", sa.String(), nullable=False),
    sa.Column("traza", JSONB(), nullable=True),
    sa.Column("updated", sa.DateTime(timezone=True), nullable=True),
    *_timestamp_columns(),
    sa.UniqueConstraint("uc_id"),
    sa.Index("ix_kb_document_domain", "domain"),
)

sa.Table(
    "kb_chunk",
    metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column(
        "document_id",
        sa.Uuid(),
        sa.ForeignKey("kb_document.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("section_type", sa.String(), nullable=False),
    sa.Column("content", sa.Text(), nullable=False),
    sa.Column("token_count", sa.Integer(), nullable=False),
    sa.Column("ordinal", sa.Integer(), nullable=False),
    _created_at_column(),
    sa.Index("ix_kb_chunk_document", "document_id"),
)

sa.Table(
    "embedding",
    metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column(
        "chunk_id", sa.Uuid(), sa.ForeignKey("kb_chunk.id", ondelete="CASCADE"), nullable=False
    ),
    sa.Column("model", sa.String(), nullable=False),
    sa.Column("vector", Vector(1536), nullable=False),
    _created_at_column(),
    sa.UniqueConstraint("chunk_id"),
)


def upgrade() -> None:
    bind = op.get_bind()

    # 1) Extensión pgvector (antes de create_all: `embedding.vector` es vector(1536)).
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 2) Las 18 tablas + enums nativos + FKs/cascadas + índices (schema congelado de arriba).
    metadata.create_all(bind=bind)

    # 3) CHECK de rango (no viven en el modelo — decisión owner). La naming_convention añade
    #    el prefijo `ck_<tabla>_`, así que el nombre aquí es solo el sufijo semántico.
    op.create_check_constraint("csat_range", "ticket", "csat IS NULL OR csat BETWEEN 1 AND 5")
    op.create_check_constraint(
        "confidence_range", "agent_run", "confidence IS NULL OR confidence BETWEEN 0 AND 1"
    )
    # role.tenant_id es NULL sii el rol es de sistema (coherencia system/tenant, 02 §4).
    op.create_check_constraint(
        "tenant_system", "role", "(tenant_id IS NULL) = (kind::text = 'system')"
    )

    # 4) GRANTs DML al rol runtime `syntax_app` (existe ya: init script / ops, ADR-0016).
    op.execute("GRANT USAGE ON SCHEMA public TO syntax_app")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO syntax_app")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO syntax_app")

    # 5) RLS + policy tenant_isolation en las 7 de negocio (KB e identidad NO llevan RLS).
    for table in BUSINESS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING ({_POLICY_PREDICATE}) "
            f"WITH CHECK ({_POLICY_PREDICATE})"
        )


def downgrade() -> None:
    bind = op.get_bind()

    # Revierte RLS (el rol syntax_app se gestiona FUERA de Alembic: no se toca aquí).
    for table in BUSINESS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    # Los CHECK caen con sus tablas en drop_all; los enums nativos también (create_type).
    metadata.drop_all(bind=bind)
    # La extensión `vector` se deja instalada (barata; re-upgrade la reusa con IF NOT EXISTS).
