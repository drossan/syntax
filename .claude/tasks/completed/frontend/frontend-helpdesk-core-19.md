---
id: frontend-helpdesk-core-19
package: frontend
plan: helpdesk-core
status: done
priority: 3
depends_on: [frontend-helpdesk-core-07, frontend-helpdesk-core-13]
estimate: 3h
actual: 0.9h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# Dashboard / analytics

## Description

Panel de métricas del helpdesk (`GET /analytics/summary`): volumen de tickets, % resueltos por IA,
pendientes de aprobación, SLA en riesgo. Acotado por tenant/rol.

## Spec

- Tarjetas de métricas + gráficas básicas; datos de `/analytics/summary`, filtrables por rango.
- Acotación: Soporte ve agregado global (o por tenant seleccionado); cliente ve solo su tenant.
- Estados loading / empty (sin datos) / error.

## Fuera de alcance

- Analítica avanzada / export. Cómputo (backend).

## Scenarios (Gherkin)

```gherkin
Feature: Dashboard

  Scenario: Métricas del tenant para un cliente
    Given una usuaria cliente
    When abre el dashboard
    Then ve métricas acotadas a su propio tenant

  Scenario: Soporte ve el agregado del tenant seleccionado
    Given un agente de soporte con un tenant seleccionado
    When abre el dashboard
    Then ve las métricas de ese tenant

  Scenario: Sin datos
    Given un tenant sin actividad
    When abre el dashboard
    Then se muestra el estado vacío
```

## Provides

- Página de dashboard con métricas.

## Definition of Done

- [x] Tests ANTES (TDD): métricas del summary (server-scoped, sirve cliente y soporte), estado vacío, error+retry, guards de página.
- [x] Tarjetas de métricas + barras por estado (accesibles, sin lib nueva); acotación por tenant/rol server-side; queryKey por tenant activo.
- [x] Lint + typecheck OK; gate de mutation 88.46% (break 80); estados loading/empty/error + a11y (grupos etiquetados, live-region).
- [x] `Provides` disponible; `fact-checker` 10/10 VERIFICADO; docs 3 capas + session log.
