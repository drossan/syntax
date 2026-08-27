"""tenant.ai_auto_draft — dispara el draft IA automáticamente al crear un ticket.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-27

Setting por tenant (mismo patrón que `auto_approve`, migración `0002`), activable/desactivable por el
admin del tenant vía `PATCH /tenants/settings`. `server_default=true` — por defecto ACTIVO (decisión de
producto): al crear un ticket, si la IA puede responder lo responde (sujeto a `auto_approve`/HITL como
siempre); si no puede, deja el `human_note` explicando qué encontró o por qué no encontró nada.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenant",
        sa.Column("ai_auto_draft", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("tenant", "ai_auto_draft")
