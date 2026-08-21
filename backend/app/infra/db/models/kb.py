"""app.infra.db.models.kb — modelos ORM de la base de conocimiento (data-model.md §4.3).

Grupo **global** (KB compartida entre tenants): SIN `tenant_id`, SIN RLS (§2/§6, ADR-0006). La columna
`embedding.vector` es `Vector(1536)` **literal** (pgvector): la dimensión se congela en el modelo y en la
migración (06) — usar `settings.embedding_dim` en import acoplaría a `Settings`/`JWT_SECRET` y daría un
falso negativo en el drift-test. `settings.embedding_dim` solo lo lee `/health/ready` (09). Índice ANN
(ivfflat/hnsw) diferido al plan RAG (13/14). Sin efectos en import.
"""

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.db.base import Base, TimestampMixin
from app.infra.db.models.enums import KbDomain, KbEstado, pg_enum

EMBEDDING_DIM_LITERAL = 1536
"""Dimensión del vector, LITERAL (no `settings.embedding_dim`): misma revisión = mismo schema (M3)."""


class KBDocument(TimestampMixin, Base):
    """Un UC de la KB. Upsert idempotente por `uc_id` (04). `source_url` derivado de la ruta del repo."""

    __tablename__ = "kb_document"
    __table_args__ = (
        UniqueConstraint("uc_id"),
        Index("ix_kb_document_domain", "domain"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    uc_id: Mapped[str] = mapped_column(String)
    domain: Mapped[KbDomain] = mapped_column(pg_enum(KbDomain, "kb_domain"))
    package: Mapped[str] = mapped_column(String)
    estado: Mapped[KbEstado] = mapped_column(pg_enum(KbEstado, "kb_estado"))
    title: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(String)
    traza: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    updated: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KBChunk(Base):
    """Trozo de un documento (chunking H2 tolerante, 04). `section_type` string libre (no enum rígido)."""

    __tablename__ = "kb_chunk"
    __table_args__ = (
        Index("ix_kb_chunk_document", "document_id"),
        UniqueConstraint("document_id", "ordinal"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("kb_document.id", ondelete="CASCADE"))
    section_type: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer)
    ordinal: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Embedding(Base):
    """Vector de un chunk (1:1 con `kb_chunk`). `model` guarda qué modelo lo generó (detectar mezclas)."""

    __tablename__ = "embedding"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("kb_chunk.id", ondelete="CASCADE"), unique=True
    )
    model: Mapped[str] = mapped_column(String)
    vector: Mapped[Any] = mapped_column(Vector(EMBEDDING_DIM_LITERAL))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
