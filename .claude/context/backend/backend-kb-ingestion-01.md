# Session log — `backend-kb-ingestion-01` — Puerto `EmbeddingModel` + adaptador OpenAI real + `Settings`

> Append-only. Registro canónico de la tarea (task-lifecycle §Cerrar una tarea).

## 2026-08-21 — Arranque

- **Plan** `backend/kb-ingestion` movido `pending → active`; rama `plan/backend/kb-ingestion` creada
  desde `main` (repo sin rama `dev`; `main` sincronizada con `origin/main` tras el merge de
  `plan/frontend/multi-tenant-login`... aún pendiente de merge, PR #7 abierta — esta rama parte de
  `main` en su estado actual, sin ese merge).
- **Tarea 01** movida `pending → active`. `depends_on: []` → sin bloqueos. Única tarea activa del plan.
- Plan gestado con el flujo completo: plan mode (con un subagente Plan de investigación) →
  `grilling` (11 decisiones) → `design-review` (3 hallazgos, incl. una contradicción real corregida) →
  7 tareas descompuestas → `scenario-coverage` (11 decisiones más, incl. un gap de **diseño** real:
  `ChunkWrite.vector=None` para ediciones parciales). Detalle completo en
  `.claude/plans/active/backend/kb-ingestion.md` (Registro de cambios).
- **Precondición del `HOW-TO-START-A-TASK.md` verificada como obsoleta**: dice "el backend aún no
  ejecuta" (deps no instaladas) — falso hoy: `.venv` con deps reales, Docker con Postgres+pgvector ya
  arriba, `pytest` corrido en esta sesión → **749 tests, todos en verde**. No se corrige el documento en
  esta tarea (fuera de su alcance), solo se anota aquí para que la sesión no pierda tiempo re-verificando
  algo ya resuelto.

## 2026-08-21 — Cierre

- **TDD**: tests escritos antes de la implementación (`tests/test_openai_adapter.py` nuevo +
  4 casos en `tests/test_config.py`); rojo confirmado antes de escribir `EmbeddingModel`/
  `OpenAIEmbeddingModel`/los 4 campos de `Settings`, verde después.
- **Implementado**: `app/domain/ports/embeddings.py` (Protocol `EmbeddingModel`, solo
  `embed_documents`); `app/core/config.py` (+`llm_provider`/`openai_api_key`/`chat_model`/
  `embedding_model`); `app/infra/llm/openai_adapter.py` (`OpenAIEmbeddingModel` real + factory
  `get_embedding_model`, fail-fast de dimensión antes de cualquier llamada de red, instanciación
  perezosa del cliente OpenAI). `OpenAIChatModel` queda GUIÓN, anotado en el docstring del módulo.
- **sdd-lint**: 0 ERROR, 5 AVISO sobre `spec.md`/`CU-BE-07`/`rag-ingestion.md`/ADR-0010. Uno
  corregido (el Then no-determinista "espera o falla claro" del escenario de concurrencia —
  reescrito a "falla claro de inmediato, sin esperar", fiel a la decisión real de `-02`:
  `pg_try_advisory_lock` no bloqueante). Los otros 4 se reconocen sin corregir (elaboración
  legítima del CU/spec más allá del nivel FR, no defecto):
  1. FR-034 no cubre literalmente la reconciliación a nivel de chunk de un documento vivo (3b).
  2. Escenario 3c (fallo real a mitad de batch) no traza a ningún FR/NFR explícito.
  3. Escenario 4a (ejecuciones concurrentes) no traza a ningún FR/NFR explícito.
  4. `rag-ingestion.md` §7 no menciona explícitamente 3b/4b (no los contradice).
- **fact-checker** (subagente independiente, agentId `a6d0d64020ab09221`): 8/8 afirmaciones
  VERIFICADO, 0 INCORRECTO, 0 NO VERIFICABLE. Confirmó, re-ejecutando él mismo los comandos:
  `pytest tests/test_openai_adapter.py tests/test_config.py` → 50 passed; suite completa → **771
  passed**; `ruff check` limpio; `mypy --strict` limpio (3 ficheros); `cosmic-ray` re-ejecutado de
  cero → `cr-rate --fail-over 20` → **0.00% supervivencia** (36/36 mutantes KILLED), exit 0.
- **DoD**: todos los checkboxes cumplidos (ver abajo). Sin pendientes.
- Excluido de este commit: `backend/docs/domain-services-explicado.md` (cambio no relacionado,
  de una sesión anterior, sigue sin commitear).
