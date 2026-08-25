---
id: backend-kb-retriever-04
package: backend
plan: kb-retriever
status: pending
priority: 1
depends_on: [backend-kb-retriever-01]
estimate: 4h
actual:
created: 2026-08-24
updated: 2026-08-24
---

# `SqlAlchemyKBIndexWriter.search()` real (pgvector, coseno)

## Description

`app/infra/vector/__init__.py:168-177` es hoy `raise NotImplementedError("search real: tarea 14
(retriever, CU-BE-05)")`. Es la **única** puerta de entrada a la búsqueda ANN: la usarán tanto el camino
HTTP (`-05`/`-06`) como el nodo `retrieve` del grafo en el plan del agent-graph.

Esta tarea la implementa **sin política de negocio**: coseno crudo, filtros y top-k. El peso de `estado`
y el dedup viven en `app/rag/` (`-05`), decisión D3b — así la infra sigue siendo infra y un futuro índice
ANN sigue siendo utilizable (el `ORDER BY` no lleva expresiones ponderadas).

Specs: `.claude/specs/backend/rag-ingestion.md` §6, `ADR-0010`, `ADR-0018`, `data-model.md` §4.3.

## Spec

- Implementar en `app/infra/vector/__init__.py`:
  ```python
  async def search(self, query_vector, *, top_k, domain=None, package=None, estado=None) -> list[Hit]
  ```
- **Consulta**: `JOIN` `embedding` → `kb_chunk` → `kb_document`, ordenada por
  `Embedding.vector.cosine_distance(query_vector)` ascendente, `LIMIT top_k`.
  **Verificado**: `cosine_distance` existe en el comparador de `pgvector.sqlalchemy.Vector` instalado.
- **Score acotado**: `score = max(0.0, 1.0 - distance)` (hallazgo C1). `1 - cosine_distance` ∈ [-1,1];
  sin el clamp, un hit de similitud negativa haría que el boost multiplicativo de `-05` lo **penalizara**
  e invirtiera el orden frente a `draft`. Un coseno negativo es "menos relacionado que el azar": no hay
  ranking que preservar por debajo de 0.
- **Filtro por modelo de embeddings** (hallazgo A3): solo participan las filas con
  `Embedding.model == settings.embedding_model`. `app/infra/db/models/kb.py:65` documenta esa columna
  como *"guarda qué modelo lo generó (detectar mezclas)"*: comparar vectores de dos espacios distintos
  devolvería **basura perfectamente ordenada**, sin señal de error. Decidir en la sesión cómo llega
  `settings` al adaptador (parámetro de constructor o argumento) sin romper a los callers de ingestión
  existentes — hay tests que lo construyen con solo `session` (`tests/test_vector_adapter.py`).
- **Filtros opcionales** `domain` / `package` / `estado` sobre `kb_document`, combinables con `AND`,
  omitidos si son `None`. `estado` sigue siendo **opt-in**, nunca filtro por defecto (ADR-0010).
- **`Hit` gana `content`** en `app/domain/ports/vector.py`: texto completo del chunk. Lo necesita el
  `snippet` de `-06` y el prompt del nodo `generate` del plan siguiente. **`Hit.score` se queda CRUDO**
  (sin peso): el ponderado solo existe al producir el `KBSearchHit` (hallazgo C2, para que el futuro
  `confidence.py` no cuente `estado` dos veces). Actualizar el docstring del DTO y el del módulo, que
  hoy dicen que `search` está "sin implementar todavía (tarea 14)".
- **Chunks sin embedding** (hallazgo A4): el `JOIN` los excluye por construcción. Debe haber un
  escenario que lo fije como comportamiento **decidido**, no accidental — es un caso real
  (`ChunkWrite.vector=None` sobre un chunk nuevo no crea fila de `embedding`, según el docstring de
  este mismo módulo).
- Errores de infraestructura → `PortError`, igual que el resto de métodos de la clase.
- **Tests de INTEGRACIÓN** contra Postgres de docker-compose, extendiendo `tests/test_vector_adapter.py`
  (ya tiene fixture `superuser_engine`, `TRUNCATE` y el helper `_vector(value)` que construye vectores de
  `EMBEDDING_DIM_LITERAL`). Vectores deterministas de dimensión real para que el orden sea predecible.
