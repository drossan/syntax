---
id: frontend-helpdesk-core-10
package: frontend
plan: helpdesk-core
status: done
priority: 2
depends_on: [frontend-helpdesk-core-09]
estimate: 4h
actual: 2h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# Ticket — mutaciones (estado, prioridad, asignación)

## Description

Mutaciones del ticket con **optimistic-update + rollback** por envelope de error, y **confirm** en acciones
destructivas: transición de estado (máquina new/open/pending/resolved/closed/reopened), prioridad, asignación.

## Spec

- Transición de estado válida (según máquina); la UI **no ofrece** transiciones inválidas; server rechaza → rollback.
- Cambio de prioridad y asignación (a agente permitido), con optimistic-update y revalidación.
- **Confirm dialog** en acciones destructivas (cerrar ticket). Añadir respuesta pública también aquí o en 15
  (respuesta del agente = mensaje `public`).

## Fuera de alcance

- Aprobación de draft IA (15). Adjuntos (11). SLA/timeline (12).

## Scenarios (Gherkin)

```gherkin
Feature: Mutaciones de ticket

  Scenario: Transición de estado optimista
    Given un ticket abierto
    When el agente lo marca como pendiente
    Then el estado se refleja de inmediato y se confirma tras la respuesta del servidor

  Scenario: Rollback ante error del servidor
    Given un ticket abierto
    When el agente cambia el estado y el servidor responde error
    Then el estado vuelve a su valor anterior y se muestra un aviso

  Scenario: Transición inválida no ofrecida
    Given un ticket cerrado
    When el agente abre las acciones de estado
    Then no se ofrece una transición inválida desde "cerrado"

  Scenario: Confirmación al cerrar
    Given un ticket abierto
    When el agente intenta cerrarlo
    Then se le pide confirmación antes de aplicar el cierre
```

## Refuerzos (scenario-coverage)

```gherkin
Feature: Refuerzos mutaciones (concurrencia)

  Scenario: Cancelar la confirmación de cierre no cambia el ticket
    Given un ticket abierto
    When el agente inicia el cierre pero cancela la confirmación
    Then el ticket permanece abierto y no se envía ninguna mutación

  Scenario: Escritura obsoleta cuando otro agente ya cambió el estado
    Given dos agentes viendo el mismo ticket
    When el agente A cambia el estado y el servidor lo rechaza por conflicto de versión
    Then se revierte el cambio de A y se le muestra el estado real actualizado

  Scenario: Respuestas fuera de orden dejan estado consistente
    Given dos cambios de estado seguidos sobre un ticket
    When las respuestas del servidor llegan en orden inverso
    Then el estado final refleja la última acción del agente
```

## Provides

- Acciones de mutación del ticket (estado/prioridad/asignación) con optimistic/confirm. 12/15 conviven en el detalle.

## Definition of Done

- [x] Tests ANTES (TDD); cada escenario con ≥1 test (optimista, rollback, transición inválida, confirm, cancelar, reconciliación, asignación, prioridad).
- [x] Optimistic-update + rollback por envelope; máquina de estados respetada; confirm en destructivas (cerrar).
- [x] Lint + typecheck OK; gate de mutation 84.81% (break 80); a11y de diálogo (role=alertdialog, foco, Escape).
- [x] `Provides` disponible (acciones estado/prioridad/asignación); `fact-checker` 10/10 VERIFICADO; docs 3 capas + session log.
