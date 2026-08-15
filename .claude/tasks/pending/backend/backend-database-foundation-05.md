---
id: backend-database-foundation-05
package: backend
plan: database-foundation
status: pending
priority: 1
depends_on: [backend-database-foundation-04]
estimate: 2h
actual:
created: 2026-08-15
updated: 2026-08-15
---

# Modelos ORM — KB (3 tablas globales, sin RLS) + columna vector

## Description

Los modelos del grupo **KB** (base de conocimiento global, compartida entre tenants → **sin RLS**,
`data-model.md` §2/§6, ADR-0006): `kb_document`, `kb_chunk`, `embedding`. La columna `embedding.vector` usa
el tipo `Vector` de `pgvector` con dimensión **literal `Vector(1536)`** (decisión del owner tras QA: evita el
acoplamiento import-time con `Settings`/`JWT_SECRET` y el falso negativo del drift-test; `settings.embedding_dim`
se usa **solo** en `/health/ready` (09) para asertar la dimensión viva; cambiar dim = editar el literal +
migración nueva, M3). Sin `tenant_id`. Spec: `data-model.md` §8 (dimensión), §9 (índice ANN **diferido**), ADR-0010.

## Spec

- 3 modelos: `kb_document`, `kb_chunk`, `embedding`; columnas de `data-model.md` §5; enums `kb_estado`,
  `kb_domain` (17 dominios).
- `embedding.vector`: `mapped_column(Vector(1536))` **literal** (pgvector). **Sin índice ANN** (diferido a RAG);
  sí las FKs a `kb_chunk`/`kb_document` (CASCADE) y sus unicidades: **`kb_document.uc_id` único** (base de la
  idempotencia de ingestión, FR-032) y **`embedding.chunk_id` único** (1:1 con `kb_chunk`); índice por
  `kb_document.domain` (filtro de retrieval, §9).
- **Ninguna** tabla KB lleva `tenant_id` (global, sin RLS).
- Registradas en `Base.metadata`.

## Fuera de alcance

- El índice ANN (ivfflat/hnsw) y el poblado de embeddings → plan RAG (13/14).
- La migración/extensión `vector` → 06 (la columna se congela `vector(1536)` allí).

## Scenarios (Gherkin)

<!-- SDD: modelos de infra → Gherkin LOCAL, "sin cambios de spec/CU". Verificación a nivel de metadata (unit). -->

```gherkin
Feature: modelos de la base de conocimiento (global)

  Scenario: las 3 tablas KB están registradas
    Given la metadata de los modelos
    When se listan las tablas del grupo KB
    Then están kb_document, kb_chunk y embedding

  Scenario: ninguna tabla KB lleva tenant_id (global, sin RLS)
    Given los modelos KB
    When se inspeccionan sus columnas
    Then ninguna tiene tenant_id

  Scenario: la columna vector es Vector(1536) literal
    Given el modelo embedding
    When se inspecciona embedding.vector
    Then su tipo es Vector con dimensión 1536 (literal, sin leer settings en import)

  Scenario: kb_domain tiene exactamente los 17 dominios
    Given el enum kb_domain
    When se inspecciona el conjunto de sus valores
    Then es exactamente los 17 dominios de data-model §3 (ni más ni menos)

  Scenario: kb_estado tiene exactamente draft y active
    Given el enum kb_estado
    When se inspecciona el conjunto de sus valores
    Then es exactamente {draft, active}

  Scenario: kb_document.uc_id es único (base de la idempotencia de ingestión)
    Given el modelo kb_document
    When se inspeccionan sus constraints
    Then uc_id tiene una constraint de unicidad

  Scenario: embedding es 1:1 con kb_chunk
    Given el modelo embedding
    When se inspecciona chunk_id
    Then es FK a kb_chunk con constraint única (relación 1:1)

  Scenario Outline: las FKs KB cascadean al borrar el padre
    Given la FK <fk>
    When se inspecciona su on_delete
    Then es CASCADE

    Examples:
      | fk                    |
      | kb_chunk.document_id  |
      | embedding.chunk_id    |
```

## Provides

Los 3 modelos ORM KB (con `embedding.vector`) en `app.infra.db.models`; completan las 18 entidades para la
migración inicial (06).

## Definition of Done

- [ ] Tests escritos ANTES de la implementación (Red → Green → Refactor).
- [ ] Cada escenario Gherkin tiene al menos un test (3 tablas KB, sin tenant_id, Vector(dim), kb_domain).
- [ ] Todos los tests en verde (`make test`).
- [ ] `Provides` disponible; el dominio no importa `app.infra`.
- [ ] `ruff check` (+`S`) + `ruff format --check` + `mypy` strict OK.
- [ ] Gate de mutation: modelos **declarativos** → mutation N/A documentado (M4 del plan).
- [ ] Gate `/sdd-lint` sin ERROR (SDD: sin cambios de spec/CU — modelos de infra).
- [ ] Gate de `fact-checker`.
- [ ] Documentación: docstrings de los modelos/enums; session log.
