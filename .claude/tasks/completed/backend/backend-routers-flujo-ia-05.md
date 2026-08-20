---
id: backend-routers-flujo-ia-05
package: backend
plan: routers-flujo-ia
status: done
priority: 3
depends_on: [backend-routers-flujo-ia-01, backend-routers-flujo-ia-02]
estimate: 4h
actual: 4h
issue:
created: 2026-08-20
updated: 2026-08-20
---

# AnalyticsRepository (agregados SQL) + FR nueva en spec.md + router analytics

## Description

`GET /analytics/summary` no tiene FR ni CU hoy (hueco real, confirmado por grep sobre `spec.md`). Decisión
del owner (`grilling` de este plan): se cierra con **solo una FR nueva** en `spec.md`, sin CU dedicado —
es una lectura agregada de un solo paso, sin actores ni flujos alternativos que justifiquen un Cockburn
completo. Depende de las tareas 01/02 porque agrega sobre `agent_run`/`approval_task`, cuyos adaptadores
nacen ahí.

## Spec

- **`.claude/specs/backend/spec.md`**: nueva FR (numeración siguiente a FR-038) — "Cuando un sujeto con
  `analytics.read` consulta el resumen, el sistema DEBERÁ devolver, acotado a su ámbito (tenant o
  cross-tenant si `global`): tickets agrupados por `status` (**las 6 claves de `TicketStatus` siempre
  presentes**, `0` donde no hay datos — `scenario-coverage`, decisión del owner: evita que el consumidor
  trate una clave ausente como caso especial), nº de `ApprovalTask` `pending`, confianza media de
  `AgentRun.confidence` (`null` si no hay runs con confianza), y nº de tickets con SLA vencido (`sla_due <
  now()` **estricto** y no `resolved`/`closed`; un `sla_due` `NULL` nunca cuenta)".
- **`app/domain/ports/analytics.py`** (nuevo): `AnalyticsRepository.summary(tenant_id: uuid.UUID | None)
  -> AnalyticsSummary` (`tenant_id=None` = cross-tenant, ámbito `global`).
- **`app/infra/db/repositories/analytics.py`** (nuevo): `SqlAlchemyAnalyticsRepository` — una query SQL
  por agregado (no en Python): `COUNT(*) ... GROUP BY status` (tickets) **rellenado en Python con las 6
  claves de `TicketStatus` a `0`** tras el `GROUP BY` (el `GROUP BY` puro solo devuelve los status con al
  menos un ticket); `COUNT(*) WHERE status='pending'` (approval_task); `AVG(confidence) WHERE confidence
  IS NOT NULL` (agent_run); `COUNT(*) WHERE sla_due < now() AND status NOT IN ('resolved','closed')`
  (tickets — `sla_due IS NULL` ya queda fuera por cómo Postgres evalúa `NULL < now()`, sin `AND sla_due IS
  NOT NULL` explícito redundante). Sin filas → cada contador es `0`, `avg_confidence` es `None` (nunca
  `NaN` ni división por cero — `AVG` de Postgres ya devuelve `NULL` sobre cero filas, se propaga tal cual).
- **`app/domain/services/analytics.py`** (nuevo, **función suelta**, sin clase — mismo patrón que
  `classification.classify()`): `async def summary(repo: AnalyticsRepository, tenant_id: uuid.UUID |
  None) -> AnalyticsSummary` — passthrough directo, sin lógica adicional (el agregado ya es correcto en
  SQL).
- **Router `app/api/v1/routers/analytics.py`**: `GET /analytics/summary` (capacidad `analytics.read`) →
  `tenant_id = subject.tenant_id` en ámbito `tenant`, `None` en ámbito `global` (vía `get_tenant_context`,
  mismo patrón que `/admin/settings`) → `summary(repo, tenant_id)`, 200 + `AnalyticsSummary`.
