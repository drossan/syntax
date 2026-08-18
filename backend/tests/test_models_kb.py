"""Tests de los modelos ORM de la KB (tarea 05) — nivel metadata, unit.

Grupo **global** (compartido entre tenants): SIN `tenant_id`, SIN RLS (data-model §2/§6, ADR-0006).
`embedding.vector` = `Vector(1536)` literal (sin leer settings en import). Índice ANN diferido a RAG.
"""

import pytest
from app.infra.db.base import Base, TenantMixin
from app.infra.db.models import Embedding, KBChunk, KBDocument
from app.infra.db.models.enums import KbDomain, KbEstado
from pgvector.sqlalchemy import Vector
from sqlalchemy import UniqueConstraint

_KB_TABLES = {"kb_document", "kb_chunk", "embedding"}
_KB_MODELS = [KBDocument, KBChunk, Embedding]

_KB_DOMAINS_17 = {
    "analytics-logs-and-activity",
    "authoring-and-editor",
    "content-modeling-and-schemas",
    "data-collection-and-store",
    "data-packs-and-distributors",
    "forms-and-submissions",
    "i18n-and-translations",
    "identity-and-permissions",
    "integrations-crm-and-feeds",
    "media-and-dam",
    "navigation-and-menus",
    "platform-and-devex",
    "render-infra-and-config",
    "rendering-and-publishing",
    "search-ai-and-llms",
    "seo-sitemaps-and-edge",
    "sites-domains-instances",
}


def _unique_column_sets(model: type) -> list[frozenset[str]]:
    return [
        frozenset(col.name for col in constraint.columns)
        for constraint in model.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    ]


def test_three_kb_tables_registered() -> None:
    """Las 3 tablas KB están registradas en Base.metadata."""
    assert set(Base.metadata.tables) >= _KB_TABLES


def test_no_kb_table_has_tenant_id() -> None:
    """Ninguna tabla KB lleva tenant_id (global, sin RLS)."""
    for model in _KB_MODELS:
        assert "tenant_id" not in model.__table__.c, model.__name__
        assert not issubclass(model, TenantMixin), model.__name__


def test_embedding_vector_is_literal_1536() -> None:
    """embedding.vector es Vector(1536) literal (dimensión fija, sin leer settings en import)."""
    column = Embedding.__table__.c["vector"]
    assert isinstance(column.type, Vector)
    assert column.type.dim == 1536


def test_kb_domain_has_exactly_17_domains() -> None:
    """kb_domain tiene EXACTAMENTE los 17 dominios de data-model §3."""
    values = {m.value for m in KbDomain}
    assert values == _KB_DOMAINS_17
    assert len(values) == 17


def test_kb_estado_has_exact_value_set() -> None:
    """kb_estado tiene exactamente {draft, active}."""
    assert {m.value for m in KbEstado} == {"draft", "active"}


def test_kb_document_uc_id_is_unique() -> None:
    """kb_document.uc_id es único (base de la idempotencia de ingestión, FR-032)."""
    assert frozenset({"uc_id"}) in _unique_column_sets(KBDocument)


def test_embedding_is_one_to_one_with_chunk() -> None:
    """embedding.chunk_id es FK a kb_chunk con unicidad (relación 1:1)."""
    chunk_fk = next(iter(Embedding.__table__.c["chunk_id"].foreign_keys))
    assert chunk_fk.target_fullname == "kb_chunk.id"
    assert frozenset({"chunk_id"}) in _unique_column_sets(Embedding)


@pytest.mark.parametrize(
    ("model", "column"),
    [
        (KBChunk, "document_id"),
        (Embedding, "chunk_id"),
    ],
)
def test_kb_fks_cascade_on_parent_delete(model: type, column: str) -> None:
    """Las FKs de la KB cascadean al borrar el padre (re-ingesta limpia chunks y vectores, §7)."""
    fk = next(iter(model.__table__.c[column].foreign_keys))
    assert fk.ondelete == "CASCADE"


def test_kb_document_domain_uses_kb_domain_enum() -> None:
    """kb_document.domain usa el enum kb_domain (17 dominios) con un índice de retrieval (§9)."""
    domain_col = KBDocument.__table__.c["domain"]
    assert set(domain_col.type.enums) == _KB_DOMAINS_17
    indexed_column_sets = [
        tuple(c.name for c in idx.columns) for idx in KBDocument.__table__.indexes
    ]
    assert ("domain",) in indexed_column_sets
