---
id: backend-kb-retriever-01
package: backend
plan: kb-retriever
status: done
priority: 1
depends_on: []
estimate: 3h
actual: 3h
created: 2026-08-24
updated: 2026-08-25
---

# SDD y contrato del camino de lectura de la KB

## Description

El camino HTTP de la KB (`/kb/search`, `/kb/documents`, `/kb/documents/{uc_id}`) se construyó en
`routers-core` **antes** de la capa SDD: no lo cubre ningún CU ni ningún FR. Además `grilling` y
`design-review` cerraron 20+ decisiones que hoy solo viven en el plan. Esta tarea materializa los
artefactos SDD y alinea el contrato, para que `-02`…`-07` tengan a qué enlazar su Gherkin.

Es **doc-only**: no escribe código de negocio. El `CU-BE-12` ya está materializado (lo creó
`/plan-task` al descomponer, porque las tareas necesitan enlazarlo); aquí se completa el resto.

Specs de referencia: `.claude/specs/backend/spec.md` (EARS), `.claude/specs/backend/rag-ingestion.md`
§4/§6, `.claude/specs/general/api-contract.md` + `.yaml`, `.claude/specs/adr/adr-index.md` (MADR).

## Spec

- **FR nuevos en `spec.md`**, sección "KB: ingestión y retrieval", numerados desde **FR-049** (el máximo
  actual es FR-048), cubriendo: búsqueda semántica desde el panel con filtros y orden `score desc`;
  dedup por `uc_id`; `total` acotado a la ventana; rechazo de consulta vacía; listado con **orden
  determinista**; detalle por `uc_id` con 404. Enlazar `CU-BE-12` en la sección "Casos de uso".
- **`CU-BE-12`**: revisar que enlaza el ADR nuevo y que sigue el estilo de los CU existentes.
- **ADR nuevo `0018-retrieval-http-de-la-kb-ventana-dedup-y-peso-de-estado.md`** (MADR, mismo formato
  que `0017`), registrando **todas** las decisiones del plan: embeber sin caché (y la caché como
  follow-up), ventana en documentos con over-fetch, dedup por `uc_id`, peso de `estado` en `app/rag/`
  con `score * (1 + w)` sobre score acotado a `[0,1]`, `Hit.score` crudo vs `KBSearchHit.score`
  ponderado, `Hit.content`, política del `snippet`, `q` vacía → 422, filtro por `embedding.model`,
  **diferir el índice ANN con umbral de 50.000 filas en `kb_chunk`** (y la nota de que un umbral sin
  alarma es una promesa que nadie cumple), **mantener los dos puertos con su deuda**, y **descartar**
  la guardia global contrato↔OpenAPI (aquí solo la de KB). Añadirlo a `adr-index.md`.
  Y las tres decisiones de `scenario-coverage`: **límite superior de `q`**; **RN-8** (la estabilidad de
  paginación se garantiza dentro de una ventana, no entre requests — limitación aceptada frente a
  cursores, que serían sobre-ingeniería para una paginación sin UI); **RN-9** (los glosarios se exponen,
  con el sesgo de `package`/`estado` por defecto documentado como defecto **de la ingestión**, a
  corregir en su propio plan — migración + re-ingesta).
- **`rag-ingestion.md` §4/§6 actualizado**: §6 hoy define la salida del retriever como "score coseno
  normalizado" y no conoce ventana, dedup ni el `score` ponderado de la API. Debe distinguir
  explícitamente la salida del **camino del agente** (chunks, `score` crudo) de la del **camino HTTP**
  (documentos, `score` ponderado), o el futuro `confidence.py` contará `estado` dos veces.
- **Nota de alcance en `CU-BE-05`**: qué escenarios cubre este plan (2 y 4) y cuáles son del plan del
  agent-graph (1, 3 y 5).
- **`api-contract.yaml`**: añadir `'422': { $ref: '#/components/responses/ValidationError' }` y
  `'502'` a `/kb/search`. Verificar si existe un `components/responses` para 502; si no, crearlo con el
  mismo patrón que `ValidationError`. Reflejar también el **`maxLength` del parámetro `q`** (decidido
  en `scenario-coverage`; `-07` lo implementa).
