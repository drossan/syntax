---
id: backend-skeleton-foundation-14
package: backend
plan: skeleton-foundation
status: done
priority: 3
depends_on: [backend-skeleton-foundation-04, backend-skeleton-foundation-08, backend-skeleton-foundation-09]
estimate: 3h
actual: 0.4h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# Skeleton RAG retriever

## Description

Esqueleto de `app/rag/`: recuperación sobre pgvector con filtros, rerank, **confianza híbrida** y citas,
según spec 04/05. Solo esqueleto + guión.

## Spec

- `app/rag/retriever.py` — similitud pgvector (coseno) top-k con **filtros** (`domain/package/estado`);
  el filtro `domain` lo fija el clasificador (05).
- `app/rag/reranker.py` — guión de rerank opcional (p.ej. por `estado` con **peso explícito**, cross-encoder futuro).
- `app/rag/confidence.py` — **confianza híbrida**: combina similitud + resultado del nodo `grade` (05).
- `app/rag/citations.py` — construye citas (`uc_id`, `title`, `section_type`) para la respuesta y el frontend.
- Puerto `vector_store` en `domain/ports` (implementado por infra/db o infra/vector).

## Fuera de alcance

- El nodo `grade` LLM vive en el grafo (15); aquí solo el contrato de confianza. BM25 híbrido (diferido). Implementar lógica.

## Scenarios (Gherkin)

<!-- Doc-only. -->
**Verificación (doc-only):**
- El retriever aplica filtros domain/package/estado y expone top-k; el peso de `estado` es explícito en el reranker.
- `confidence.py` define cómo se combinan similitud + grade (coherente con 05).
- Las citas incluyen `uc_id/title/section_type`.

## Provides

- `app/rag/*` + puerto `vector_store`. 15 (grafo) usa retriever+confidence+citations; 12 (routers) expone las citas.

## Definition of Done

- [x] Retriever/reranker/confidence/citations creados con guión según 04/05; puerto vector ya en `domain/ports/vector.py` (10). `compileall` OK.
- [x] Filtros domain/package/estado; peso de `estado` explícito (desempate, no veto); confianza híbrida (similitud+grade, umbral config) definida.
- [x] `Provides` disponible para las dependientes (15 usa retriever+confidence+citations; 12 expone citas).
- [x] Gate de `fact-checker` superado (sonnet): 7/7 VERIFICADO.
- [x] Histórico en `.claude/context/backend/backend-skeleton-foundation-14.md`.
