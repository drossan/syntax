---
id: backend-kb-ingestion-06
package: backend
plan: kb-ingestion
status: completed
priority: 1
depends_on: [backend-kb-ingestion-02, backend-kb-ingestion-05]
estimate: 4h
actual: 6h
created: 2026-08-21
updated: 2026-08-21
---

# Pipeline (orquestación + reconciliación)

## Description

`app/ingestion/pipeline.py` es GUIÓN puro. Orquesta loader (`-03`) → parser (`-03`) → chunker (`-04`) →
diff contra `KBIndexWriter` (`-02`) → embed solo lo cambiado (`-05`) → `upsert_document` → reconciliación
de huérfanos. Es la tarea de mayor superficie del plan: toda la lógica de negocio de CU-BE-07 vive aquí
(los módulos anteriores son piezas puras/de infraestructura sin esta orquestación).

**Reglas de `grilling`/`design-review`/`scenario-coverage` que esta tarea debe cumplir**:
- `ingest()` toma el advisory lock (`writer.try_acquire_ingestion_lock()`, `-02`) al arrancar; si
  devuelve `False`, falla claro de inmediato (otra ejecución ya está en curso) — nunca corre en paralelo
  con otra.
- `uc_id` duplicado entre ficheros (2 o más) → **todo-o-nada**: se valida en memoria (recolectando todos
  los `uc_id` parseados) ANTES de cualquier `upsert_document`/`delete_by_uc_ids` — si hay conflicto,
  ninguna fila nueva ni ningún borrado de esa ejecución llega a BD (ni las altas válidas ni las
  reconciliaciones de documentos retirados). Con 3+ ficheros para el mismo `uc_id`, el error reporta
  **todos** los ficheros en conflicto, no solo un par.
- Un fallo real (no de validación) del embedder o del writer a mitad de un batch con varios documentos
  → aborta **todo** el run (mismo criterio todo-o-nada, para cualquier causa de fallo) — no hay éxito
  parcial de documentos ya procesados antes del fallo.
- "¿Re-embeber este chunk?" → el pipeline compara `chunk.content` contra
  `existing_chunk_contents(uc_id)` (clave natural `(document_id, ordinal)`, sin columna de hash); solo
  los chunks nuevos/cambiados van al embedder (`-05`) — los que no cambiaron se mandan a
  `upsert_document` con `ChunkWrite.vector=None` ("no lo toques", `-02`).
- Reconciliación: documentos retirados del origen (`existing_uc_ids() − uc_ids del origen`) →
  `delete_by_uc_ids`. Chunks retirados de un documento que sigue vivo (menos `ordinal` que antes) → los
  borra `upsert_document` (`-02`), no este módulo.
- Documento malformado (parser devuelve `ParseError`) → se salta con log; no aborta el batch.
- Origen vacío o todo malformado (0 documentos válidos) → éxito, 0 procesados, sin tocar BD.
- Reporte final: nº documentos procesados/actualizados/omitidos/errores + discrepancias `package` (solo
  vía `structlog`, no en el reporte — decisión de `grilling`).

## Spec

- `.claude/specs/backend/rag-ingestion.md` (completa) y §7 (refuerzos).
- `.claude/specs/backend/casos-de-uso/CU-BE-07-ingestion-de-la-kb.md` (Gherkin completo — esta tarea es
  la que de verdad lo satisface end-to-end).
- `pipeline.py`: `async def ingest(path: Path, *, writer: KBIndexWriter, model: EmbeddingModel) ->
  IngestReport`.

## Fuera de alcance

- CLI (parseo de args, exit codes) — tarea `-07`.
- Implementar `search`/el retriever — fuera de este plan (tarea 14).
- Ejecutar contra la KB real (no existe en esta máquina) — verificación manual del owner cuando la
  tenga disponible.

## Scenarios (Gherkin)

Fuente única (SDD): `CU-BE-07-ingestion-de-la-kb.md`, sección `## Criterios de aceptación (Gherkin)`
(ya actualizada tras `grilling`/`design-review`: comparación por contenido en vez de hash, chunk
huérfano en documento vivo, todo-o-nada extendido a la reconciliación). Esta tarea cubre **todos** sus
escenarios, a nivel de **integración** (Postgres+pgvector real vía Docker; `EmbeddingModel` fake para no
pegar a red):

- `Ingesta de un UC válido`
- `Re-ingesta idempotente sin cambios`
- `Documento malformado se salta`
- `uc_id duplicado aborta el batch`
- `Documento retirado se reconcilia`
- `Chunk retirado de un documento que sigue vivo`
- `uc_id duplicado bloquea también la reconciliación del mismo run`
- `Precedencia del package del frontmatter`
- `package o domain fuera de catálogo se salta`
- `3 o más ficheros con el mismo uc_id reportan todos los conflictos`
- `Un fallo real a mitad de un batch de varios documentos aborta todo el run`
- `Ejecuciones concurrentes de la ingestión no se solapan`
- `Un origen sin documentos válidos termina con éxito sin efecto`

> Añadido para esta tarea (edición parcial, sin escenario propio en el CU — es el mecanismo interno que
> hace posible `Re-ingesta idempotente sin cambios` también cuando el cambio es parcial):
> ```gherkin
> Scenario: Edición parcial de un documento solo re-embebe los chunks cambiados
>   Given un UC ya ingerido donde el ordinal 0 cambia de contenido y el ordinal 1 permanece igual
>   When se ingiere la KB
>   Then el chunk 0 se re-embebe (embed_documents se llama con su texto) y el chunk 1 conserva su
>     vector existente (upsert_document recibe ChunkWrite.vector=None para el ordinal 1)
> ```

## Provides

- `ingest(path, *, writer, model) -> IngestReport` en `ingestion/pipeline.py`.
- Consumido por `-07` (CLI).

## Definition of Done

- [x] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [x] Cada escenario del CU (los 9 de arriba) tiene al menos un test
- [x] Todos los tests en verde (`make test`) — 914 passed
- [x] Spec cumplida; `Provides` disponible para `-07`
- [x] `ruff check` + `ruff format --check` + `mypy` strict OK
- [x] Gate de mutation `cosmic-ray` (`break: 80`, referencia no verificada) sobre `pipeline.py` —
  4.50% supervivencia (5/111, los 5 documentados como equivalentes)
- [x] Gate `/sdd-lint` — N/A esta tarea: no edita spec.md/CU/ADR (solo los satisface end-to-end)
- [x] Gate de `fact-checker` superado (INCORRECTO bloquea) — 10/10 VERIFICADO (3er intento; los dos
  anteriores fallaron por el equipo suspendiéndose durante el gate de mutation, no por el trabajo)
- [x] Documentación — docstring de la orquestación (por qué el diff de re-embeber vive aquí y no en el
  embedder) + session log
