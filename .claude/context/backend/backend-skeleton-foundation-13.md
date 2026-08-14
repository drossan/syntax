# Session log — backend-skeleton-foundation-13 (Skeleton pipeline de ingestión)

## 2026-08-13 — Arranque

Movida `pending → active`. Deps 04/08/09 `done`. Doc-only skeleton.

**Aviso de alcance (una frase):** el `Makefile` cablea `make ingest` → `python -m app.ingestion`, así que
además del `cli.py` que lista la tarea creo `app/ingestion/__main__.py` (entry-point real del comando).

Ficheros: `app/ingestion/{loader,parser,chunker,embedder,pipeline,cli,__main__}.py`. Fieles a la spec 04
(verificada contra la KB real en tareas 03/04).

## 2026-08-13 — Cierre

**Resumen:** 7 ficheros guión en `app/ingestion/`: `loader` (recorre domains/uc + index/glosario, ruta
config, fallback llms-full.txt), `parser` (frontmatter sin url→source_url derivado; Trazabilidad;
malformado→skip+log, dup→fail), `chunker` (H2 tolerante, no partir tablas, 5 facetas), `embedder`
(puerto embeddings, dim de config, re-embed solo si cambió), `pipeline` (orquesta + upsert idempotente
por uc_id + reconciliación huérfanos), `cli` + `__main__` (entry-point `python -m app.ingestion` de
`make ingest`).

**Verificación:** `compileall` exit 0; grep código ejecutable → sin coincidencias. Makefile `ingest` →
`$(PY) -m app.ingestion` confirmado.

**Gate `fact-checker` (sonnet):** **7/7 VERIFICADO** (K4 con matiz: Makefile usa `$(PY)`, resuelve a
python del venv).

**Docs:** 7 ficheros nuevos. Plan: `[x]` 13 + Registro. **Tiempo real:** ~0.5 h.

**Follow-ups:** 14 (retriever) consume lo que puebla; 17 (seeds) puede invocar ingesta de muestra.
