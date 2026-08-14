---
id: frontend-helpdesk-core-12
package: frontend
plan: helpdesk-core
status: done
priority: 3
depends_on: [frontend-helpdesk-core-09]
estimate: 3h
actual: 0.9h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# Ticket — SLA + timeline de actividad

## Description

Indicador de SLA en el detalle (restante/vencido) y el **timeline de actividad** (auditoría): transiciones,
asignaciones, mensajes, decisiones de aprobación — en orden.

## Spec

- Indicador de SLA (restante / inminente / vencido) coherente con la bandeja (07).
- Timeline de actividad desde el audit/actividad del ticket (evento, actor, fecha), orden cronológico.
- Estados loading / empty (sin actividad) / error.

## Fuera de alcance

- Cómputo/escalado de SLA (backend, tarea 18 del backend). Edición de la actividad.

## Scenarios (Gherkin)

```gherkin
Feature: SLA y actividad del ticket

  Scenario: SLA restante
    Given un ticket con SLA aún no vencido
    When se abre el detalle
    Then se muestra el tiempo restante de SLA

  Scenario: SLA vencido
    Given un ticket con SLA vencido
    When se abre el detalle
    Then el indicador de SLA se muestra como vencido

  Scenario: Timeline en orden
    Given un ticket con varias acciones registradas
    When se abre el timeline
    Then los eventos se muestran en orden cronológico con su actor
```

## Provides

- Indicador SLA + timeline en el detalle.

## Definition of Done

- [x] Tests ANTES (TDD); cada escenario con ≥1 test (SLA restante/vencido/sin-SLA, orden del timeline, vacío).
- [x] Indicador SLA coherente con la bandeja (reusa `SlaBadge`/`slaLevel`); timeline ordenado + respeta visibilidad.
- [x] Lint + typecheck OK; gate de mutation 100% (break 80); estados loading/empty + a11y (`<time>`, `<ol>`, `role=status`).
- [x] `Provides` disponible (SLA + timeline en el detalle); `fact-checker` 10/10 VERIFICADO; docs 3 capas + session log. *(eventos de transición/asignación en timeline: pendientes de endpoint de actividad backend)*
