"""UniqueConstraint(document_id, ordinal) en kb_chunk.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-21

Defensa en profundidad (tarea `backend-kb-ingestion-02`) de la clave natural que usa la detección de
"chunk sin cambios" del pipeline de ingestión (`(document_id, ordinal)`, comparación de contenido, sin
columna de hash — decisión de `grilling` del plan `kb-ingestion`). Aditiva y sin backfill (no añade
columna): dos `kb_chunk` del mismo documento nunca deben compartir `ordinal`, y hoy nada lo impedía a
nivel de BD.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT_NAME = "uq_kb_chunk_document_id"
"""Nombre derivado de la MISMA `naming_convention` que `app.infra.db.base.Base.metadata`
(`"uq": "uq_%(table_name)s_%(column_0_name)s"` — solo usa la PRIMERA columna, aunque el constraint
tenga dos). Debe coincidir exactamente con lo que generaría el modelo ORM, o `compare_metadata`
(`tests/test_migration.py::test_models_do_not_drift_from_schema`) reportaría drift de nombre."""


def upgrade() -> None:
    op.create_unique_constraint(_CONSTRAINT_NAME, "kb_chunk", ["document_id", "ordinal"])


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT_NAME, "kb_chunk", type_="unique")
