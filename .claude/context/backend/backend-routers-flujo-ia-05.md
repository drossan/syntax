# Session log — backend-routers-flujo-ia-05

Tarea: `AnalyticsRepository` (agregados SQL) + función suelta `analytics.summary()` + router
`analytics.py` + FR nueva en `spec.md` (sin CU dedicado, decisión del owner). Última tarea del plan
`routers-flujo-ia` (depends_on: 01, 02 — ambas ya `done`).

## Entradas

- 2026-08-20 — Arranque. Tarea movida a `active/`. Continúa en la misma rama `plan/backend/
  routers-flujo-ia` (tareas 01/02/03/04 ya cerradas y commiteadas).
- 2026-08-20 — Cierre. Última tarea del plan (5/5).

## Resumen

TDD completo. Orden real: (1) FR-041 en `spec.md` (sin CU dedicado, decisión del owner); (2)
`AnalyticsSummary` (entidad de dominio, nueva) + `AnalyticsRepository` (puerto, recortado a
`summary()`) + `app/domain/services/analytics.py` (función suelta, sin clase); (3)
`SqlAlchemyAnalyticsRepository` (agregados 100% SQL: `GROUP BY` para tickets por status, `COUNT`
filtrado para approvals pending y SLA breaches, `AVG` para confidence media); (4)
`get_analytics_repository` en `deps.py`; (5) router `analytics.py` + schema + `main.py`.

## Decisiones técnicas + porqué

- **`tickets_by_status` rellenado en Python, no en SQL**: `GROUP BY` de Postgres solo devuelve las
  claves con al menos una fila — rellenar las 6 claves de `TicketStatus` a `0` de antemano
  (`{status.value: 0 for status in TicketStatus}`) y sobrescribir con los resultados reales evita que
  el consumidor trate una clave ausente como caso especial (decisión del owner, ya fijada en el plan).
- **`AVG(confidence) IS NOT NULL` se propaga tal cual desde Postgres**: sin filas, `AVG` de Postgres ya
  devuelve `NULL` — no hace falta ningún `if`/división manual para evitar `NaN` o división por cero,
  el propio SQL ya da la semántica correcta.
- **Frontera "sla_due exactamente ahora" testeada a nivel de repositorio, no HTTP**: un test HTTP no
  puede fijar `sla_due` al mismo instante exacto que la query de resumen usará (dos transacciones
  distintas, con latencia real entre inserción y consulta — cualquier `datetime.now(UTC)` de Python
  queda ligeramente en el pasado respecto al `now()` de Postgres de la query posterior, así que SIEMPRE
  cuenta como breach, dando un falso positivo determinista). Solución: capturar `SELECT now()` de
  POSTGRES y usarlo como `sla_due` dentro de la MISMA transacción que la consulta de `summary()` (sin
  `commit()` intermedio) — Postgres cachea `now()` por transacción, así que ambas lecturas ven
  literalmente el mismo valor, haciendo `sla_due < now()` determinísticamente `False`.
- **Refuerzo de mutation testing en el adaptador** (27.59% → 10.34%, survivors reales sobre
  `approval_scope`/`agent_run_scope` sin aislamiento por tenant probado y `approvals_pending` con
  conteos 1+1 que no distinguían `==` de `!=`): añadidos 2 tests con IDs deterministas (bajo/medio/alto,
  mismo patrón que tareas anteriores) para `approvals_pending`/`avg_confidence`, y ampliado el test de
  status a 2 pending + 1 rejected para que la inversión del operador cambie el conteo observable.

## Tests corridos + resultado

- `tests/test_analytics_service.py` (nuevo, 2 tests): passthrough delega en el repo con el `tenant_id`
  dado (incl. `None`).
- `tests/test_repositories_analytics.py` (nuevo, 13 tests): sin datos (ceros + `null`), las 6 claves
  siempre presentes, `approvals_pending` solo cuenta `pending` (+ aislamiento por tenant con IDs
  deterministas), `avg_confidence` ignora runs sin confidence (+ aislamiento por tenant), `sla_breaches`
  cuenta vencidos abiertos, excluye `null`/futuro/resueltos-cerrados, frontera exacta (`now()` de
  Postgres en la misma transacción), aislamiento/agregación por tenant.
