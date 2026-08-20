# Session log — backend-routers-flujo-ia-01

Tarea: migración (índice único parcial `agent_run`) + `AgentRunner.trigger()` (puerto) +
`StubAgentRunner` + `AgentRunRepository.get_active_for_ticket` + adaptador
`SqlAlchemyAgentRunRepository` (CAS vía `IntegrityError`→`Conflict`) + puerto `RateLimiter` +
`InMemoryRateLimiter` + error `RateLimited`→429 + elimina `ai_draft_max_per_ticket` + `agent_service`
(rate-limit → 409 si hay run en curso → trigger; get con scope por tenant) + capacidad compuesta
`agent.trigger` OR `ticket.read` en `deps.py` + router `agent.py` completo. Primera tarea del plan
`routers-flujo-ia` (depends_on: —).

## Entradas

- 2026-08-20 — Arranque. Plan `routers-flujo-ia` movido a `active/`. Precondición: `plan/backend/
  routers-core` (9/9 tareas, ya completado) mergeado a `main` (fast-forward, autorizado por el owner) —
  no había rama `dev`, `main` es la rama de integración real de este repo. Rama nueva `plan/backend/
  routers-flujo-ia` creada desde `main`. Tarea movida a `active/`.
- 2026-08-20 — Cierre.

## Resumen

TDD completo (Red→Green→Refactor por módulo). Orden real de implementación: (1) `RateLimited`
(`app/domain/errors.py`) + puerto `RateLimiter` + mapeo 429 (`app/api/errors.py`) + `Settings.
ai_draft_rate_limit_per_minute` (sustituye `ai_draft_max_per_ticket`, eliminado junto con su test); (2)
`AgentRunner.trigger()` en el puerto + `AgentRunRepository.get_active_for_ticket` en
`app/domain/ports/repositories.py`; (3) `InMemoryRateLimiter` (ventana fija 60s, `Clock` inyectable
para tests deterministas); (4) `StubAgentRunner` — **diseño corregido a mitad de tarea** (ver
Decisiones); (5) migración `0003_agent_run_active_index.py` (índice único parcial
`ix_agent_run_active_per_ticket`) + `Index` equivalente en el modelo ORM (para no divergir del gate
`test_models_do_not_drift_from_schema`); (6) `SqlAlchemyAgentRunRepository` (CAS real:
`IntegrityError`→`Conflict` en `add()`); (7) `agent_service.py` (orden de chequeos barato→caro); (8)
`deps.py`: `require_any_capability` (refactor interno de `get_tenant_context` sobre una función común
`_scope_for_any_capability`, sin cambiar su comportamiento externo) + `get_agent_service` (rate-limiter
singleton de proceso vía `lru_cache` parametrizado por `limit`); (9) router `agent.py` + schema +
`main.py`; (10) CU-BE-06 ampliado con los 2 escenarios de disparo (409/429) + RN-4/RN-5 + FR-040 nueva
en `spec.md` (cierre del AVISO de trazabilidad de `sdd-lint`).

## Decisiones técnicas + porqué

- **`StubAgentRunner.trigger()` persiste vía `AgentRunRepository.add()`, no solo construye el
  `AgentRun` en memoria** — corrección sobre mi propia implementación inicial (más fiel a la redacción
  del plan de alto nivel que a la Spec de la tarea, ambas con matices distintos): la Spec de la tarea
  dice literalmente que el paso 6 de `agent_service.trigger()` ES `agent_runner.trigger(...)` y que "si
  el adaptador lanza `Conflict` (índice único parcial), se propaga tal cual" — no hay un paso separado
  `agent_runs.add(...)` en `agent_service`. Esto solo tiene sentido si `AgentRunner.trigger()` (el
  adaptador) es quien persiste, reflejando que en el grafo real (15/16) arrancar el run y crear su fila
  son el mismo acto atómico conceptual. Detectado por el primer test de integración del router (`GET`
  tras `POST` no encontraba la fila) — no fue una suposición sin verificar, se corrigió tras un fallo
  real reproducido. `StubAgentRunner` pasó a recibir `AgentRunRepository` por constructor;
  `get_agent_service` comparte la MISMA instancia de `SqlAlchemyAgentRunRepository` entre `AgentService`
  y `StubAgentRunner` sobre la misma sesión (sin duplicar).
- **`get_tenant_context` refactorizado internamente (no reescrito) para compartir lógica con
  `require_any_capability`**: ambos delegan en `_scope_for_any_capability(session, subject,
  capabilities: tuple[str, ...])` — con una sola capacidad es el comportamiento exacto de antes (mismo
  test suite de toda la app sigue en verde, sin cambiar la firma pública de `get_tenant_context`).
  Evita duplicar la regla de precedencia de ámbito (`global` gana) en dos sitios.
- **`_rate_limiter_singleton` vía `functools.lru_cache` parametrizado por `limit`** (no un global
  module-level simple como `session.py`): permite que tests con distinto `ai_draft_rate_limit_per_minute`
  obtengan limiters independientes sin reiniciar el proceso, y sigue siendo un singleton real por valor
  de `limit` dentro del mismo proceso (el contador SÍ acumula entre requests, requisito explícito de la
  tarea).
