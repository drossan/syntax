---
id: backend-skeleton-foundation-04
package: backend
plan: skeleton-foundation
status: done
priority: 1
depends_on: []
estimate: 3h
actual: 1h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# Spec RAG + ingestión de la KB

## Description

Escribir `.claude/specs/backend/rag-ingestion.md`: cómo se ingiere la documentación de Syntax
(`domains/*/uc/*.md` + `index.md`), se trocea, se categoriza, se embebe en pgvector y se recupera con
confianza híbrida. Diseñada contra el **formato real verificado** de la fuente restaurada. Fuente para el
pipeline de ingestión (13) y el retriever (14).

## Spec

- **Fuente**: `~/Documents/Desarrollo/syntax/docs-site/domains/<dominio>/uc/UC-*.md` (268) + `index.md`
  por dominio (17, con `## Glosario`). Fallback documentado: `.vitepress/dist` / `llms-full.txt`.
- **Parsing**: frontmatter YAML **`title/domain/package/uc`** (NO `url`); bloque `::: info Trazabilidad`
  → `Estado` (`draft`/`active`) + `Traza`; línea `Relacionado:` → grafo de relacionados.
- **Chunking por sección H2 TOLERANTE**: H2 casi-uniformes (`Comportamiento`/`Conceptos`/`Reglas e
  invariantes`/`Detalles observados en QA`/`Fidelidad`) pero variables → no asumir estructura fija;
  tolerar H2 ausentes/renombrados; no partir tablas. Del `index.md`, ingerir `## Glosario`
  (`section_type=glosario`); `## Casos de uso`/`## Todos los dominios` = navegación, no se embeben.
- **Categorización (metadatos por chunk)**: `uc_id`, `domain` (17), `package` (5), `estado`,
  `section_type`. `estado` como señal de retrieval con **peso explícito** (draft=218/active=50: no
  penalizar draft a ciegas; el 81% es draft).
- **Embeddings**: puerto abstraído; default OpenAI `text-embedding-3-small` → `vector(1536)`
  (dimensión desde config). Upsert **idempotente por `uc_id`**; re-embeber solo al cambiar el contenido.
- **Retrieval**: similitud pgvector (coseno) top-k con **filtros** (domain/package/estado); confianza
  **híbrida** (similitud + grade LLM, ver agent-graph 05); citas con `uc_id`/`title`/sección.

## Refuerzos (scenario-coverage)

- **Frontmatter malformado / `uc_id` faltante o duplicado** → comportamiento definido (skip+log / fail),
  nunca silencioso (`uc_id` es la clave de upsert; `domain` es filtro de retrieval).
- **Doc retirado en origen** → reconciliación (borrado/tombstone de `KBChunk`/`Embedding` huérfanos), no
  solo-upsert.
- **Precedencia** `package` frontmatter vs bloque Trazabilidad si difieren (frontmatter gana; log si discrepan).
- Conteo real de la señal `estado` ≈ **218 draft / 51 active** (mayoría draft; no penalizar a ciegas).

## Fuera de alcance

- Implementar loaders/embedders (eso es 13/14); aquí solo la spec.
- Búsqueda híbrida BM25 (diferida); recrear la fuente `domains/*/uc` (lo hace el owner).

## Scenarios (Gherkin)

<!-- Doc-only. -->
**Verificación (doc-only):**
- El parsing descrito corresponde al formato real (frontmatter `title/domain/package/uc` + Trazabilidad), no a `url`.
- El chunker se especifica **tolerante** a H2 ausentes/renombrados y no parte tablas.
- La categorización cubre las 5 facetas y el peso de `estado` es explícito (no "draft = menos" a ciegas).
- La dimensión del embedding es parametrizable y el upsert es idempotente por `uc_id`.

## Provides

- `.claude/specs/backend/rag-ingestion.md`: contrato de ingestión (parsing/chunking/categorización/upsert)
  y de retrieval (filtros/confianza/citas). 13 implementa la ingestión; 14 el retriever; 05 consume la confianza.

## Definition of Done

- [x] Spec creada y fiel al formato real de la fuente (verificado contra la KB: frontmatter, Trazabilidad, index.md/Glosario, H2, packages).
- [x] Chunker tolerante, categorización de 5 facetas, peso de `estado` explícito, dimensión parametrizable, upsert idempotente.
- [x] Coherente con 03 (tablas KB) y 05 (confianza híbrida). <!-- 05 aún no existe; se fija aquí el contrato de retrieval/confianza que 05 consumirá. -->
- [x] `Provides` disponible para las dependientes.
- [x] Gate de `fact-checker` superado (sonnet): 9/10 VERIFICADO + 1 INCORRECTO (conteos H2) corregido y re-cuadrado con el conteo del verificador.
- [x] Histórico en `.claude/context/backend/backend-skeleton-foundation-04.md`.
