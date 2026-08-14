---
id: frontend-helpdesk-core-21
package: frontend
plan: helpdesk-core
status: done
priority: 3
depends_on: [frontend-helpdesk-core-15, frontend-helpdesk-core-05, frontend-helpdesk-core-20]
estimate: 3h
actual: 1.7h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# e2e Playwright — smokes del happy-path crítico

## Description

Suite e2e **acotada** (design-review C5): smokes del camino dorado contra la app mockeada (MSW), para
cubrir el cableado full-app y comportamientos de navegador (cookies, foco, navegación dura) que RTL+MSW no
cubren. **No** e2e de flujos no-críticos (los cubre la integración por-feature).

## Spec

- e2e 1 (happy path): login → crear ticket → generar draft IA → aprobar → ver respuesta publicada.
- e2e 2 (tenant): Soporte cambia de tenant y ve datos del tenant seleccionado.
- Corre en CI contra MSW; fuera del gate de mutation por tarea. Estable (sin flaky por orden — depende de 20).

## Fuera de alcance

- e2e de KB/admin/roles/dashboard (cubiertos por RTL+MSW). e2e contra backend real (llegará con el backend).

## Scenarios (Gherkin)

```gherkin
Feature: Smokes e2e del camino crítico

  Scenario: Camino dorado login → ticket → draft → aprobación
    Given un agente de soporte autenticado
    When crea un ticket, genera el draft IA y lo aprueba
    Then la respuesta aprobada queda publicada como mensaje público del ticket

  Scenario: Cambio de tenant por Soporte
    Given un agente de soporte con ámbito global
    When cambia de tenant
    Then la bandeja muestra los tickets del tenant seleccionado
```

## Provides

- Suite e2e de smokes críticos en Playwright. Cierra el plan frontend.

## Definition of Done

- [x] Los dos smokes pasan contra MSW (login→ticket→draft→aprobación; tenant-switch) — `pnpm e2e` → 2 passed (verificado 2×).
- [x] Solo los 2 smokes críticos; navegación client-side para estado MSW estable (sin flakiness de orden).
- [x] Lint + typecheck OK (specs e2e incluidos); webServer con MSW → corre en CI. Unit suite intacta (274/63).
- [x] `fact-checker` 10/10 VERIFICADO; docs: cómo correr el e2e + session log (arriba). *(sin gate de mutación: tarea e2e por diseño)*
