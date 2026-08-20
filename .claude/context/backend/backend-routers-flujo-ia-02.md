# Session log — backend-routers-flujo-ia-02

Tarea: `ApprovalRepository.list_pending` reemplazado por `list(tenant_id | None, status, sort, page,
page_size)` (agrega cross-tenant cuando `tenant_id=None`) + adaptador `SqlAlchemyApprovalRepository` +
actualización de `approval_service`/`tests/test_approval_service.py` + router `approvals.py` completo.
Segunda tarea del plan `routers-flujo-ia` (depends_on: —).

## Entradas

- 2026-08-20 — Arranque. Tarea movida a `active/`. Continúa en la misma rama `plan/backend/
  routers-flujo-ia` (tarea 01 ya cerrada y commiteada).
- 2026-08-20 — Cierre.

## Resumen

TDD completo. Orden real: (1) `ApprovalRepository.list_pending` reemplazado por `list(tenant_id |
None, status, sort, page, page_size)` + `APPROVAL_SORT_FIELDS` (whitelist de un único valor literal)
en `app/domain/ports/repositories.py`; (2) `approval_service.list_queue()` (renombrado desde
`list_pending`, delega en el nuevo `list()`) + `tests/test_approval_service.py` actualizado
(`test_list_pending_isolates_by_tenant` → `test_list_queue_isolates_by_tenant` + 2 tests nuevos para
`tenant_id=None` y filtro `status`); (3) `SqlAlchemyApprovalRepository` (nuevo, primer adaptador real
de este puerto) — `list()` con `JOIN` a `ticket`/`agent_run` (`sla_due`/`confidence` no viven en
`approval_task`), `decide_if_pending` como CAS de una sola sentencia `UPDATE...RETURNING`; (4)
`get_approval_service` en `deps.py`; (5) router `approvals.py` (4 endpoints) + schemas + `main.py`.

## Decisiones técnicas + porqué

- **`tenant_id: uuid.UUID | None` en el puerto/adaptador/servicio**, no solo en el router: la garantía
  "Soporte ve todas las aprobaciones" tiene que ser real en la query (`WHERE tenant_id = :t` se omite
  del todo, no se sustituye por un `IN (...)` de todos los tenants), no un parche de presentación.
- **`decide_if_pending` como adaptador real por primera vez** (antes solo fakes en `domain-services`):
  mismo patrón que `rotate_if_active` de `refresh_session.py` — `UPDATE...WHERE status='pending'...
  RETURNING` en una sola sentencia, sin `get`+`if`+`update`. Sin este CAS real, la doble-decisión en
  carrera (FR-028/RN-2 de CU-BE-06) no tendría garantía real, solo la de los fakes de test.
- **Bug real de mi propio test, no del código de producción**: mi primer intento de test de "Soporte en
  ámbito global ve todo" fallaba porque el helper de siembra asignaba el rol con `tenant_id=tenant.id`
  en vez de `tenant_id=None` para una capacidad `scope='global'` — la fila `user_role.tenant_id` sigue
  siendo lo que `effective_capabilities` usa para acotar, independientemente del `scope` propio de la
  capacidad. Detectado comparando contra el patrón ya probado de `test_router_admin.py::
  _grant_capability` (que sí distingue `tenant_id=None` para `scope=global`), reproducido con un script
  aislado contra Postgres directo (confirmó que el repo/RLS funcionaban bien) antes de corregir el test.
- **Mutation testing de `deps.py` esta vez sin incidentes**: aplicado el protocolo aprendido en la tarea
  01 (releer el fichero completo tras cada corrida antes de continuar) — las 4 corridas de esta tarea
  dejaron el fichero íntegro, confirmado también por el `fact-checker` de forma independiente.

## Tests corridos + resultado

- `tests/test_approval_service.py` (ampliado): `test_list_queue_isolates_by_tenant` (renombrado),
  `test_list_queue_with_tenant_id_none_aggregates_cross_tenant` (nuevo), `test_list_queue_with_status_
  filters_by_that_status_instead_of_pending` (nuevo).
