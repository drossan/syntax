---
id: frontend-helpdesk-core-09
package: frontend
plan: helpdesk-core
status: done
priority: 2
depends_on: [frontend-helpdesk-core-07, backend-skeleton-foundation-03, backend-skeleton-foundation-06]
estimate: 4h
actual: 1.2h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# Ticket detalle — hilo + visibilidad (lectura)

## Description

Vista de detalle del ticket con el **hilo de conversación** y el **filtro de visibilidad** de mensajes
(`public` para todos; `internal` solo para Syntax con `note.internal.read`). Es la parte de **lectura** del
detalle; las mutaciones y adjuntos/SLA van en 10-12.

## Spec

- Render del hilo ordenado (mensajes públicos + internos según capacidad); metadatos (autor, fecha, `is_ai_draft`).
- **Filtro de visibilidad**: una usuaria cliente **nunca** ve mensajes `internal`; Soporte sí.
- Cabecera del ticket (asunto, estado, prioridad, dominio, assignee) en solo-lectura (mutaciones en 10).
- Estados empty (sin mensajes) / loading / error.

## Fuera de alcance

- Mutaciones estado/prioridad/asignación (10); adjuntos (11); SLA/timeline (12); nota-al-desarrollador (Fase 2).

## Scenarios (Gherkin)

```gherkin
Feature: Detalle de ticket (lectura)

  Scenario: El cliente no ve notas internas
    Given un ticket con un mensaje público y una nota interna
    And una usuaria cliente
    When abre el detalle del ticket
    Then ve el mensaje público y NO ve la nota interna

  Scenario: Soporte ve las notas internas
    Given el mismo ticket
    And un agente de soporte
    When abre el detalle
    Then ve tanto el mensaje público como la nota interna

  Scenario: Hilo en orden cronológico
    Given un ticket con varios mensajes
    When se abre el detalle
    Then los mensajes se muestran en orden cronológico con su autor y fecha
```

## Refuerzos (scenario-coverage)

```gherkin
Feature: Refuerzos detalle (defensa en profundidad + acceso)

  Scenario: Una nota interna en el payload nunca se muestra al cliente
    Given un ticket cuyo payload incluye una nota interna
    And una usuaria cliente
    When se renderiza el hilo
    Then la nota interna no aparece bajo ninguna circunstancia

  Scenario: Detalle de un ticket inaccesible
    Given un enlace a un ticket inexistente o de otro tenant
    When se abre el detalle
    Then se muestra no-encontrado o acceso denegado, sin filtrar datos
```

## Provides

- Página de detalle (contenedor) + componente de hilo con filtro de visibilidad. 10/11/12/15 cuelgan de aquí.

## Definition of Done

- [x] Tests ANTES (TDD); cada escenario con ≥1 test (cliente sin internal, soporte con internal, orden, empty, inaccesible + defensa en profundidad).
- [x] Filtro de visibilidad correcto por capacidad (`note.internal.read`); hilo ordenado cronológicamente.
- [x] Lint + typecheck OK; gate de mutation 92.31% (break 80); estados loading/error/empty + a11y (`role=status/alert`, `listitem`, `aria-busy`).
- [x] `Provides` disponible (detalle + hilo con filtro); `fact-checker` 10/10 VERIFICADO; docs 3 capas + session log.
