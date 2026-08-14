---
id: frontend-helpdesk-core-14
package: frontend
plan: helpdesk-core
status: done
priority: 2
depends_on: [frontend-helpdesk-core-13]
estimate: 4h
actual: 1.2h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# Ciclo de draft IA (disparo + polling)

## Description

El ciclo de generación del draft IA: disparar la generación, **hacer polling** del `AgentRun` hasta
`done`/`failed`, y mostrar el draft con sus **fuentes y confianza**. Maneja el estado `failed` con
reintento. (Sin streaming SSE en Fase 1: polling.)

## Spec

- Disparar `POST /tickets/{id}/ai-draft`; **polling** de `GET /agent-runs/{id}` (`running`→`done`/`failed`)
  vía `refetchInterval` de Query, con parada al terminar.
- `done`: mostrar draft + **fuentes** (citas UC) + **confianza**; `failed`: mensaje de error + **reintentar**.
- Estados: sin draft / generando / listo / fallido. Idempotente ante re-disparo (no duplica runs en curso).

## Fuera de alcance

- Decisiones aprobar/editar/rechazar (15). Streaming SSE (diferido). Generación real (backend).

## Scenarios (Gherkin)

```gherkin
Feature: Generación del draft IA

  Scenario: El draft se genera y se muestra con fuentes y confianza
    Given un ticket sin draft
    When se dispara la generación y el run llega a "done"
    Then se muestra el draft con sus fuentes y su nivel de confianza

  Scenario: El run falla y se puede reintentar
    Given una generación en curso
    When el run termina en "failed"
    Then se muestra el error y una acción de reintentar

  Scenario: Estado de generación en curso
    Given una generación disparada
    When el run está "running"
    Then se muestra el estado de "generando" y se sondea hasta que cambie
```

## Provides

- Componente del ciclo de draft (disparo+polling+estado) con fuentes/confianza. 15 opera sobre el draft listo.

## Definition of Done

- [x] Tests ANTES (TDD): done con fuentes/confianza, failed+retry, running/polling con MSW, idempotencia, sin-capacidad.
- [x] Polling con parada al terminar (`draftPollInterval`); manejo de `failed`; idempotencia (botón deshabilitado con run activo).
- [x] Lint + typecheck OK; gate de mutation 87.76% (break 80); estados + a11y (`aria-live` del estado).
- [x] `Provides` disponible; `fact-checker` 10/10 VERIFICADO; docs 3 capas + session log.
