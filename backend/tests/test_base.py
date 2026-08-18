"""Tests de app.infra.db.base — fundamento ORM determinista (nivel metadata, unit).

Los modelos de prueba viven en un `_ProbeBase` aislado: NO se registran en el
`Base.metadata` real, para no interferir con el test de drift `compare_metadata` (06).
"""

import uuid

import pytest
from app.infra.db.base import NAMING_CONVENTION, Base, TenantMixin, TimestampMixin
from sqlalchemy import CheckConstraint, Integer, MetaData, String, Uuid
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.schema import CreateIndex, CreateTable


class _ProbeBase(DeclarativeBase):
    """Base aislado con la MISMA naming_convention que el real (sin contaminarlo)."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class _Tenant(_ProbeBase):
    """Destino de la FK de TenantMixin (para resolver la referencia en el DDL)."""

    __tablename__ = "tenant"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)


class _Ticket(TenantMixin, TimestampMixin, _ProbeBase):
    """Modelo de prueba con pk, fk (tenant_id), uq (subject), ix (domain) y ck (csat)."""

    __tablename__ = "probe_ticket"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    subject: Mapped[str] = mapped_column(String, unique=True)
    domain: Mapped[str] = mapped_column(String, index=True)
    csat: Mapped[int] = mapped_column(Integer)
    __table_args__ = (CheckConstraint("csat > 0", name="csat_range"),)


class _Message(TenantMixin, _ProbeBase):
    """Segundo modelo con TenantMixin: su FK a tenant no debe colisionar con la de _Ticket."""

    __tablename__ = "probe_message"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)


_PG = postgresql.dialect()
_TICKET_DDL = str(CreateTable(_Ticket.__table__).compile(dialect=_PG))
_TICKET_IX = "\n".join(
    str(CreateIndex(ix).compile(dialect=_PG)) for ix in _Ticket.__table__.indexes
)
_ALL_DDL = _TICKET_DDL + "\n" + _TICKET_IX


def test_metadata_has_naming_convention() -> None:
    """La metadata del Base define plantillas para ix/uq/ck/fk/pk."""
    convention = Base.metadata.naming_convention
    assert {"ix", "uq", "ck", "fk", "pk"} <= set(convention)


def test_timestamp_mixin_columns() -> None:
    """TimestampMixin aporta created_at/updated_at timezone-aware, NOT NULL, con server_default."""
    cols = _Ticket.__table__.c
    for name in ("created_at", "updated_at"):
        assert cols[name].type.timezone is True
        assert cols[name].nullable is False
        assert cols[name].server_default is not None
    assert cols["updated_at"].onupdate is not None


def test_tenant_mixin_column() -> None:
    """TenantMixin aporta tenant_id UUID NOT NULL con FK a tenant.id."""
    col = _Ticket.__table__.c["tenant_id"]
    assert col.nullable is False
    assert isinstance(col.type, Uuid)
    foreign_keys = list(col.foreign_keys)
    assert len(foreign_keys) == 1
    assert foreign_keys[0].target_fullname == "tenant.id"


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("pk", "pk_probe_ticket"),
        ("fk", "fk_probe_ticket_tenant_id_tenant"),
        ("uq", "uq_probe_ticket_subject"),
        ("ix", "ix_probe_ticket_domain"),
        ("ck", "ck_probe_ticket_csat_range"),
    ],
)
def test_constraint_name_follows_convention(kind: str, expected: str) -> None:
    """Cada tipo de constraint sigue su plantilla determinista de la naming_convention."""
    assert expected in _ALL_DDL


def test_tenant_fk_names_do_not_collide() -> None:
    """Dos modelos con TenantMixin generan nombres de FK distintos (incluyen su tabla origen)."""
    message_ddl = str(CreateTable(_Message.__table__).compile(dialect=_PG))
    assert "fk_probe_ticket_tenant_id_tenant" in _TICKET_DDL
    assert "fk_probe_message_tenant_id_tenant" in message_ddl
