---
id: backend-kb-ingestion-02
package: backend
plan: kb-ingestion
status: completed
priority: 1
depends_on: []
estimate: 4h
actual: 4h
created: 2026-08-21
updated: 2026-08-21
---

# Puerto `KBIndexWriter` + adaptador pgvector real + migración `kb_chunk`

## Description

`domain/ports/vector.py` es hoy solo docstring (GUIÓN); `infra/vector/__init__.py` también. Esta tarea
define el puerto de **escritura** de la KB — nombrado `KBIndexWriter` (no `VectorStore`, para no
colisionar con la clase `VectorStore` ya real de `domain/ports/vectorstore.py`, que es el puerto de
**lectura** del router `kb`) — y su adaptador SQLAlchemy+pgvector real.

**Decisión de `grilling`, resuelta en `design-review`**: `KBIndexWriter` incluye ya `search` (firma
vectorial: `search(query_vector: list[float], *, top_k: int, domain=None, package=None, estado=None) ->
list[Hit]`, `Hit = {uc_id, chunk_id, section_type, title, source_url, domain, estado, score}`, según
`rag-ingestion.md` §6) — **este es el puerto que la tarea 14 (retriever) implementará de verdad**;
`VectorStore`/`StubVectorStore` quedan deprecados entonces, no en este plan. Aquí `search` se implementa
con `raise NotImplementedError` (sin test de esa rama: no hay caller que la ejercite todavía).

También define `KBDocumentDraft` (tipo propio de escritura, con `traza` — no se toca la entidad
`KBDocument` compartida con el puerto de lectura, cuyo shape ya es "el final" para la tarea 14).

**Migración aditiva**: `UniqueConstraint(document_id, ordinal)` en `kb_chunk` — defensa en profundidad de
la clave natural que usa la detección de "chunk sin cambios" (decisión de `grilling`, sin columna de
hash). No añade columna, no requiere backfill.

## Spec

- `.claude/specs/backend/rag-ingestion.md` §6 (contrato de `search`, sin implementar aquí).
- `.claude/specs/backend/data-model.md` §4.3/7 (schema `kb_document`/`kb_chunk`/`embedding`, cascada).
- `domain/ports/vector.py`: `KBDocumentDraft` (Pydantic v2: `uc_id, domain, package, estado, title,
  source_url, traza: list[str] | None, updated`); `class KBIndexWriter(Protocol)`:
  - `async def existing_uc_ids(self) -> set[str]`
  - `async def existing_chunk_contents(self, uc_id: str) -> dict[int, str]` (`ordinal -> content`, `{}`
    si el documento no existe)
  - `async def upsert_document(self, doc: KBDocumentDraft, chunks: list[ChunkWrite]) -> UpsertReport`
    (upsert idempotente por `uc_id`; borra los `kb_chunk`/`embedding` cuyo `ordinal` ya no está en
    `chunks`, aunque el documento siga vivo). `ChunkWrite.vector: list[float] | None` — decisión de
    `scenario-coverage`: `None` significa "no toques el embedding existente de ese `ordinal`" (edición
    parcial: el pipeline solo manda vector real para los chunks con contenido cambiado). Fallos de
    infraestructura (BD caída/timeout) se propagan envueltos en `PortError`.
  - `async def delete_by_uc_ids(self, uc_ids: set[str]) -> int` (cascada a chunk/embedding)
  - `async def search(self, query_vector: list[float], *, top_k: int, domain=None, package=None,
    estado=None) -> list[Hit]`
  - `async def try_acquire_ingestion_lock(self) -> bool` (decisión de `scenario-coverage`: usa
    `pg_try_advisory_lock` — no bloqueante; devuelve `False` de inmediato si otra ejecución ya lo tiene,
    en vez de esperar indefinidamente. El pipeline, `-06`, decide qué hacer con `False`: fallar claro).
- `infra/vector/__init__.py`: adaptador real de todo lo anterior salvo `search`
  (`raise NotImplementedError`).
- Migración Alembic nueva (aditiva): `UniqueConstraint(document_id, ordinal)` en `kb_chunk`.

## Fuera de alcance

- Implementar `search` de verdad — tarea 14 (retriever, CU-BE-05), fuera de este plan.
- Tocar `domain/ports/vectorstore.py`/`StubVectorStore`/el router `kb` — sin cambios.
- Loader/parser/chunker/embedder/pipeline — tareas `-03` a `-07`.

## Scenarios (Gherkin)

Fuente única (SDD): `CU-BE-07-ingestion-de-la-kb.md`. Infraestructura de adaptador (sin caller directo
en un escenario de usuario todavía — lo consumirá `-06`). Nivel: **integración real contra
Postgres+pgvector** (Docker, mismo patrón que `tests/test_repositories_ticket.py` — fixture
`superuser_engine` + `TRUNCATE` autouse):

