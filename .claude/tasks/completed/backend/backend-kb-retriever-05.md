---
id: backend-kb-retriever-05
package: backend
plan: kb-retriever
status: done
priority: 2
depends_on: [backend-kb-retriever-03, backend-kb-retriever-04]
estimate: 3h
actual: 2h
created: 2026-08-24
updated: 2026-08-25
---

# `app/rag/`: re-ranking por `estado`, dedup por `uc_id` y retriever

## Description

`app/rag/reranker.py` y `app/rag/retriever.py` existen solo como **guión** (docstrings "→ tarea 14").
Esta tarea los hace reales. Es donde vive la **política de negocio** del retrieval: el peso de `estado`
y el dedup por documento — deliberadamente fuera del adaptador SQL (decisión D3b), para que sean
funciones puras testeables sin Postgres y para no dejar inservible un futuro índice ANN.

Specs: `.claude/specs/backend/rag-ingestion.md` §4 y §6, `ADR-0010` (peso de `estado`), `ADR-0018`.

## Spec

- **`app/rag/reranker.py`** — función pura:
  ```python
  def rerank(hits: list[Hit], *, weight: float) -> list[RankedHit]
  ```
  - `RankedHit` = dataclass frozen con el `Hit` original y su `weighted_score`. **`Hit.score` NO se
    muta**: el crudo debe sobrevivir para el futuro `confidence.py` (hallazgo C2).
  - `weighted_score = hit.score * (1 + weight)` si `hit.estado is KbEstado.active`; si no,
    `hit.score` **intacto**. El "suelo" de ADR-0010 se cumple por construcción: `draft` no se toca.
  - Orden descendente por `weighted_score`, **estable** ante empates (que dos hits empatados no cambien
    de orden entre ejecuciones — importa para la paginación estable del contrato).
  - `weight = 0.0` es legítimo: desempate desactivado, orden = coseno puro.
- **Dedup** — función pura (fichero nuevo `app/rag/dedup.py`, o dentro de `reranker.py`; decidir en la
  sesión y justificarlo):
  ```python
  def dedup_by_uc_id(ranked: list[RankedHit]) -> list[RankedHit]
  ```
  - Sobre una lista **ya ordenada**: conserva el primer `RankedHit` de cada `uc_id` y descarta el resto.
  - Vive en `app/rag/` pero **la llama solo el adaptador HTTP** (`-06`): el camino del agente consume
    chunks sin deduplicar (D3a). **Sin flag `dedup: bool`** — un flag cuya segunda rama no tiene
    consumidor es justo lo que este plan evita en otros sitios (hallazgo A1).
- **`app/rag/retriever.py`**:
  ```python
  async def retrieve(query: str, *, top_k: int, domain=None, package=None, estado=None) -> list[RankedHit]
  ```
  - Compone: `EmbeddingModel.embed_query(query)` → `KBIndexWriter.search(vector, top_k=..., filtros)`
    → `rerank(hits, weight=...)`. **No deduplica** (eso lo hace su llamante HTTP).
  - Recibe los puertos por inyección (constructor de una clase o parámetros): el dominio/aplicación
    **no** importa infra.
  - **`retrieve` recibe un `top_k` y no lo calcula.** El over-fetch
    (`rag_search_window * rag_chunks_per_doc`) lo calcula **`-06`**, el adaptador HTTP — decidido tras
    `scenario-coverage`, que señaló la ambigüedad. Motivo: la ventana es un concepto del **camino
    HTTP** (documentos por página); el nodo `retrieve` del agente no pagina y no debe heredar esa
    noción. Así el cálculo vive en **un solo sitio**.
- **Tests unit con dobles** de `EmbeddingModel` y `KBIndexWriter` (sin Postgres, sin red). Patrón de
  dobles: mirar `tests/test_openai_adapter.py` y los tests de servicios de dominio.
- **Frontera de la ventana**: incluir tests **mínimos** de slicing/paginación. (El `design-review`
  sugería no gastar escenarios ahí por no tener consumidor; se acepta a medias porque el gate de
  mutation generará survivors sobre ese código si no hay asserts.)
