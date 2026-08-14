---
id: frontend-helpdesk-core-15
package: frontend
plan: helpdesk-core
status: done
priority: 2
depends_on: [frontend-helpdesk-core-14]
estimate: 4h
actual: 1.4h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# Decisiones de aprobación (aprobar / editar / rechazar)

## Description

El corazón de la Fase 1: sobre un draft IA listo, el humano de Syntax **aprueba** (publica), **edita y
aprueba**, o **rechaza** dejando una **nota-al-humano**. Aprobar/editar materializa un mensaje `public` y
transiciona el ticket.

## Spec

- Aprobar → `POST /approvals/{id}/approve` → el draft se publica como mensaje `public` y el ticket transiciona.
- Editar → ajustar el texto → `.../edit` (publica el texto editado).
- Rechazar → `.../reject` con **nota-al-humano** obligatoria + **confirm**; el draft no se publica.
- Refleja `AgentRun.failed` (no hay draft que aprobar → invita a reintentar/escala).

## Fuera de alcance

- Nota-al-desarrollador (Fase 2). Generación del draft (14). Enforcement (API).

## Scenarios (Gherkin)

```gherkin
Feature: Decisión sobre el draft IA

  Scenario: Aprobar publica la respuesta al cliente
    Given un draft IA pendiente de aprobación
    When el agente lo aprueba
    Then se publica como mensaje público y el ticket avanza de estado

  Scenario: Editar y aprobar
    Given un draft IA pendiente
    When el agente edita el texto y aprueba
    Then se publica el texto editado

  Scenario: Rechazar exige nota y confirmación
    Given un draft IA pendiente
    When el agente intenta rechazarlo sin nota
    Then se le exige una nota-al-humano y una confirmación antes de rechazar

  Scenario: Sin draft por fallo del run
    Given un run de draft en estado "failed"
    When el agente abre la aprobación
    Then no hay draft que aprobar y se ofrece reintentar o escalar
```

## Refuerzos (scenario-coverage)

```gherkin
Feature: Refuerzos decisiones (idempotencia)

  Scenario: Un draft ya aprobado no se vuelve a aprobar
    Given un draft cuya aprobación ya fue aplicada
    When el agente intenta aprobarlo de nuevo
    Then la acción no tiene efecto adicional y se informa del estado ya resuelto

  Scenario: Cancelar la confirmación de rechazo no rechaza
    Given un draft pendiente
    When el agente inicia el rechazo pero cancela la confirmación
    Then el draft sigue pendiente y no se envía el rechazo
```

## Provides

- Acciones de decisión (aprobar/editar/rechazar + nota). Cierra el flujo IA→aprobación→respuesta.

## Definition of Done

- [x] Tests ANTES (TDD): aprobar (POST approve), editar (final_body), rechazar (nota obligatoria + confirm), cancelar rechazo, idempotencia (ya resuelta), sin-borrador, 409.
- [x] Aprobar/editar → POST approve/edit (server publica + transiciona; invalida ticket); rechazar con nota+confirm → POST reject.
- [x] Lint + typecheck OK; gate de mutation 95.65% (break 80); a11y del diálogo de rechazo (role=alertdialog, textarea etiquetada).
- [x] `Provides` disponible; `fact-checker` (9 VERIFICADO, 0 INCORRECTO); docs 3 capas + session log.
