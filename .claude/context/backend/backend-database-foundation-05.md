# Session log — backend-database-foundation-05

Tarea: 3 modelos ORM de la KB (global, sin RLS) + `embedding.vector = Vector(1536)` literal.
Nivel: **unit** (metadata). Mutation: **N/A** (declarativo). Fichero: `app/infra/db/models/kb.py`.

## Resumen

- `kb.py`: `KBDocument` (uc_id único, domain KbDomain con índice de retrieval, estado KbEstado,
  traza JSONB, `updated` timestamptz), `KBChunk` (document_id FK CASCADE, section_type libre, ordinal),
  `Embedding` (chunk_id FK CASCADE **único** 1:1, `vector` = `Vector(1536)`).
- Constante `EMBEDDING_DIM_LITERAL = 1536` (literal, no `settings.embedding_dim`).
- Con esto, las **18 entidades** de `data-model.md` están modeladas y registradas en `Base.metadata`.

## Decisiones técnicas + porqué

- **`Vector(1536)` literal** (decisión owner tras QA): usar `settings.embedding_dim` en import acoplaría
  el import de modelos a `Settings` (que exige `JWT_SECRET`) y daría un **falso negativo** en el drift-test
  (06) — la dimensión viva vs. la del modelo siempre "coincidiría" al leer la misma config. Con literal, el
  drift-test detecta un cambio de dimensión no migrado. `settings.embedding_dim` solo lo usa `/health/ready`.
- **Sin índice ANN** (ivfflat/hnsw): diferido al plan RAG (13/14); aquí solo la columna `Vector(N)` + FKs.
- **Sin `tenant_id`**: KB es global read-only compartida (ADR-0006); no hereda `TenantMixin`.
- **`vector: Mapped[Any]`**: el tipo pgvector `Vector` no tiene un tipo Python nativo trivial para el
  mapeo por anotación; `Any` + tipo explícito `Vector(1536)` es lo idiomático (acepta list[float]/np.array).

## Tests corridos + resultado

- TDD: 10 tests RED (ImportError) → GREEN. `tests/test_models_kb.py`: 3 tablas registradas, sin tenant_id,
  Vector(1536) literal (dim==1536), kb_domain con los 17 exactos, kb_estado {draft,active}, uc_id único,
  embedding 1:1 (chunk_id único + FK), cascadas CASCADE, índice de domain.
- Suite completa `pytest -q` verde (153 tests). `ruff check` OK (tras `--fix`) · `ruff format --check` OK ·
  `mypy app` strict Success (83 files).
- Mutation: **N/A** (declarativo, M4). `/sdd-lint`: sin cambios SDD (infra) → PASA.
- `fact-checker` (sonnet): **10/10 VERIFICADO, 0 INCORRECTO**. Confirmó 18 tablas registradas, `Vector(1536)`
  con `.dim==1536`, `kb.py` sin import de `Settings`, 17 dominios. Señaló (contexto, no error) que el literal
  1536 se desvía de la lectura estricta de §8 pero es decisión trazada del owner. Gate limpio.

## Docs actualizadas

- Docstrings de módulo/clase en `kb.py` (incl. el porqué del literal 1536 y del índice ANN diferido);
  `__init__.py` re-exporta los 3 modelos KB.
- Session log (este fichero).
