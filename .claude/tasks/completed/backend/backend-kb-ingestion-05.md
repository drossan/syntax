---
id: backend-kb-ingestion-05
package: backend
plan: kb-ingestion
status: completed
priority: 2
depends_on: [backend-kb-ingestion-01, backend-kb-ingestion-04]
estimate: 2h
actual: 2h
created: 2026-08-21
updated: 2026-08-21
---

# Embedder

## Description

`app/ingestion/embedder.py` es GUIÓN puro. Recibe los `Chunk` de `-04` y devuelve el mismo chunk con su
vector, usando el `EmbeddingModel` de `-01`. **Decisión de diseño** (del plan, confirmada en
`design-review`): el embedder es "tonto" — siempre embebe lo que recibe, sin conocer BD ni decidir si un
chunk cambió. La decisión de "¿hace falta re-embeber este chunk?" vive en el pipeline (`-06`), que ya
conoce tanto `KBIndexWriter.existing_chunk_contents` como el embedder: solo le pasa a este los chunks
cuyo contenido cambió o son nuevos. Esto mantiene el embedder testeable con un `EmbeddingModel` fake puro
(mismo patrón que `_FakeChatModel` de `tests/test_classification.py`), sin mocks de BD.

**Sub-lotes** (hallazgo de `scenario-coverage`: con la KB real, un batch de todos los chunks nuevos/
cambiados puede superar el límite de items por request del proveedor OpenAI): `embed()` trocea
internamente en sub-lotes de tamaño configurable (`Settings.embedding_batch_size`, nuevo) si el número
de chunks lo supera — transparente para el llamante, que sigue recibiendo un `ChunkWithVector` por
chunk, en el mismo orden.

## Spec

- `.claude/specs/backend/rag-ingestion.md` §5.
- `core/config.py`: añade `embedding_batch_size: int = Field(default=..., gt=0)` a `Settings` (elige un
  default conservador, p.ej. 100 — por debajo del límite real de items por request de OpenAI).
- `embedder.py`: `async def embed(chunks: list[Chunk], model: EmbeddingModel) -> list[ChunkWithVector]`
  (`ChunkWithVector = Chunk + vector: list[float]`). Si `len(chunks) > settings.embedding_batch_size`,
  hace varias llamadas a `embed_documents` (una por sub-lote) en vez de una sola con todos los textos.
  Preserva el orden/`ordinal` de entrada en la salida, sea una o varias llamadas.

## Fuera de alcance

- Decidir qué chunks re-embeber (esa lógica vive en el pipeline, `-06`) — este módulo no consulta BD.
- El adaptador OpenAI real (`-01`, ya completada, consumida aquí vía el puerto `EmbeddingModel`).

## Scenarios (Gherkin)

Fuente única (SDD): `CU-BE-07-ingestion-de-la-kb.md`. Esta tarea es un paso interno del pipeline sin
escenario de usuario propio en el CU (lo orquesta `-06`); cubre el contrato de `embed()`:

```gherkin
Feature: Embedder

  Scenario: Embeber una lista de chunks devuelve un vector por chunk, en el mismo orden
    Given una lista de Chunk y un EmbeddingModel fake que devuelve un vector por texto recibido
    When se llama a embed(chunks, model)
    Then el resultado tiene un ChunkWithVector por chunk de entrada, en el mismo orden y con su vector

  Scenario: embed() hace una sola llamada al proveedor si el batch no supera el límite
    Given una lista de N chunks con N <= settings.embedding_batch_size
    When se llama a embed(chunks, model)
    Then embed_documents del EmbeddingModel se llama exactamente una vez, con los N textos

  Scenario: embed() trocea en sub-lotes si el batch supera el límite configurado
    Given una lista de chunks con más elementos que settings.embedding_batch_size
    When se llama a embed(chunks, model)
    Then embed_documents se llama varias veces (sub-lotes), y el resultado preserva un ChunkWithVector
      por chunk de entrada, en el mismo orden

  Scenario: Lista de chunks vacía no llama al proveedor
    Given una lista vacía de chunks
    When se llama a embed([], model)
    Then el resultado es una lista vacía y embed_documents no se llama

  Scenario: Un solo chunk hace una sola llamada con un solo texto
    Given una lista con exactamente un chunk
    When se llama a embed(chunks, model)
    Then embed_documents se llama una vez con ese único texto, y el resultado tiene un solo ChunkWithVector

  Scenario: Fallo del proveedor durante embed() se propaga
    Given un EmbeddingModel fake que lanza (PortError) al procesar un sub-lote
    When se llama a embed(chunks, model)
    Then la excepción se propaga (no se traga ni deja resultados parciales inconsistentes)

  Scenario: El proveedor devuelve un número de vectores distinto al de textos enviados en un sub-lote
    Given un EmbeddingModel fake que devuelve N-1 vectores para N textos de un sub-lote
    When se llama a embed(chunks, model)
    Then se detecta el desajuste y falla claro (no asigna vectores a chunks equivocados)
```

## Provides

- `embed(chunks, model) -> list[ChunkWithVector]` en `ingestion/embedder.py`.
- `Settings.embedding_batch_size`.
- Consumido por `-06` (pipeline).

## Definition of Done

- [x] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [x] Cada escenario tiene al menos un test (camino feliz + bordes/errores)
- [x] Todos los tests en verde (`make test`) — 896 passed
- [x] Spec cumplida; `Provides` disponible para `-06`
- [x] `ruff check` + `ruff format --check` + `mypy` strict OK
- [x] Gate de mutation `cosmic-ray` (`break: 80`, referencia no verificada) sobre `embedder.py` —
  5.56% supervivencia (2/36, los 2 documentados como equivalentes)
- [x] Gate `/sdd-lint` — N/A esta tarea: no toca spec.md/CU/ADR
- [x] Gate de `fact-checker` superado (INCORRECTO bloquea) — 7/7 VERIFICADO
- [x] Documentación — docstring explicando por qué el embedder no conoce BD (esa decisión es del
  pipeline) + session log