- **Regenerar los artefactos del front**: `pnpm gen:api` desde `frontend/` y **commitear**
  `frontend/src/types/api.ts` y `frontend/src/mocks/contract/openapi.json`. Verificación:
  `pnpm gen:api:check` en verde.
- **Corregir docstrings que afirman cosas falsas**:
  - `app/domain/ports/vector.py:9-10` — promete que la tarea 14 deja `VectorStore`/`StubVectorStore`
    "deprecados en favor de este puerto". Es imposible: `KBIndexWriter` no tiene `list_documents` ni
    `get_document`. Sustituir por la decisión real (dos puertos, con su porqué, apuntando al ADR-0018).
  - `app/infra/db/models/kb.py:7` — "Índice ANN (ivfflat/hnsw) diferido al plan RAG (13/14)" deja de
    ser cierto al cerrarse este plan: apuntar al umbral del ADR-0018.
  - `app/api/v1/routers/kb.py:8` — describe el stub como comportamiento esperado; anticipar que `-07`
    lo sustituye (o dejarlo para `-07`, pero no dejarlo mintiendo al cerrar el plan).

## Fuera de alcance

- Escribir código de negocio: esta tarea no toca `app/rag/`, `app/infra/vector/` ni `app/infra/vectorstore/`.
- Tocar **código** del frontend: solo se regeneran dos ficheros *generados* desde el contrato.
- Guardia global contrato↔OpenAPI para todos los routers (aquí solo se documenta el descarte; la de KB
  la implementa `-07`).
- La migración del índice ANN (diferida, D4): aquí solo se escribe el umbral.
- Cualquier referencia al nombre del cliente/proyecto del que se verificó el formato de la KB.

## Scenarios (Gherkin)

**Tarea doc-only**: no produce código testeable, así que no tiene escenarios propios. Los criterios de
aceptación de la capacidad que documenta viven en su caso de uso:

- [`.claude/specs/backend/casos-de-uso/CU-BE-12-consulta-de-la-kb-desde-el-panel.md`](../../../specs/backend/casos-de-uso/CU-BE-12-consulta-de-la-kb-desde-el-panel.md) — los materializan `-02`…`-07`.

**Cómo se verifica esta tarea**:

1. `/sdd-lint` en verde sobre `spec.md`, `CU-BE-12` y `ADR-0018` (formato EARS / Gherkin / MADR).
2. `pnpm gen:api:check` en verde desde `frontend/` (contrato y tipos generados sincronizados).
3. `make test` sin regresión: los tests existentes de contrato/migración no deben romperse.
4. Revisión manual de que ningún docstring corregido sigue afirmando algo falso.

## Provides

- `CU-BE-12` enlazable desde el `## Scenarios` de `-02`…`-07`.
- `ADR-0018` como fuente única del "por qué" de las decisiones de diseño del plan.
- FR-049…FR-05x en `spec.md`, trazables desde el CU.
- `api-contract.yaml` con `422`/`502` en `/kb/search` y los tipos del front regenerados: `-07` puede
  escribir la guardia contrato↔OpenAPI sin arrastrar drift previo.

## Definition of Done

- [x] Todos los tests en verde (`make test`, sin regresión sobre los 1064)
- [x] Spec cumplida; lo declarado en `Provides` queda realmente disponible para las tareas dependientes
- [x] Lint / format / typecheck OK (`ruff`, `mypy --strict`)
- [x] **Gate `sdd-lint` superado** — artefactos SDD sin ERROR de formato/completitud
- [x] Gate de `fact-checker` superado — afirmaciones de la sesión verificadas, antes de commit/resumen
- [x] **SDD** — `spec.md` (EARS) + `CU-BE-12` (Gherkin) + `ADR-0018` (MADR) creados/actualizados
- [x] Documentación actualizada — tres capas:
  - [x] **Docstrings** — los tres docstrings falsos corregidos
  - [x] **Doc técnica** — `rag-ingestion.md` §4/§6, `adr-index.md`, nota de alcance en `CU-BE-05`
  - [x] **Histórico** — session log en `.claude/context/backend/backend-kb-retriever-01.md`
- [x] `pnpm gen:api:check` en verde con los ficheros generados commiteados

> Sin línea de mutation testing: la tarea no añade código ejecutable que mutar. Se declara así en el
> session log en vez de omitirlo en silencio.