- **Docstrings** en todo símbolo público, al escribirlo.

## Fuera de alcance

- **Peso de `estado` y dedup**: viven en `app/rag/` (`-05`). Este adaptador no aplica política.
- **Índice ANN**: diferido (D4) hasta 50.000 filas en `kb_chunk`; el umbral lo documenta `-01`.
- **Ventana / paginación**: las decide `-05`/`-06`; aquí solo se honra el `top_k` recibido.
- Búsqueda híbrida BM25 y re-rank por cross-encoder: diferidos por ADR-0010 y `rag-ingestion.md` §8.
- Tocar `app/infra/vectorstore/`, `deps.py` o el router.

## Scenarios (Gherkin)

Criterios de aceptación en los casos de uso (fuente única):

- [`.claude/specs/backend/casos-de-uso/CU-BE-12-consulta-de-la-kb-desde-el-panel.md`](../../../specs/backend/casos-de-uso/CU-BE-12-consulta-de-la-kb-desde-el-panel.md)
- [`.claude/specs/backend/casos-de-uso/CU-BE-05-clasificacion-y-retrieval-rag.md`](../../../specs/backend/casos-de-uso/CU-BE-05-clasificacion-y-retrieval-rag.md)

Escenarios que materializa esta tarea:

- CU-BE-12 · *La búsqueda devuelve documentos ordenados por relevancia* (la parte de orden por coseno)
- CU-BE-12 · *Una similitud negativa no invierte el orden de los resultados* — el clamp a `[0,1]`.
  **El plan lo prometía en `design-review` (C1) y este `## Scenarios` no lo listaba**: lo cazó
  `scenario-coverage`.
- CU-BE-12 · *Los filtros acotan la búsqueda*
- CU-BE-12 · *Los filtros combinados acotan por conjunción* (los tres a la vez, no uno aislado)
- CU-BE-12 · *Pedir un estado concreto sí lo filtra* — RN-2 describe **dos** comportamientos (peso y
  filtro opt-in) y solo el peso tenía Gherkin; el filtro duro se materializa aquí
- CU-BE-12 · *Pedir más resultados de los que existen devuelve solo los que hay* (fronteras de `top_k`)
- CU-BE-12 · *Solo participan los vectores del modelo de embeddings configurado*
- CU-BE-12 · *Un chunk sin embedding no participa ni rompe la búsqueda*
- CU-BE-12 · *Un fallo de la base de datos no se disfraza de KB vacía* — aquí, sobre el `JOIN` de `search`
- CU-BE-05 · *Ticket no clasificable usa fallback sin filtro de dominio* (aquí: `domain=None` no filtra)

## Provides

- `SqlAlchemyKBIndexWriter.search()` funcionando: `-05` (retriever) y el plan del agent-graph lo consumen.
- `Hit.content` disponible en el DTO del puerto; `Hit.score` garantizado **crudo** y en `[0, 1]`.

## Definition of Done

- [ ] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [ ] Cada escenario del CU que materializa esta tarea tiene al menos un test (camino feliz + bordes)
- [ ] Todos los tests en verde (`make test`, sin regresión sobre los 1064)
- [ ] `grep -rn "NotImplementedError" app/infra/vector/` no devuelve nada
- [ ] Spec cumplida; lo declarado en `Provides` queda realmente disponible para las tareas dependientes
- [ ] Lint / format / typecheck OK (`ruff`, `mypy --strict`)
- [ ] Gate de mutation testing superado (`make mutation`, cosmic-ray `break: 80`) sobre los ficheros tocados
- [ ] **Gate `sdd-lint` superado** — tras `mutation`, antes de `fact-checker`
- [ ] Gate de `fact-checker` superado — antes de commit/resumen
- [ ] **SDD** — sin cambios de spec/CU (los fijó `-01`); declararlo así en el session log
- [ ] Documentación actualizada — tres capas:
  - [ ] **Docstrings** — `search`, `Hit.content`, y los docstrings de módulo que decían "sin implementar"
  - [ ] **Doc técnica** — donde aplique
  - [ ] **Histórico** — session log en `.claude/context/backend/backend-kb-retriever-04.md`

> ⚠️ **No solapar `pytest` con `cosmic-ray exec`**.
> Requiere la DB: `docker compose -f backend/docker-compose.yml up -d db`.
