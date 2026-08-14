---
id: frontend-helpdesk-core-13
package: frontend
plan: helpdesk-core
status: done
priority: 2
depends_on: [frontend-helpdesk-core-09, backend-skeleton-foundation-05, backend-skeleton-foundation-06]
estimate: 3h
actual: 0.9h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# Cola de aprobaciones

## Description

La cola de aprobaciones (solo Soporte de Syntax): tickets con draft IA pendiente de aprobación, **ordenados
por SLA/confianza**. Punto de entrada al ciclo de draft (14) y decisiones (15).

## Spec

- Lista de `ApprovalTask` pendientes con orden por `sla_due`/confianza; solo con capacidad `approval.decide`.
- Cada ítem: ticket, dominio, confianza del draft, SLA; enlace al detalle/decisión.
- Estados empty (nada pendiente) / loading / error. El cliente **no** ve esta cola.

## Fuera de alcance

- Ciclo de generación del draft (14). Acciones de decisión (15).

## Scenarios (Gherkin)

```gherkin
Feature: Cola de aprobaciones

  Scenario: Orden por prioridad de la cola
    Given varias aprobaciones pendientes con distinto SLA y confianza
    When se abre la cola
    Then se muestran ordenadas según la política (SLA/confianza)

  Scenario: El cliente no accede a la cola
    Given una usuaria cliente
    When intenta acceder a la cola de aprobaciones
    Then se le deniega el acceso

  Scenario: Cola vacía
    Given ninguna aprobación pendiente
    When se abre la cola
    Then se muestra el estado vacío
```

## Refuerzos (scenario-coverage)

```gherkin
Feature: Refuerzos cola (concurrencia + orden)

  Scenario: Una aprobación resuelta por otro agente desaparece de la cola
    Given dos agentes viendo la misma cola
    When uno resuelve una aprobación
    Then esa aprobación deja de aparecer en la cola del otro tras la actualización

  Scenario: Desempate estable en la cola
    Given dos aprobaciones con el mismo SLA y la misma confianza
    When se abre la cola
    Then su orden relativo es determinista y estable entre recargas
```

## Provides

- Página/cola de aprobaciones (Soporte). 14/15 operan sobre sus ítems.

## Definition of Done

- [x] Tests ANTES (TDD); cada escenario con ≥1 test (orden, desempate estable, acceso denegado a cliente, empty, error, resuelta-desaparece).
- [x] Orden por SLA/confianza (server-driven; el cliente no re-ordena); gate por capacidad `approval.decide`.
- [x] Lint + typecheck OK; gate de mutation 93.33% (break 80); estados loading/error/empty + a11y.
- [x] `Provides` disponible; `fact-checker` 9/9 VERIFICADO; docs 3 capas + session log. *(enriquecido confianza/SLA por ítem diferido — gap de contrato)*
