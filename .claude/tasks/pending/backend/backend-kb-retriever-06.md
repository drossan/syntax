---
id: backend-kb-retriever-06
package: backend
plan: kb-retriever
status: pending
priority: 1
depends_on: [backend-kb-retriever-02, backend-kb-retriever-05]
estimate: 4h
actual:
created: 2026-08-24
updated: 2026-08-24
---

# `PgVectorStore.search` + `snippet` end-to-end

## Description

Cierra el adaptador de lectura: `search` traduce del mundo del retriever (chunks con `Hit`) al del
router (documentos con `KBSearchHit`), aplicando ventana, dedup y paginación.

Y cierra un **drift real** descubierto en `grilling`: `snippet` está declarado en
`api-contract.yaml:1305` y **renderizado** por el front (`kb-search.tsx:141`, `{hit.snippet}`), pero no
existe en la entidad, ni en `schemas/kb.py`, ni en `_hit_to_schema`. Hoy no se nota porque el stub
devuelve `[]`; con datos reales cada tarjeta pintaría un snippet vacío. El `snippet` lo **produce** este
adaptador, así que entidad y schema van con su productor y no con el swap (hallazgo D2').

Specs: `CU-BE-12` (RN-1, RN-3, RN-4, RN-5), `ADR-0018`, `api-contract.yaml` (`:569-601`, `:1295-1305`).

## Spec

- **`PgVectorStore.search(query, *, domain, package, estado, page, page_size)`** en
  `app/infra/vectorstore/pgvector.py` (la clase la creó `-02`):
  1. **Calcular aquí** el over-fetch —`top_k = rag_search_window * rag_chunks_per_doc`— y delegar en
     `app/rag/retriever.retrieve(...)` con ese `top_k`. El cálculo vive en **este** lado y en ninguno
     más (decidido tras `scenario-coverage`): la ventana es un concepto del camino HTTP, y `retrieve`
     no debe heredar una noción de paginación que el nodo del agente no usa.
  2. `dedup_by_uc_id(...)` sobre el resultado ya re-rankeado.
  3. Recortar a `rag_search_window` documentos → esa es la ventana.
  4. Paginar: `items = ventana[(page-1)*page_size : page*page_size]`; **`total = len(ventana)`**
     (documentos distintos dentro de la ventana, RN-3). Una `page` más allá de la ventana devuelve
     `items: []` conservando el mismo `total`.
  5. Mapear cada `RankedHit` → `KBSearchHit`, con `score = weighted_score` (RN-4: relevancia
     re-rankeada, **puede superar 1.0**; no es un coseno crudo).
  - El constructor gana las dependencias que necesita (`EmbeddingModel`/retriever y `settings`), sin
    romper lo que `-02` dejó funcionando.
- **`snippet` end-to-end**:
  - `app/domain/entities/business.py::KBSearchHit` gana `snippet: str`.
  - `app/api/v1/schemas/kb.py::KBSearchHit` gana `snippet: str` (el contrato ya lo declara).
  - `_hit_to_schema` (`app/api/v1/routers/kb.py:43-52`) lo propaga.
  - **Truncado** desde `Hit.content`: ~**280 caracteres**, corte en el **último límite de palabra** antes
    del tope, con **elipsis** si se recortó. Constante documentada del adaptador, **no** un setting: no
    hay dos despliegues que la quieran distinta.
  - **No** se centra en el término buscado (RN-5): la búsqueda es semántica y el chunk puede casar sin
    contener la palabra — centrar fallaría justo cuando el RAG funciona bien. El snippet muestra el
    **principio de la sección ganadora**.
  - **Fronteras a cubrir**: chunk más largo que el tope; chunk más corto (sin elipsis); chunk de una
    sola palabra larguísima (sin espacio antes del tope); chunk vacío — `rag-ingestion.md` §2.1 declara
    válido el glosario vacío.
- **Tests de INTEGRACIÓN** contra Postgres (patrón `tests/test_vector_adapter.py`) con corpus sembrado y
  vectores deterministas, más el doble del puerto de embeddings (**sin red ni clave de OpenAI**).
- **Docstrings** en todo símbolo público, al escribirlo.

## Fuera de alcance

- Recablear `get_vector_store()`, borrar `StubVectorStore`, la validación de `q` vacía y la reescritura
  de `tests/test_router_kb.py` → **`-07`** (el swap es una costura distinta).
- Añadir `chunk_id` / `ordinal` al contrato: descartado en `grilling` (D3a).
- Tocar **código** del frontend: el `line-clamp` que le falta a la tarjeta no se añade — por eso el
  truncado ocurre en el backend.
- Paginación real en el front: no existe hoy y este plan no la crea.

## Scenarios (Gherkin)

Criterios de aceptación en el caso de uso (fuente única):

- [`.claude/specs/backend/casos-de-uso/CU-BE-12-consulta-de-la-kb-desde-el-panel.md`](../../../specs/backend/casos-de-uso/CU-BE-12-consulta-de-la-kb-desde-el-panel.md)

Escenarios que materializa esta tarea:

- *La búsqueda devuelve documentos ordenados por relevancia* (end-to-end del adaptador)
- *Un documento con varias secciones relevantes aparece una sola vez*
- *El resultado incluye un fragmento de la sección que lo justifica*
- *Una búsqueda sin coincidencias devuelve vacío, no un error* — el vacío **legítimo**, distinto del 502
- *Página solicitada según su posición respecto a la ventana* (`Scenario Outline`, aquí en el adaptador)
- *Un fallo del proveedor de embeddings no se disfraza de KB vacía* — **en la capa del adaptador**:
  que `PgVectorStore.search` no se trague el `PortError` que suben `embed_query`/`retrieve`. Hallazgo
  de `scenario-coverage`: ese comportamiento solo se probaba end-to-end en `-07`, dejando sin
  cobertura directa a su productor.

## Provides

- `PgVectorStore` completo (`search` + `list_documents` + `get_document`): `-07` solo tiene que cablearlo.
- `KBSearchHit` con `snippet` en entidad y schema, y `_hit_to_schema` propagándolo: `-07` puede escribir
  la guardia contrato↔OpenAPI sabiendo que los campos ya coinciden.

## Definition of Done

- [ ] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [ ] Cada escenario del CU que materializa esta tarea tiene al menos un test (camino feliz + bordes/errores)
- [ ] Todos los tests en verde (`make test`, sin regresión sobre los 1064)
- [ ] Spec cumplida; lo declarado en `Provides` queda realmente disponible para las tareas dependientes
- [ ] Lint / format / typecheck OK (`ruff`, `mypy --strict`)
- [ ] Gate de mutation testing superado (`make mutation`, cosmic-ray `break: 80`) sobre los ficheros tocados
- [ ] **Gate `sdd-lint` superado** — tras `mutation`, antes de `fact-checker`
- [ ] Gate de `fact-checker` superado — antes de commit/resumen
- [ ] **SDD** — sin cambios de spec/CU (los fijó `-01`); declararlo así en el session log
- [ ] Documentación actualizada — tres capas:
  - [ ] **Docstrings** — `search`, el truncado del snippet y su política (incl. por qué no se centra en el término)
  - [ ] **Doc técnica** — donde aplique
  - [ ] **Histórico** — session log en `.claude/context/backend/backend-kb-retriever-06.md`

> ⚠️ **No solapar `pytest` con `cosmic-ray exec`**.
> Requiere la DB: `docker compose -f backend/docker-compose.yml up -d db`.
