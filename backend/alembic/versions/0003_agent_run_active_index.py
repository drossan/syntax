"""índice único parcial en agent_run(ticket_id) para runs no terminales.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-20

CAS real contra la carrera "dos runs activos a la vez" para el mismo ticket (`design-review` #1 del
plan `routers-flujo-ia`, tarea 01): `agent_service.trigger()` hace un pre-check best-effort
(`get_active_for_ticket`) antes de crear el `AgentRun`, pero eso es check-then-act — con dos requests
concurrentes ambas pueden ver "sin run activo" antes de que cualquiera inserte. Este índice único
**parcial** (`WHERE status IN ('queued', 'running')`) es la garantía atómica real: el segundo `INSERT`
concurrente viola la constraint y Postgres lo rechaza con `IntegrityError`, que el adaptador
(`SqlAlchemyAgentRunRepository.add`) traduce a `app.domain.errors.Conflict`.

Runs ya terminales (`succeeded`/`failed`) no cuentan para el índice: un ticket reabierto puede lanzar
un run nuevo (`run_seq` siguiente) sin chocar con uno anterior ya cerrado.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX_NAME = "ix_agent_run_active_per_ticket"
_PARTIAL_PREDICATE = sa.text("status IN ('queued', 'running')")


def upgrade() -> None:
    op.create_index(
        _INDEX_NAME,
        "agent_run",
        ["ticket_id"],
        unique=True,
        postgresql_where=_PARTIAL_PREDICATE,
    )


def downgrade() -> None:
    op.drop_index(_INDEX_NAME, table_name="agent_run")
