"""app.infra.db.base — fundamento ORM de SQLAlchemy 2 (DeclarativeBase + mixins).

`Base` centraliza la ``MetaData`` con una ``naming_convention`` explícita para que
Alembic genere nombres de constraints/índices **deterministas** (diffs estables). Los
mixins ``TimestampMixin``/``TenantMixin`` inyectan columnas comunes en los modelos
(tareas 03/04/05). ``Base.metadata`` es el ``target_metadata`` de ``alembic/env.py`` (06).

Anti-patrón (hexagonal, NFR-003): ``app.domain`` **no** importa este módulo — el dominio
no conoce SQLAlchemy. Sin efectos en import: solo definiciones de clase/metadata.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
"""Plantillas de nombre por tipo de constraint → Alembic las usa para nombres estables."""


class Base(DeclarativeBase):
    """DeclarativeBase raíz: su ``metadata`` lleva la naming_convention compartida."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    """Aporta ``created_at``/``updated_at`` (``timestamptz`` UTC, gestionados por la DB).

    ``server_default=now()`` los rellena en el INSERT; ``onupdate=now()`` refresca
    ``updated_at`` en cada UPDATE. Ambos NOT NULL y timezone-aware.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class TenantMixin:
    """Aporta ``tenant_id`` (UUID NOT NULL, FK→``tenant.id``): marca de tabla de negocio con RLS.

    Solo lo heredan las 7 tablas de negocio (tarea 04). Las de identidad/RBAC y KB **no**
    lo llevan (§6 de data-model.md): su aislamiento no es RLS de fila.
    """

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), nullable=False)
