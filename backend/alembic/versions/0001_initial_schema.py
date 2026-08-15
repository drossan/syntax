"""initial schema — extensión pgvector, 18 tablas, GRANTs a syntax_app y RLS multi-tenant.

Revision ID: 0001
Revises:
Create Date: 2026-08-16

Escrita a mano (autogenerate no emite extensión, GRANTs ni RLS). El schema de tablas/enums/
índices se materializa desde `Base.metadata` (== modelos, drift-test H3). Añade a mano:
  - `CREATE EXTENSION vector` (antes de crear tablas: `embedding.vector` la necesita).
  - CHECK de rango (fuera del modelo, decisión owner): csat 1..5, confidence 0..1, role system.
  - GRANTs DML al rol runtime `syntax_app` (creado fuera de Alembic — init script / ops).
  - RLS + `CREATE POLICY tenant_isolation` en las 7 tablas de negocio (bypass GUC + 2-arg, H2).
"""

from collections.abc import Sequence

import app.infra.db.models  # noqa: F401 — registra TODOS los modelos en Base.metadata
from alembic import op
from app.infra.db.base import Base

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
# `current_setting(..., true)` (2 args, missing_ok) → NULL si el GUC no está (fail-closed,
# no lanza). El ámbito `global` de Soporte activa `app.bypass_rls='on'` por transacción (07).
_POLICY_PREDICATE = (
    "current_setting('app.bypass_rls', true) = 'on' "
    "OR tenant_id = current_setting('app.tenant_id', true)::uuid"
)


def upgrade() -> None:
    bind = op.get_bind()

    # 1) Extensión pgvector (antes de create_all: `embedding.vector` es vector(1536)).
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 2) Las 18 tablas + enums nativos + FKs/cascadas + índices (desde los modelos).
    Base.metadata.create_all(bind=bind)

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
    Base.metadata.drop_all(bind=bind)
    # La extensión `vector` se deja instalada (barata; re-upgrade la reusa con IF NOT EXISTS).