- **Incidente de mutation testing detectado y corregido antes del cierre**: durante el cierre, una
  ejecución de `cosmic-ray` sobre `app/infra/db/repositories/agent_run.py` (probablemente una de mis
  corridas interrumpidas por timeout, o la del subagente `fact-checker` al re-verificar el gate) dejó un
  mutante aplicado en disco sin revertir: `get_active_for_ticket` quedó con `ticket_id != ticket_id` en
  vez de `==`. Lo detectué porque 3 tests de `test_router_agent.py` que antes pasaban empezaron a fallar
  con 409 inesperados al re-ejecutar la suite completa tras el gate de `fact-checker`. Verificado
  reproduciendo el fallo, diagnosticada la causa exacta (`git diff`/lectura completa del fichero,
  comparado contra los demás ficheros mutados — todos los demás estaban intactos), corregido, y
  reverificado con la suite completa (664 tests verdes) + una repetición limpia del gate de mutation
  sobre ese fichero (9.09% supervivencia, igual que antes del incidente). **Lección**: tras cualquier
  corrida de `cosmic-ray` que no termine limpiamente (timeout, proceso movido a segundo plano), hay que
  releer el fichero mutado completo antes de confiar en que se revirtió solo.
- **AVISO de `/sdd-lint` (trazabilidad) resuelto, no solo reconocido**: el subagente semántico detectó
  que los 2 escenarios nuevos de disparo (409/429) no colgaban de ningún FR/RN explícito. En vez de solo
  reconocerlo, se añadió `FR-040` a `spec.md` y `RN-4`/`RN-5` a `CU-BE-06` — coste bajo, cierra el hueco
  real que el propio review señaló.

## Tests corridos + resultado

- `tests/test_domain_errors_and_ports.py`/`tests/test_api_errors.py`/`tests/test_config.py` (ampliados):
  `RateLimited`, mapeo 429, fake `RateLimiter` satisface el protocolo, `ai_draft_rate_limit_per_minute`.
- `tests/test_rate_limiter_in_memory.py` (nuevo, 7 tests): límite exacto aceptado, exceso rechazado sin
  doble consumo, expiración de ventana (incl. frontera exacta a los 60s), aislamiento entre tenants.
- `tests/test_agent_runner_stub.py` (nuevo, 5 tests): persiste vía el repo inyectado, id fresco por
  llamada, confidence/sources sin fijar, propaga `Conflict` del repo tal cual, `resume()` no-op.
- `tests/test_migration_agent_run_active_index.py` (nuevo, 6 tests): índice existe/único/parcial, dos
  runs activos del mismo ticket violan la constraint (queued+queued, queued+running), un run terminal no
  bloquea uno nuevo, dos tickets distintos no interfieren.
- `tests/test_repositories_agent_run.py` (nuevo, 13 tests): CRUD, CAS real de `add()` (`Conflict` vía
  `IntegrityError`), `next_run_seq`/`get_active_for_ticket` con IDs deterministas (bajo/medio/alto) para
  matar mutantes de comparación (`==`→`<=`/`>=`/`is not`) en el filtro `ticket_id` — el mismo patrón que
  detectó/habría detectado el incidente de mutation testing descrito arriba.
- `tests/test_agent_service.py` (nuevo, 11 tests): orden de chequeos (ticket→activo→rate-limit→crear),
  ningún chequeo posterior consume recursos si uno anterior falla, 404/409/429 con las causas correctas.
- `tests/test_router_agent.py` (nuevo, 16 tests): los 15 escenarios Gherkin de la tarea vía HTTP real
  (Postgres + RLS reales, `app_engine`) — incl. dos disparos concurrentes de verdad (`asyncio.gather`,
  máximo un 202) y aislamiento de rate-limit entre tenants con `ai_draft_rate_limit_per_minute`
  parametrizado por test.
- Suite completa del backend (`pytest`): **664 tests, verde**, sin regresiones (baseline: 602).
- `ruff check .`/`ruff format --check .`: OK. `mypy app` (strict): `Success: no issues found in 126
  source files`.
- Mutation (`cosmic-ray`, `--fail-over 20`, cada fichero contra su test dedicado, `session.sqlite`
  borrada entre corridas):
  - `app/infra/rate_limit/in_memory.py`: **6.94%** survival → PASA.
  - `app/infra/db/repositories/agent_run.py`: primera pasada **21.21%** → FALLA (2 mutantes reales sobre
    `next_run_seq`/`get_active_for_ticket` con IDs no distinguibles + 2 sobre `max_seq+1`); reforzado con
    2 tests de IDs deterministas (bajo/medio/alto) → **9.09%** (solo el patrón `except Exception`
    aceptado desde `backend-routers-core-04`) → PASA. Reconfirmado a 9.09% tras corregir el incidente de
    mutation descrito arriba.
  - `app/domain/services/agent_service.py`: **0.00%** → PASA directamente.
  - `app/api/v1/routers/agent.py`: **0.00%** → PASA directamente.
  - `app/core/deps.py`: acotado a `test_router_agent.py` en solitario, **24.39%** (10 survivors, TODOS
    en `get_current_subject`/`_unauthorized`/`oauth2_scheme` — código preexistente de
    `backend-routers-core-05`, no tocado por esta tarea, ya gateado allí a 12.82%); confirmado que con
    `test_router_agent.py`+`test_router_auth.py` juntos baja a **12.20%** → PASA (mismo criterio que
    `backend-routers-core-07`: el patrón de blind-spot de un test-command estrecho sobre un fichero
    compartido no es un hueco nuevo de esta tarea).
  - `StubAgentRunner` (`app/infra/agent_runner/stub.py`): **N/A documentado** — sin ninguna rama
    condicional (`if`/`elif`/`else`), verificado con `grep`.
