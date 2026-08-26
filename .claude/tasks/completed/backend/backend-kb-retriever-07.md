---
id: backend-kb-retriever-07
package: backend
plan: kb-retriever
status: done
priority: 1
depends_on: [backend-kb-retriever-06]
estimate: 4h
actual: 4.5h
created: 2026-08-24
updated: 2026-08-25
---

# Swap del adaptador: `deps.py`, `q` vacía, borrado del stub y guardia del contrato

## Description

El swap: `get_vector_store()` deja de devolver `StubVectorStore` y devuelve el `PgVectorStore` real.
Es **atómico a propósito** — el router resuelve los tres endpoints por la **misma** dependencia, así que
`/kb` no puede ver datos reales hasta que `search` funcione (por eso `-06` va antes, y por eso no se
pudo adelantar la entrega del listado pese al hallazgo D1' del `design-review`).

Aquí es donde el objetivo del plan se hace visible: **`/kb` deja de estar vacío en el panel**.

Specs: `CU-BE-12`, `ADR-0018`, `.claude/specs/general/api-contract.md` + `.yaml`.

## Spec

- **`app/core/deps.py`**:
  - `get_vector_store()` pasa a recibir `session: AsyncSession = Depends(get_db_session)` y
    `settings: Settings = Depends(get_settings)`, y devuelve `PgVectorStore(...)`.
    FastAPI cachea la dependencia por request, así que router y store comparten la **misma**
    `AsyncSession` y el `global_scope`/`tenant_scope` que abrió `require_capability` — no se abren dos
    transacciones (comprobado en `design-review`).
  - **Cuidado con el fail-fast de dimensión** (hallazgo E): `OpenAIEmbeddingModel.__init__` lanza
    `PortError` si `settings.embedding_dim != EMBEDDING_DIM_LITERAL` (`openai_adapter.py:36-42`). Si se
    construye de forma eager en la dependencia, **`/kb/documents` —que no necesita embeddings— daría
    502 por una config de embeddings**. Construirlo perezosamente o inyectarlo solo en el camino de
    `search`. Debe haber un test que lo fije.
  - Quitar el import de `StubVectorStore` y actualizar el docstring de la función.
- **`q` inutilizable → 422** en `app/api/v1/routers/kb.py`, **antes** de llamar al proveedor. Tres
  casos, **una sola regla**: vacía, solo espacios, y **más larga que el máximo** (`max_length`, p.ej.
  1000 — hallazgo de `scenario-coverage`: sin tope, un cliente con un bug quema cuota de embeddings sin
  límite). Usar el mecanismo de validación que el repo ya tiene (`Query(..., min_length=1,
  max_length=...)` y/o `app.domain.errors.Validation`, que mapea a 422 en `app/api/errors.py`) —
  **verificar cuál produce el envelope problem+json esperado** antes de elegir. El `max_length` debe
  quedar reflejado en `api-contract.yaml` (lo toca `-01`).
- **Borrar `StubVectorStore`**: `app/infra/vectorstore/stub.py` y `tests/test_vectorstore_stub.py`, más
  las menciones huérfanas en docstrings — hay **7 referencias** en total (verificadas):
  `app/core/deps.py:65,118`, `app/api/v1/routers/kb.py:8`, `app/domain/ports/vector.py:10`,
  `app/domain/ports/vectorstore.py:5`, `app/infra/agent_runner/stub.py:9` (dice "mismo criterio que
  `StubVectorStore`/`StubSlaPolicy`" — quedaría huérfana), y los dos ficheros a borrar.
  Criterio: `grep -rn "StubVectorStore" app/ tests/` no debe devolver nada al cerrar.
- **Reescribir `tests/test_router_kb.py`**: hoy asierta el vacío del stub como comportamiento esperado
  (su propio docstring lo dice). Pasa a sembrar corpus real y verificar la superficie HTTP:
  resultados no vacíos, orden `score desc`, filtros, `snippet` presente, 404 del detalle, 422 de `q`
  vacía, y **502 cuando el proveedor de embeddings falla** (con un doble que levanta `PortError`).
  Es una regresión **legítima** de esos tests, no un test roto.
- **Guardia contrato↔OpenAPI** (hallazgo E3): test nuevo que compara el OpenAPI que emite `create_app()`
  con `.claude/specs/general/api-contract.yaml` para los schemas de KB (`KBSearchHit`, `KBDocument`) y
  falla si divergen los campos. **Acotado a KB**: una guardia global de todo el contrato es otro plan, y
  `-01` deja ese descarte por escrito en el ADR. Motivo: `snippet` llevaba roto desde `routers-core` y se
  descubrió por casualidad al planificar; arreglarlo sin guardia garantiza que vuelva a pasar.
- **Docstrings** actualizados: `routers/kb.py:8` describe hoy el stub como comportamiento esperado.

## Fuera de alcance

- Tocar **código** del frontend (la paginación de `/kb` y el `line-clamp` siguen sin existir).
- Guardia contrato↔OpenAPI para routers que no sean KB.
- La migración del índice ANN (diferida, D4).
- Caché de vectores de consulta (follow-up documentado en `ADR-0018`).
- Ejecutar `make migrate` / `make ingest` reales contra la fuente: es **verificación manual del owner**,
  fuera del gate de esta tarea.

## Scenarios (Gherkin)

Criterios de aceptación en el caso de uso (fuente única):

- [`.claude/specs/backend/casos-de-uso/CU-BE-12-consulta-de-la-kb-desde-el-panel.md`](../../../specs/backend/casos-de-uso/CU-BE-12-consulta-de-la-kb-desde-el-panel.md)

Escenarios que materializa esta tarea (end-to-end, sobre la superficie HTTP):

- *Un término de búsqueda inutilizable se rechaza sin consultar al proveedor* (`Scenario Outline`:
  vacío · solo espacios · más largo que el máximo)
- *Un fallo del proveedor de embeddings no se disfraza de KB vacía* (end-to-end vía HTTP → 502)
- *Listar documentos no requiere el proveedor de embeddings* — hallazgo de `scenario-coverage`: el
  `## Spec` de esta tarea exigía *"debe haber un test"* de la construcción perezosa y el `## Scenarios`
  no lo declaraba. Fija que una config de embeddings inservible **no** puede tumbar `/kb/documents`.
- *El listado de documentos es estable entre páginas* (end-to-end vía HTTP)
- *Los glosarios son documentos de pleno derecho* (end-to-end vía HTTP, con su `uc_id` sintético en la
  ruta de detalle)
- *Abrir un documento inexistente* (end-to-end vía HTTP)
- *La búsqueda devuelve documentos ordenados por relevancia* (end-to-end vía HTTP)

## Provides

- `/kb/search`, `/kb/documents` y `/kb/documents/{uc_id}` sirviendo datos reales: cierra el plan.
- Guardia automatizada contra el próximo drift contrato↔implementación en los schemas de KB.

## Definition of Done

- [x] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [x] Cada escenario del CU que materializa esta tarea tiene al menos un test (camino feliz + bordes/errores)
- [x] Todos los tests en verde (`make test`, sin regresión sobre los 1064 salvo los del stub borrado, contabilizados)
- [x] `grep -rn "StubVectorStore" app/ tests/` no devuelve nada
- [x] Spec cumplida; lo declarado en `Provides` queda realmente disponible
- [x] Lint / format / typecheck OK (`ruff`, `mypy --strict`)
- [x] Gate de mutation testing superado (`make mutation`, cosmic-ray `break: 80`) sobre los ficheros tocados
- [x] **Gate `sdd-lint` superado** — tras `mutation`, antes de `fact-checker`
- [x] Gate de `fact-checker` superado — antes de commit/resumen
- [x] **SDD** — sin cambios de spec/CU (los fijó `-01`); declararlo así en el session log
- [x] Documentación actualizada — tres capas:
  - [x] **Docstrings** — `get_vector_store`, `routers/kb.py`, y los que mencionaban el stub
  - [x] **Doc técnica** — cierre del plan; nota retro (estimación vs real, sorpresas)
  - [x] **Histórico** — session log en `.claude/context/backend/backend-kb-retriever-07.md`

> ⚠️ **No solapar `pytest` con `cosmic-ray exec`**.
> Requiere la DB: `docker compose -f backend/docker-compose.yml up -d db`.
> Última tarea del plan: al cerrarla, mover el plan a `completed/` y abrir PR a `main`.
