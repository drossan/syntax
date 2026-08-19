"""identidad multi-tenant global — user global + user_tenant + refresh_session.tenant_id + tenant.auto_approve.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-19

Rediseña identidad para que un mismo usuario pertenezca a varios tenants con una sola contraseña
(decisión de owner tras `grilling`/`design-review` del plan `routers-core`, tarea 01): `user` deja de
tener `tenant_id`/`status` propios (email único **global**); el `status` por tenant pasa a la tabla
nueva `user_tenant`; `refresh_session` gana `tenant_id` (una sesión es de un tenant concreto);
`tenant` gana `auto_approve` (consumidor real: tarea 15, HITL `decide`).

Sin backfill de datos: repo pre-lanzamiento, sin datos de producción (owner, confirmado en
`grilling`). Reutiliza el enum nativo `user_status` ya creado por `0001` (`create_type=False`): no se
recrea el tipo, solo se referencia en la columna nueva de `user_tenant`.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_USER_STATUS = postgresql.ENUM(
    "invited", "active", "disabled", name="user_status", create_type=False
)
"""Referencia al tipo `user_status` ya creado por `0001` — `create_type=False` evita re-crearlo."""


def upgrade() -> None:
    # `user`: pierde tenant_id/status; email pasa a único GLOBAL (antes único por tenant).
    op.drop_constraint("fk_user_tenant_id_tenant", "user", type_="foreignkey")
    op.drop_constraint("uq_user_tenant_id", "user", type_="unique")
    op.drop_column("user", "status")
    op.drop_column("user", "tenant_id")
    op.create_unique_constraint("uq_user_email", "user", ["email"])

    # `user_tenant` (nueva): status POR membership. PK compuesta natural (user_id, tenant_id).
    op.create_table(
        "user_tenant",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("status", _USER_STATUS, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name="fk_user_tenant_user_id_user", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name="fk_user_tenant_tenant_id_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("user_id", "tenant_id", name="pk_user_tenant"),
    )
    op.create_index("ix_user_tenant_tenant_id", "user_tenant", ["tenant_id"])

    # `refresh_session`: una sesión de refresh es de un tenant concreto (elegido en select/switch_tenant).
    op.add_column("refresh_session", sa.Column("tenant_id", sa.Uuid(), nullable=False))
    op.create_foreign_key(
        "fk_refresh_session_tenant_id_tenant",
        "refresh_session",
        "tenant",
        ["tenant_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # `tenant.auto_approve`: lo configura el admin del tenant (consumidor real: tarea 15).
    op.add_column(
        "tenant",
        sa.Column("auto_approve", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("tenant", "auto_approve")

    op.drop_constraint("fk_refresh_session_tenant_id_tenant", "refresh_session", type_="foreignkey")
    op.drop_column("refresh_session", "tenant_id")

    op.drop_index("ix_user_tenant_tenant_id", table_name="user_tenant")
    op.drop_table("user_tenant")

    op.drop_constraint("uq_user_email", "user", type_="unique")
    op.add_column("user", sa.Column("tenant_id", sa.Uuid(), nullable=False))
    op.add_column("user", sa.Column("status", _USER_STATUS, nullable=False))
    op.create_foreign_key(
        "fk_user_tenant_id_tenant", "user", "tenant", ["tenant_id"], ["id"], ondelete="RESTRICT"
    )
    op.create_unique_constraint("uq_user_tenant_id", "user", ["tenant_id", "email"])
