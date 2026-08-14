# Referencia · RAG + ingestión

**Fuente canónica:** `.claude/specs/backend/rag-ingestion.md`. Implementación: `app/ingestion/` (pipeline)
y `app/rag/` (retriever).

## Fuente (KB real, verificada)

`domains/<dominio>/uc/UC-*.md` (**268** casos de uso, **17** dominios) + `index.md` por dominio (**17**,
con `## Glosario`). Total 286 `.md`. Frontmatter `title/domain/package/uc` (sin `url` → `source_url`
derivado). Fallback: `.vitepress/dist/llms-full.txt`.

## Pipeline de ingestión

```
loader → parser → chunker → embedder → upsert (idempotente por uc_id)
```

- **Parser**: frontmatter + bloque `::: info Trazabilidad` (`Estado`/`Traza`); precedencia de `package`:
  gana el frontmatter. Frontmatter malformado/`uc_id` ausente → skip+log; `uc_id` duplicado → fail.
- **Chunker H2 tolerante**: parte por secciones H2 **sin asumir estructura fija** (H2 ausentes/
  renombrados/sueltos; no partir tablas). Metadatos por chunk (5 facetas): `uc_id/domain/package/estado/
  section_type`.
- **Reconciliación**: docs retirados en origen → borrado/tombstone de chunks huérfanos (no solo-upsert).

## Retrieval

- Similitud **pgvector coseno** top-k con **filtros** (`domain` lo fija el clasificador, `package`,
  `estado`).
- **Peso de `estado` explícito** (`RAG_ESTADO_WEIGHT`): el ~81% del corpus es `draft`; se re-rankea como
  **desempate**, no se penaliza a ciegas ni se filtra por defecto.
- **Confianza híbrida**: similitud + `grade` del LLM → el agente decide auto vs escalado; contexto
  insuficiente → nota al humano (no inventar).
- **Citas**: `uc_id`, `title`, `section_type` (→ `AgentRun.sources` y el frontend).
