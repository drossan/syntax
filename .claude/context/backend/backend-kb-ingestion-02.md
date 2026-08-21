# Session log — `backend-kb-ingestion-02` — Puerto `KBIndexWriter` + adaptador pgvector real

> Append-only. Registro canónico de la tarea (task-lifecycle §Cerrar una tarea).

## 2026-08-21 — Implementación y cierre

- **TDD**: `tests/test_vector_adapter.py` (nuevo, 26 tests) escrito antes del adaptador; rojo
  confirmado (import de `SqlAlchemyKBIndexWriter` fallaba) antes de implementar
  `app/infra/vector/__init__.py`, verde después.
- **Implementado**: `app/domain/ports/vector.py` (`KBIndexWriter` Protocol +
  `KBDocumentDraft`/`ChunkWrite`/`UpsertReport`/`Hit`, `@dataclass(frozen=True)` — mismo patrón que
  `PageResult` en `domain/ports/repositories.py`, no `pydantic.BaseModel`); `SqlAlchemyKBIndexWriter`
  (`app/infra/vector/__init__.py`); `UniqueConstraint("document_id", "ordinal")` en `KBChunk`
  (`app/infra/db/models/kb.py`) + migración `alembic/versions/0004_kb_chunk_unique_ordinal.py`.
- **Decisión de implementación no cubierta explícitamente por la tarea**: `ChunkWrite` necesitaba un
  campo `model: str` para poder rellenar `embedding.model` (NOT NULL) al crear una fila de embedding
  nueva — la tarea no lo mencionaba en su lista de campos. Añadido como campo rutinario (se ignora
  cuando `vector=None`); no es una decisión arquitectónica, documentado en el docstring de `ChunkWrite`.
- **Bug real encontrado por TDD (no por mutation)**: primer intento de `upsert_document` intercalaba
  `session.add(KBChunkModel)` y `session.add(Embedding)` por chunk — sin `relationship()` entre esos
  dos modelos (solo FK de columna), el unit-of-work de SQLAlchemy no conoce la dependencia de flush
  entre objetos recién añadidos de clases distintas y puede intentar el INSERT de `embedding` antes que
  el de su `kb_chunk`, violando la FK (`ForeignKeyViolationError` real, visto en rojo). Corregido a dos
  pasadas: fase 1 persiste todos los `kb_chunk` (flush), fase 2 crea/actualiza sus `embedding`.
  Documentado como comentario en el código (no es obvio sin conocer esta limitación de SQLAlchemy).
- **Mutation testing (cosmic-ray)**: primera pasada 17.60% supervivencia (22 survivors) — casi todos
  mutantes `==`→`<=`/`>=`/`is not` en filtros `.where(Model.columna == valor)` que mis tests originales
  no distinguían (con una sola fila en la tabla, cualquier operador de comparación da el mismo
  resultado). Añadidos 6 tests con el patrón "documento bajo/objetivo/alto" (`id`/`uc_id` deterministas,
  mismo criterio que `test_repositories_ticket.py`'s `low/target/high` de UUIDs) + 1 test para el
  `continue`→`break` de la fase de embeddings + 4 tests de fallo de infraestructura (broken engine) para
  los métodos que no lo tenían todavía → segunda pasada: **2.40% supervivencia (3/125)**, los 3
  documentados como mutantes equivalentes:
  1. 2× `NumberReplacer` sobre `_INGESTION_LOCK_KEY` — constante arbitraria del advisory lock; cualquier
     valor entero es funcionalmente equivalente, ningún test puede distinguirlos.
  2. 1× `ReplaceBinaryOperator_Mul_Div` sobre el `*` (separador keyword-only) de la firma de `search` —
     artefacto de la herramienta sobre sintaxis no-operador; `search` lanza `NotImplementedError`
     incondicionalmente sin usar ningún parámetro, código inalcanzable por diseño (tarea 14, fuera de
     este plan).
- **sdd-lint**: N/A para esta tarea — no toca `spec.md`/casos-de-uso/ADR (solo `data-model.md`, que no
  es uno de los artefactos que audita `sdd-lint`). El gate ya corrió sobre `CU-BE-07` en el cierre de
  la tarea `-01`.
- **fact-checker** (subagente independiente, agentId `a5dd84bb2f6a23745`): 9/9 afirmaciones VERIFICADO,
  0 INCORRECTO, 0 NO VERIFICABLE. Confirmó, re-ejecutando él mismo: `pytest
  tests/test_vector_adapter.py tests/test_migration.py` → 45 passed; suite completa → **797 passed**;
  `ruff check` limpio; `mypy --strict` limpio (3 ficheros de producción); `cosmic-ray` re-ejecutado de
  cero → 2.40% supervivencia, mismos 3 survivors exactos.
- **DoD**: todos los checkboxes cumplidos (ver tarea). Sin pendientes.
- Excluido de este commit: `backend/docs/domain-services-explicado.md` (cambio no relacionado, de una
  sesión anterior, sigue sin commitear).