- `tests/test_repositories_approval.py` (nuevo, 11 tests): CRUD, filtro por status/sin status
  (default pending), orden `sla_due,confidence`, aislamiento/agregación por tenant, paginación (25→20),
  CAS de `decide_if_pending` (aplica/ya-decidida/no-existe/con final_body).
- `tests/test_router_approvals.py` (nuevo, 14 tests): los 11 escenarios Gherkin de la tarea vía HTTP
  real (Postgres + RLS reales) — listar sin filtro/con filtro, sort no soportado (422), aislamiento
  tenant vs agregación global (RLS real con `bypass_rls`), approve/edit/reject (200, 422 sin
  final_body/human_note, 409 doble decisión, 404 id inexistente), 403 sin capacidad.
- Suite completa del backend (`pytest`): **691 tests, verde** (baseline 664 + 27 nuevos/ampliados).
- `ruff check .`/`ruff format --check .`: OK. `mypy app` (strict): `Success: no issues found in 128
  source files`.
- Mutation (`cosmic-ray`, `--fail-over 20`, `session.sqlite` borrada entre corridas, fichero mutado
  releído completo tras cada corrida — sin incidentes esta vez):
  - `app/infra/db/repositories/approval.py`: **13.91%** (re-confirmado por `fact-checker`: 14.57%,
    pequeña variación entre corridas por el orden no determinista de algunos mutantes, ambas ≤20%) →
    PASA directamente.
  - `app/api/v1/routers/approvals.py`: **10.53%** → PASA directamente.
  - `app/domain/services/approval_service.py`: **7.23%** → PASA directamente.
  - `app/core/deps.py`: acotado a `test_router_approvals.py`+`test_router_agent.py`+
    `test_router_auth.py` juntos (mismo criterio que la tarea 01 para ficheros compartidos): **12.20%**
    → PASA.
- `/sdd-lint`: sin cambios de CU en esta tarea (CU-BE-06 ya cubría approve/edit/reject/idempotencia).
  Sincronía verificada: `rbac.md` ya declara `approval.decide` exclusivamente `global` (catálogo §2 +
  invariante de roles custom §4), coherente con lo implementado — sin gate semántico completo por no
  haber artefacto SDD nuevo que auditar.
- `fact-checker`: **12/12 afirmaciones VERIFICADO**, 0 INCORRECTO, 0 NO VERIFICABLE (incluye
  re-ejecución independiente de los 4 gates de mutation, sin corrupción detectada).

## Docs actualizadas

- Docstrings de todos los ficheros nuevos/tocados (repositories.py, approval_service.py, approval.py
  adaptador, deps.py, approvals.py router) — el porqué de cada decisión no obvia.
- Este session log.

## Ficheros / commits

- Nuevos: `backend/app/infra/db/repositories/approval.py`, `backend/app/api/v1/routers/approvals.py`,
  `backend/app/api/v1/schemas/approvals.py`, `backend/tests/test_repositories_approval.py`,
  `backend/tests/test_router_approvals.py`.
- Tocados: `backend/app/domain/ports/repositories.py` (`ApprovalRepository.list` + `APPROVAL_SORT_
  FIELDS`), `backend/app/domain/services/approval_service.py` (`list_queue`), `backend/app/core/
  deps.py` (`get_approval_service`), `backend/app/infra/db/repositories/__init__.py`,
  `backend/app/main.py` (monta `approvals_router`), `backend/tests/test_approval_service.py`.
- `backend/cosmic-ray.toml` (apunta a `app/api/v1/routers/approvals.py`, último módulo mutado).
- Commit: uno solo, `backend-routers-flujo-ia-02: feat(backend): ApprovalRepository ampliado + CAS
  real + router approvals`.

## Tiempo real

- `estimate: 4h` → real: cercana a la estimación, ampliada por el diagnóstico del bug de mi propio
  helper de test (siembra de capacidad global) — no fue una duda de diseño, fue una comparación directa
  contra un patrón ya probado en el propio repo (`test_router_admin.py`) la que lo resolvió rápido.

## Follow-ups

- Ninguno propio bloqueante. `backend-routers-flujo-ia-03` (notificaciones in-app) es la siguiente
  tarea recomendada — sin `depends_on` declarado, puede arrancar de inmediato.