```gherkin
Feature: Adaptador de escritura de la KB (pgvector)

  Scenario: upsert_document inserta un documento nuevo con sus chunks y embeddings
    Given un KBDocumentDraft con sus chunks+vectores, sin fila previa en BD
    When se hace upsert_document
    Then kb_document/kb_chunk/embedding quedan persistidos con esos datos

  Scenario: upsert_document sobre un uc_id existente no duplica el documento
    Given un kb_document ya persistido para ese uc_id
    When se hace upsert_document con datos nuevos para el mismo uc_id
    Then sigue existiendo una sola fila de kb_document para ese uc_id, con los datos actualizados

  Scenario: upsert_document borra los chunks cuyo ordinal ya no llega
    Given un documento con chunks persistidos en los ordinales 0, 1 y 2
    When se hace upsert_document con chunks solo para los ordinales 0 y 1
    Then el chunk (y su embedding) del ordinal 2 se elimina

  Scenario: delete_by_uc_ids elimina documento, chunks y embeddings en cascada
    Given un kb_document persistido con chunks y embeddings
    When se llama a delete_by_uc_ids con su uc_id
    Then no quedan filas de ese documento ni de sus chunks/embeddings

  Scenario: existing_chunk_contents refleja lo persistido
    Given un documento con chunks persistidos
    When se llama a existing_chunk_contents(uc_id)
    Then devuelve {ordinal: content} exactamente como está en BD

  Scenario: existing_uc_ids refleja el corpus persistido
    Given varios kb_document persistidos
    When se llama a existing_uc_ids()
    Then devuelve exactamente el conjunto de sus uc_id

  Scenario: search sin implementar
    Given el adaptador pgvector real
    When se llama a search(...)
    Then lanza NotImplementedError

  Scenario: upsert_document conserva el embedding de un chunk cuyo ChunkWrite.vector es None
    Given un documento con un chunk ya persistido en el ordinal 0
    When se hace upsert_document con un ChunkWrite para el ordinal 0 con vector=None
    Then el embedding existente de ese ordinal no cambia (edición parcial: solo se tocan los chunks con
      vector real)

  Scenario: upsert_document con chunks=[] borra todos los chunks previos del documento
    Given un documento con chunks persistidos en los ordinales 0 y 1
    When se hace upsert_document con chunks=[] para el mismo uc_id
    Then el documento sigue existiendo pero sin ningún kb_chunk/embedding

  Scenario: existing_chunk_contents para un uc_id inexistente devuelve {}
    Given ningún kb_document con ese uc_id
    When se llama a existing_chunk_contents(uc_id)
    Then devuelve {}

  Scenario: existing_uc_ids con corpus vacío devuelve el conjunto vacío
    Given ningún kb_document persistido
    When se llama a existing_uc_ids()
    Then devuelve set()

  Scenario: delete_by_uc_ids con un conjunto vacío no falla y no borra nada
    Given cualquier estado de BD
    When se llama a delete_by_uc_ids(set())
    Then devuelve 0 y no se ejecuta ningún DELETE

  Scenario: Un fallo de infraestructura durante upsert_document se propaga envuelto en PortError
    Given una conexión a BD que falla (timeout/caída) durante upsert_document
    When se invoca el método
    Then la excepción se propaga envuelta en PortError, no cruda

  Scenario: try_acquire_ingestion_lock devuelve True si nadie más lo tiene
    Given ninguna sesión con el advisory lock de ingestión activo
    When se llama a try_acquire_ingestion_lock()
    Then devuelve True

  Scenario: try_acquire_ingestion_lock devuelve False si otra sesión ya lo tiene
    Given una sesión que ya tiene el advisory lock de ingestión (pg_advisory_lock, misma clave)
    When otra sesión llama a try_acquire_ingestion_lock()
    Then devuelve False de inmediato, sin bloquear
```

## Provides

- `KBIndexWriter` (Protocol) + `KBDocumentDraft`/`ChunkWrite`/`Hit`/`UpsertReport` en
  `domain/ports/vector.py`.
- Adaptador real en `infra/vector/__init__.py`.
- Migración `UniqueConstraint(document_id, ordinal)` en `kb_chunk`.
- Consumido por la tarea `-06` (pipeline) y, más adelante, por la tarea 14 (retriever, fuera de este
  plan) para `search`.

## Definition of Done

- [x] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [x] Cada escenario tiene al menos un test (camino feliz + bordes/errores)
- [x] Todos los tests en verde (`make test`) — 797 passed
- [x] Spec cumplida; `Provides` disponible para `-06`
- [x] `ruff check` + `ruff format --check` + `mypy` strict OK
- [x] Gate de mutation `cosmic-ray` (`break: 80`, referencia no verificada) sobre `vector.py`/
  `infra/vector/__init__.py` — 2.40% supervivencia (3/125 mutantes, los 3 documentados como
  equivalentes: 2 `NumberReplacer` sobre la constante arbitraria del lock, 1 sobre el separador
  keyword-only de la firma de `search`, que solo lanza `NotImplementedError`)
- [x] Gate `/sdd-lint` — N/A esta tarea: no toca spec.md/CU/ADR (solo `data-model.md`, que no es
  artefacto SDD auditado por `sdd-lint`); el gate del plan ya corrió sobre CU-BE-07 en la tarea `-01`
- [x] Gate de `fact-checker` superado (INCORRECTO bloquea) — 9/9 VERIFICADO
- [x] Documentación — docstrings (por qué `KBIndexWriter` no `VectorStore`, por qué `search` fijado sin
  implementar, resolución del doble contrato con `vectorstore.py`) + `data-model.md` actualizada con la
  nueva `UniqueConstraint` + session log