- `tests/test_router_analytics.py` (nuevo, 7 tests): los 9 escenarios Gherkin de la tarea vía HTTP real
  (el de frontera exacta se cubre a nivel de repo, ver Decisiones) — resumen con datos reales, sin
  datos, aislamiento tenant vs agregación global, las 6 claves siempre, ticket resuelto con SLA vencido
  no cuenta, 403 sin capacidad.
- Suite completa del backend (`pytest`): **749 tests, verde** (baseline 727 + 22 nuevos).
- `ruff check .`/`ruff format --check .`: OK. `mypy app` (strict): `Success: no issues found in 134
  source files`.
- Mutation (`cosmic-ray`, `--fail-over 20`):
  - `app/infra/db/repositories/analytics.py`: primera pasada **27.59%** → FALLA → reforzado (ver
    Decisiones) → **10.34%** (re-confirmado por `fact-checker`: 8.62%) → PASA.
  - `app/domain/services/analytics.py`: **0.00%** → PASA directamente (passthrough sin ramas).
  - `app/api/v1/routers/analytics.py`: **0.00%** → PASA directamente.
  - `app/core/deps.py`: acotado a los 5 test files de routers que lo ejercitan (mismo criterio que
    tareas anteriores para ficheros compartidos): **12.20%** → PASA.
- `/sdd-lint`: sin CU dedicado (decisión del owner, ya documentada en el plan). Verificación mecánica:
  FR-041 presente y bien formada (`grep` de ids `FR-NNN`), sin `[NECESITA ACLARACIÓN`.
- `fact-checker`: **11/11 afirmaciones VERIFICADO**, 0 INCORRECTO, 0 NO VERIFICABLE (incluye
  re-ejecución independiente de los 4 gates de mutation, sin incidentes de mutación sin revertir esta
  vez).

## Docs actualizadas

- `.claude/specs/backend/spec.md`: FR-041 (contrato de agregados de analytics).
- Docstrings de todos los ficheros nuevos (business.py `AnalyticsSummary`, analytics.py puerto/
  servicio/adaptador/router, deps.py, main.py) — el porqué de cada decisión no obvia.
- Este session log.

## Ficheros / commits

- Nuevos: `backend/app/domain/ports/analytics.py`, `backend/app/domain/services/analytics.py`,
  `backend/app/infra/db/repositories/analytics.py`, `backend/app/api/v1/routers/analytics.py`,
  `backend/app/api/v1/schemas/analytics.py`, `backend/tests/test_analytics_service.py`,
  `backend/tests/test_repositories_analytics.py`, `backend/tests/test_router_analytics.py`.
- Tocados: `backend/app/domain/entities/business.py` (`AnalyticsSummary`), `backend/app/core/deps.py`
  (`get_analytics_repository`), `backend/app/infra/db/repositories/__init__.py`, `backend/app/main.py`
  (monta `analytics_router`), `.claude/specs/backend/spec.md` (FR-041).
- `backend/cosmic-ray.toml` (apunta a `app/api/v1/routers/analytics.py`, último módulo mutado).
- Commit: uno solo, `backend-routers-flujo-ia-05: feat(backend): AnalyticsRepository + router
  analytics (FR-041)`.

## Tiempo real

- `estimate: 4h` → real: cercana a la estimación, ampliada por una ronda de refuerzo de mutation
  testing en el adaptador (aislamiento por tenant sin probar en 2 de las 3 queries agregadas) — no
  reveló ningún bug real, solo huecos de test.

## Follow-ups

- Ninguno propio bloqueante. **Esta es la última tarea del plan `routers-flujo-ia` (5/5)** — el plan
  queda listo para cerrarse: mover a `completed/`, retro, PR desde `plan/backend/routers-flujo-ia`
  hacia la rama de integración (`main`, ya que este repo no tiene `dev`).
