---
id: frontend-helpdesk-core-07
package: frontend
plan: helpdesk-core
status: done
priority: 2
depends_on: [frontend-helpdesk-core-06, backend-skeleton-foundation-03, backend-skeleton-foundation-06]
estimate: 4h
actual: 1.2h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# Bandeja de tickets

## Description

La lista/inbox de tickets (TanStack Table): filtros por estado/tenant/assignee/tag/dominio, búsqueda,
paginación con **orden determinista**, e **indicadores de SLA** (vencido/inminente). Respeta tenant y capacidades.

## Spec

- Tabla con columnas (asunto, estado, prioridad, dominio, assignee, SLA, actualizado); orden por defecto `updated desc`.
- Filtros combinables (estado/tenant/assignee/tag/dominio) + búsqueda; paginación server-driven, orden estable.
- Indicador de SLA por fila: normal / **inminente** / **vencido** (según `sla_due`).
- Estados **empty** (sin resultados) / **loading** / **error** (envelope).

## Fuera de alcance

- Alta (08), detalle (09+). Cómputo de SLA (backend); aquí solo indicador visual.

## Scenarios (Gherkin)

```gherkin
Feature: Bandeja de tickets

  Scenario: Listado ordenado y paginado de forma determinista
    Given una bandeja con más tickets que una página
    When se carga la primera página
    Then los tickets se muestran ordenados por actualización descendente de forma estable

  Scenario: Filtro por estado
    Given una bandeja con tickets en varios estados
    When se filtra por estado "pendiente"
    Then solo se muestran los tickets pendientes

  Scenario: Indicador de SLA vencido
    Given un ticket cuyo SLA ha vencido
    When aparece en la bandeja
    Then su indicador de SLA se muestra como vencido

  Scenario: Bandeja sin resultados
    Given un filtro que no coincide con ningún ticket
    When se aplica
    Then se muestra el estado vacío con una acción para limpiar filtros
```

## Refuerzos (scenario-coverage)

```gherkin
Feature: Refuerzos bandeja

  Scenario: Fallo al cargar la bandeja
    Given un servidor que responde con un error de envelope
    When se abre la bandeja
    Then se muestra el estado de error con una acción de reintento

  Scenario: Un cliente no puede ampliar el alcance a otro tenant
    Given una usuaria cliente
    When manipula el enlace para pedir tickets de otro tenant
    Then solo se listan los tickets de su propio tenant

  Scenario: Página fuera de rango
    Given una bandeja con varias páginas
    When se solicita una página posterior a la última
    Then se muestra la última página válida (o el estado vacío) sin error
```

## Provides

- Página de bandeja + hooks de listado/filtros. 08/09 enlazan desde aquí; el patrón de tabla lo reusa admin (17).

## Definition of Done

- [x] Tests ANTES (TDD); cada escenario con ≥1 test (orden, filtro, SLA vencido, empty, error+retry, aislamiento tenant, página fuera de rango).
- [x] Orden determinista (`-updated_at`) + paginación estable; indicadores SLA (none/normal/imminent/overdue); filtro por estado. *(búsqueda/tag/priority-domain-assignee UI diferidos — gap de contrato / follow-up; ver session log)*
- [x] Lint + typecheck OK; gate de mutation 98.04% (break 80); estados empty/loading/error + a11y de tabla (`aria-label`, `scope`, live-regions).
- [x] `Provides` disponible (bandeja + hooks de listado/filtros); `fact-checker` (9/10 VERIFICADO, INCORRECTO de conteo corregido); docs 3 capas (TSDoc + specs + session log).