- **`app/api/v1/schemas/analytics.py`** (nuevo): `AnalyticsSummary` (espejo **literal** de
  `api-contract.yaml`, línea 1293-1301 — nombre de campo verificado: `approvals_pending`, **no**
  `pending_approvals`): `tickets_by_status: dict[str, int]`, `approvals_pending: int`, `avg_confidence:
  float | None`, `sla_breaches: int`.
- **`app/core/deps.py`**: `get_analytics_repository`.
- **`app/main.py`**: registra `analytics_router` bajo `/api/v1`.

## Fuera de alcance

- CU-BE dedicado para analytics — decisión del owner, solo FR (ver plan).
- Cualquier métrica no listada en el contrato (`AnalyticsSummary`) — no se inventan campos nuevos.
- Cacheo/materialización de los agregados (rendimiento) — no pedido, no hay volumen real todavía.

## Scenarios (Gherkin)

**SDD**: sin CU dedicado (decisión del owner) — el Gherkin vive en esta tarea, la FR nueva en `spec.md` es
la fuente EARS.

```gherkin
Feature: resumen de analytics agregado por tenant

  Scenario: resumen con datos reales
    Given tickets en varios status, ApprovalTask pendientes, AgentRun con confidence y un ticket con SLA vencido
    When un subject con analytics.read pide GET /analytics/summary
    Then recibe los tickets agrupados por status, el nº de aprobaciones pendientes, la confianza media y el nº de breaches de SLA

  Scenario: resumen sin ningún dato
    Given un tenant sin tickets/runs/aprobaciones
    When pide GET /analytics/summary
    Then todos los contadores son 0 y avg_confidence es null (nunca un error)

  Scenario: aislamiento por tenant
    Given tickets/runs de dos tenants distintos
    When un subject en ámbito tenant pide GET /analytics/summary
    Then los agregados solo cuentan su propio tenant

  Scenario: ámbito global agrega cross-tenant
    Given tickets/runs de varios tenants y un subject con analytics.read en ámbito global
    When pide GET /analytics/summary
    Then los agregados suman todos los tenants

  Scenario: tickets_by_status incluye siempre las 6 claves
    Given un tenant con tickets solo en 2 de los 6 status posibles
    When pide GET /analytics/summary
    Then tickets_by_status trae las 6 claves, con 0 en los status sin tickets

  Scenario: un ticket con sla_due exactamente ahora no cuenta como breach
    Given un ticket cuyo sla_due coincide exactamente con el instante de la consulta
    When se calcula sla_breaches
    Then ese ticket no cuenta (la comparación es estrictamente menor que ahora)

  Scenario: un ticket sin sla_due nunca cuenta como breach
    Given un ticket con sla_due=null
    When se calcula sla_breaches
    Then ese ticket no cuenta

  Scenario: un ticket resuelto con SLA vencido no cuenta como breach
    Given un ticket status=resolved con sla_due en el pasado
    When se calcula sla_breaches
    Then ese ticket no cuenta

  Scenario: un subject sin analytics.read no puede pedir el resumen
    Given un subject sin la capacidad analytics.read
    When pide GET /analytics/summary
    Then recibe 403
```

## Provides

—

## Definition of Done

- [x] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [x] Cada escenario Gherkin tiene al menos un test (camino feliz + bordes/errores)
- [x] Todos los tests en verde
- [x] Spec cumplida; lo declarado en `Provides` queda realmente disponible para las tareas dependientes
- [x] Lint / format / typecheck OK
- [x] Gate de mutation testing superado (`cosmic-ray`, `break:80`) — `analytics.py` (servicio) 0.00%
  directo (passthrough sin ramas); el resto sí entró en el gate con refuerzo
- [x] Gate `sdd-lint` superado (FR-041 en `spec.md` presente y trazable; "sin CU" declarado, no un hueco
  silencioso)
- [x] Gate `fact-checker` superado (11/11 afirmaciones VERIFICADO)
- [x] Documentación — TSDoc + doc técnica (`spec.md`) + session log
- [x] Docs de dev/usuario donde aplique (N/A — sin superficie de usuario final nueva, solo API)
