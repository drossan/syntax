---
id: backend-skeleton-foundation-13
package: backend
plan: skeleton-foundation
status: done
priority: 3
depends_on: [backend-skeleton-foundation-04, backend-skeleton-foundation-08, backend-skeleton-foundation-09]
estimate: 3h
actual: 0.5h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# Skeleton pipeline de ingestión de la KB

## Description

Esqueleto de `app/ingestion/`: el pipeline que lleva los `domains/*/uc/*.md` a pgvector según la spec
04. Loader → parser (frontmatter + Trazabilidad) → chunker H2 tolerante → embedder → upsert idempotente,
más una CLI. Solo esqueleto + guión.

## Spec

- `app/ingestion/loader.py` — recorre `domains/<dominio>/uc/*.md` + `index.md`; ruta configurable; fallback documentado.
- `app/ingestion/parser.py` — frontmatter `title/domain/package/uc`; bloque `::: info Trazabilidad`
  (`Estado`/`Traza`); `Relacionado:`; glosario de `index.md`.
- `app/ingestion/chunker.py` — **por sección H2 tolerante** (H2 ausentes/renombrados; no partir tablas);
  metadatos por chunk (`uc_id/domain/package/estado/section_type`).
- `app/ingestion/embedder.py` — usa el puerto embeddings (09); dimensión de config.
- `app/ingestion/pipeline.py` + `cli.py` — orquesta y hace **upsert idempotente por `uc_id`** (re-embeber
  solo si cambió el contenido); `make ingest` lo invoca.

## Refuerzos (scenario-coverage)

- Manejo de **frontmatter malformado / `uc_id` faltante o duplicado** (skip+log / fail, no silencioso).
- **Reconciliación de docs retirados** (tombstone/borrado de chunks huérfanos), no solo-upsert — espejo de 04.

## Fuera de alcance

- Recrear la fuente (lo hace el owner). BM25/híbrido (diferido). Implementar la lógica real (solo esqueleto + guión).

## Scenarios (Gherkin)

<!-- Doc-only. -->
**Verificación (doc-only):**
- El parser guión corresponde al formato real (frontmatter `title/domain/package/uc` + Trazabilidad + glosario).
- El chunker es tolerante a H2 y no parte tablas; cada chunk lleva las 5 facetas de metadatos.
- El upsert es idempotente por `uc_id`; la dimensión viene de config; `make ingest` está cableado.

## Provides

- `app/ingestion/*` + `make ingest`. Puebla `KBDocument/KBChunk/Embedding` (03) que consume el retriever (14) y los seeds (17).

## Definition of Done

- [x] Pipeline (loader/parser/chunker/embedder/pipeline/cli + `__main__`) creado con guión, fiel a la spec 04. `compileall` OK.
- [x] Chunker tolerante, metadatos de 5 facetas, upsert idempotente por `uc_id` + reconciliación, dimensión de config.
- [x] `Provides` disponible para las dependientes (puebla KBDocument/Chunk/Embedding para 14/17; `make ingest` cableado).
- [x] Gate de `fact-checker` superado (sonnet): 7/7 VERIFICADO.
- [x] Histórico en `.claude/context/backend/backend-skeleton-foundation-13.md`.