- **Docstrings** en todo símbolo público, al escribirlo.

## Fuera de alcance

- `app/rag/confidence.py` y `app/rag/citations.py`: **siguen en guión**. No tienen consumidor hasta el
  plan del agent-graph, y fijar una firma sin consumidor es el criterio que el propio repo rechaza
  (`ports/embeddings.py`, `ports/llm.py`).
- Nodos `classify` / `grade` del grafo, y los escenarios 1, 3 y 5 de CU-BE-05.
- Re-rank por cross-encoder: diferido (ADR-0010). El seam se menciona, no se construye.
- Tocar `app/infra/`, `deps.py` o el router.

## Scenarios (Gherkin)

Criterios de aceptación en los casos de uso (fuente única):

- [`.claude/specs/backend/casos-de-uso/CU-BE-12-consulta-de-la-kb-desde-el-panel.md`](../../../specs/backend/casos-de-uso/CU-BE-12-consulta-de-la-kb-desde-el-panel.md)
- [`.claude/specs/backend/casos-de-uso/CU-BE-05-clasificacion-y-retrieval-rag.md`](../../../specs/backend/casos-de-uso/CU-BE-05-clasificacion-y-retrieval-rag.md)

Escenarios que materializa esta tarea:

- CU-BE-12 · *Los borradores participan ponderados, no excluidos*
- CU-BE-12 · *Sin desempate configurado el orden es el de la similitud pura* (`weight = 0.0`, que el
  propio Spec declara legítimo y no tenía escenario)
- CU-BE-12 · *Un documento con varias secciones relevantes aparece una sola vez* (la función
  `dedup_by_uc_id`), incluida su frontera con lista vacía
- CU-BE-12 · *Una búsqueda sin coincidencias devuelve vacío, no un error* — a nivel de las funciones
  puras: `rerank` y `dedup_by_uc_id` sobre lista vacía
- CU-BE-12 · *Página solicitada según su posición respecto a la ventana* (`Scenario Outline`)
- CU-BE-05 · *El retrieval no se vacía por el predominio de borradores*

Frontera adicional que la sesión debe cubrir con un test aunque no tenga escenario propio en el CU (es
detalle de implementación de la estabilidad que exige RN-6, no comportamiento de usuario): **empate
exacto de `weighted_score` entre dos `uc_id` distintos** conserva el orden de entrada. Hallazgo de
`scenario-coverage`.

## Provides

- `app/rag/reranker.py::rerank` + el tipo `RankedHit` (score ponderado separado del crudo).
- `dedup_by_uc_id` como función pura, lista para que `-06` la llame desde el adaptador HTTP.
- `app/rag/retriever.py::retrieve` componiendo embeddings + ANN + re-ranking: lo consume `-06`, y el
  plan del agent-graph lo reusará para el nodo `retrieve`.

## Definition of Done

- [x] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [x] Cada escenario del CU que materializa esta tarea tiene al menos un test (camino feliz + bordes/errores)
- [x] Todos los tests en verde (`make test`, sin regresión sobre los 1064)
- [x] Spec cumplida; lo declarado en `Provides` queda realmente disponible para las tareas dependientes
- [x] Lint / format / typecheck OK (`ruff`, `mypy --strict`)
- [x] Gate de mutation testing superado (`make mutation`, cosmic-ray `break: 80`) sobre los ficheros tocados
- [x] **Gate `sdd-lint` superado** — tras `mutation`, antes de `fact-checker`
- [x] Gate de `fact-checker` superado — antes de commit/resumen
- [x] **SDD** — sin cambios de spec/CU (los fijó `-01`); declararlo así en el session log
- [x] Documentación actualizada — tres capas:
  - [x] **Docstrings** — todo símbolo público; los docstrings-guión de `app/rag/` sustituidos por doc real
  - [x] **Doc técnica** — `rag-ingestion.md` §4 si el detalle de la fórmula lo merece
  - [x] **Histórico** — session log en `.claude/context/backend/backend-kb-retriever-05.md`

> ⚠️ **No solapar `pytest` con `cosmic-ray exec`**.
