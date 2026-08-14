# 0010. RAG: pgvector, dimensión desde config, chunking H2 tolerante y `estado` con peso

- **Estado**: accepted
- **Fecha**: 2026-08-11
- **Decisores**: Owner; `grilling` backend (rama 6) + `design-review` (H2 tolerante, peso `estado` explícito).

## Contexto y planteamiento del problema

La KB real son **268 UC** en **17 dominios** (Markdown con frontmatter + bloque Trazabilidad). El **81%**
está en `estado: draft`. Hay que ingerirla en un store vectorial y recuperarla con calidad, sin asumir una
estructura de secciones rígida ni vaciar el retrieval penalizando `draft` a ciegas.

## Decision drivers

- Store vectorial junto al Postgres de negocio (una sola base).
- La estructura H2 de los UC **no es uniforme** (secciones ausentes/renombradas/extra).
- `draft` es el 81% del corpus: no puede ser un filtro duro por defecto.
- Cambiar el modelo de embeddings no debe requerir tocar el schema literal.

## Opciones consideradas

- **Opción 1** — **pgvector** en el mismo Postgres; `vector(N)` con **N desde config** (default 1536);
  **chunking H2 tolerante**; `estado` = **señal de re-ranking con peso** configurable (no filtro duro).
- **Opción 2** — Store vectorial externo (Chroma) + chunking por estructura H2 **fija**.
- **Opción 3** — Filtrar el retrieval a solo `estado: active` (documentación "estable").

## Resultado de la decisión

Elegida: **Opción 1**. Embeddings en **pgvector** (búsqueda coseno top-k); `embedding.vector(N)` con
`N=EMBEDDING_DIM` (default **1536**, OpenAI `text-embedding-3-small`) — cambiar N obliga a **re-embeber todo
+ reconstruir índice** (no en caliente). **Chunking H2 tolerante**: parte por secciones H2 sin asumir
estructura fija (tolera H2 ausentes/renombrados/extra; no parte tablas ni bloques de código; glosario del
`index.md`). **`estado`** es una señal de **re-ranking con peso** (`RAG_ESTADO_WEIGHT`, active recibe un
boost leve, draft no se hunde), **no** un filtro duro; filtrar por `estado` es **opt-in** por consulta.
Upsert **idempotente por `uc_id`**; `uc_id` duplicado → fail del batch; doc retirado → reconcilia (tombstone).

### Confirmación

`rag-ingestion.md` (fuente verificada, chunking, peso `estado` §4) + `data-model.md` §8; `app/ingestion/`
(loader/parser/chunker/embedder/cli) y `app/rag/` (retriever/reranker/confidence/citations), guión doc-only.

## Consecuencias

- **Buenas**: una sola base (negocio + vectores); robusto ante KB irregular; `draft` no vacía el retrieval.
- **Malas / coste**: cambiar dimensión = re-ingesta completa; BM25 híbrido diferido (solo semántico Fase 1).

## Pros y contras de las opciones

- **Opción 1**: 👍 una base, tolerante, `draft` aprovechado · 👎 re-embed caro al cambiar N.
- **Opción 2**: 👍 store especializado · 👎 otra infra; chunking fijo rompe con la KB real irregular.
- **Opción 3**: 👍 "solo doc estable" · 👎 descarta el 81% del corpus → retrieval vacío.
