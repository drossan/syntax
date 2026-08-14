"""app.infra.db.base — DeclarativeBase de SQLAlchemy 2.

GUIÓN (→ tarea 08)
------------------
Qué implementar:
  - ``class Base(DeclarativeBase)`` (SQLAlchemy 2, tipado ``Mapped``/``mapped_column``).
  - Convención de nombres de constraints (``metadata.naming_convention``) para que Alembic genere
    nombres deterministas (evita autogenerados ilegibles y migraciones frágiles).
  - Mixins comunes: ``TimestampMixin`` (``created_at``/``updated_at`` ``timestamptz`` UTC) y, para las
    tablas de negocio, ``TenantMixin`` (``tenant_id`` ``UUID NOT NULL`` FK→``tenant``) — ver 03 §1.
  - ``target_metadata = Base.metadata`` es lo que consume ``alembic/env.py``.

Contrato: todos los modelos de ``models/`` heredan de ``Base``. Anti-patrón: exponer ``Base`` o los
modelos hacia ``app.domain`` (rompe hexagonal: el dominio no conoce SQLAlchemy).
"""