- `/sdd-lint`: mecánico limpio (sin `[NECESITA ACLARACIÓN`, ids `FR`/`SC` bien formados, enlaces de
  CU-BE-06 resuelven, 8 secciones `##`). Semántico vía subagente fresco: **0 ERROR, 1 AVISO** (EARS
  bien-formado ✓, Gherkin declarativo ✓, coherencia interna ✓; AVISO de trazabilidad de los 2 escenarios
  nuevos sin FR/RN explícito) → **resuelto** con `FR-040` + `RN-4`/`RN-5` (ver Decisiones), no solo
  reconocido.
- `fact-checker`: **19/19 afirmaciones VERIFICADO**, 0 INCORRECTO, 0 NO VERIFICABLE (incluye
  re-ejecución independiente de los 5 gates de mutation).

## Docs actualizadas

- Docstrings de todos los ficheros nuevos/tocados (agent_runner.py, repositories.py, rate_limiter.py,
  agent_run.py adaptador, agent_service.py, deps.py, agent.py router, config.py, errors.py, domain
  errors.py) — el porqué de cada decisión no obvia (ver Decisiones).
- `.claude/specs/backend/casos-de-uso/CU-BE-06-draft-ia-y-aprobacion-hitl.md`: nota en "Disparador",
  extensiones 0a/0b, 2 escenarios Gherkin nuevos, RN-4/RN-5.
- `.claude/specs/backend/spec.md`: FR-040 nueva.
- Este session log.

## Ficheros / commits

- Nuevos: `backend/alembic/versions/0003_agent_run_active_index.py`,
  `backend/app/domain/ports/rate_limiter.py`, `backend/app/domain/services/agent_service.py`,
  `backend/app/infra/agent_runner/__init__.py`, `backend/app/infra/agent_runner/stub.py`,
  `backend/app/infra/rate_limit/__init__.py`, `backend/app/infra/rate_limit/in_memory.py`,
  `backend/app/infra/db/repositories/agent_run.py`, `backend/app/api/v1/routers/agent.py`,
  `backend/app/api/v1/schemas/agent.py`.
- Tocados: `backend/app/domain/errors.py` (`RateLimited`), `backend/app/domain/ports/agent_runner.py`
  (`trigger()`), `backend/app/domain/ports/repositories.py` (`get_active_for_ticket`),
  `backend/app/api/errors.py` (429), `backend/app/core/config.py`
  (`ai_draft_rate_limit_per_minute`, elimina `ai_draft_max_per_ticket`), `backend/app/core/deps.py`
  (`require_any_capability`, `get_agent_service`), `backend/app/infra/db/models/business.py` (índice),
  `backend/app/infra/db/repositories/__init__.py`, `backend/app/main.py` (monta `agent_router`).
- Tests nuevos: `test_rate_limiter_in_memory.py`, `test_agent_runner_stub.py`,
  `test_migration_agent_run_active_index.py`, `test_repositories_agent_run.py`, `test_agent_service.py`,
  `test_router_agent.py`. Tests ampliados: `test_domain_errors_and_ports.py`, `test_api_errors.py`,
  `test_config.py`.
- `backend/cosmic-ray.toml` (apunta a `app/api/v1/routers/agent.py`, último módulo mutado).
- Specs: `.claude/specs/backend/casos-de-uso/CU-BE-06-draft-ia-y-aprobacion-hitl.md`,
  `.claude/specs/backend/spec.md`.
- Commit: uno solo, `backend-routers-flujo-ia-01: feat(backend): AgentRunner.trigger + CAS +
  rate-limit + agent_service + router agent`.

## Tiempo real

- `estimate: 6h` → real: cercana a la estimación, ampliada por (1) la corrección de diseño de
  `StubAgentRunner` a mitad de tarea (detectada por un test de integración, no una revisión de código) y
  (2) el incidente de mutation testing detectado y corregido antes del cierre (~20 min extra de
  diagnóstico + reverificación).

## Follow-ups

- Ninguno propio bloqueante. `backend-routers-flujo-ia-02` (cola de aprobación HITL, `ApprovalRepository`
  ampliado + router `approvals.py`) es la siguiente tarea recomendada — sin `depends_on` declarado sobre
  esta, puede arrancar en paralelo si el owner lo prefiere, aunque el orden natural del plan la sitúa
  después.
- El AVISO de `/sdd-lint` sobre trazabilidad ya se resolvió en esta misma tarea (no queda pendiente).
