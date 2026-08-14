---
id: frontend-helpdesk-core-22
package: frontend
plan: helpdesk-core
status: done
priority: 3
depends_on: [frontend-helpdesk-core-07, frontend-helpdesk-core-08]
estimate: 4h
actual: 2h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# Requisitos transversales de helpdesk (URL-state, no-leído, nav-guard, offline)

## Description

Requisitos que un helpdesk necesita y que ninguna feature cubría (scenario-coverage T5/T6/T7/T10):
persistencia de estado de lista en la URL, indicador de "no leído" en tickets, guard de navegación con
cambios sin guardar, y manejo de "sin conexión". Se aplican como utilidades reutilizables sobre las
features ya existentes.

## Spec

- **URL-state (T5)**: hook `useUrlListState` que sincroniza filtros/orden/página con la query string
  (bandeja 07, cola 13, KB 16, dashboard 19). El estado es compartible por enlace y sobrevive a la recarga.
- **No leído (T10)**: derivar/mostrar el estado "no leído" de un ticket (última visita vs última actividad);
  se distingue en la bandeja y se marca leído al abrir el detalle.
- **Nav-guard (T6)**: hook `useUnsavedGuard` que pide confirmación al navegar fuera de un form con cambios
  sin guardar (alta 08, editar draft 15, forms admin 17).
- **Offline (T7)**: detección de pérdida de conexión (aviso global) + reintento de lecturas al recuperar la red.

## Fuera de alcance

- Presence/"quién está viendo", command palette (baja prioridad Fase 1). Sincronización servidor del "leído"
  si el contrato no lo expone → derivación en cliente documentada.

## Scenarios (Gherkin)

```gherkin
Feature: Requisitos transversales de helpdesk

  Scenario: Un listado filtrado es compartible y sobrevive a la recarga
    Given una bandeja filtrada por estado y ordenada por prioridad, en la página 2
    When se recarga la página o se comparte el enlace
    Then se restauran los mismos filtros, orden y página

  Scenario: Un ticket con actividad nueva se marca como no leído
    Given un ticket con un mensaje nuevo desde la última visita
    When aparece en la bandeja
    Then se distingue como no leído, y deja de estarlo tras abrir su detalle

  Scenario: Navegar fuera de un formulario con cambios sin guardar pide confirmación
    Given un formulario con cambios sin guardar
    When la persona intenta abandonar la vista
    Then se le pide confirmación antes de descartar los cambios

  Scenario: Pérdida de conexión durante el uso
    Given una persona usando la app
    When se pierde la conexión de red
    Then se le informa del estado sin conexión y las lecturas se reintentan al recuperarla
```

## Provides

- `useUrlListState`, indicador de no-leído, `useUnsavedGuard`, detección offline. Reutilizados por 07/08/13/15/16/17/19.

## Definition of Done

- [x] Tests ANTES (TDD): URL-state (read/write + restauración), no-leído (isUnread + store + detalle marca visitado), nav-guard (beforeunload dirty/limpio/unmount), offline (banner + reintento al reconectar).
- [x] Hooks reutilizables aplicados: URL-state+no-leído en bandeja (07), nav-guard en alta (08), offline en shell, markVisited en detalle (09); núcleo puro compartido (list-state/unread), sin duplicar.
- [x] Lint + typecheck OK; gate de mutation 82.61% (break 80); a11y (`role=alert` offline, `aria-label` no-leído).
- [x] `Provides` disponible; `fact-checker` 11/11 VERIFICADO; docs 3 capas + session log. *(guard nav-soft App Router: follow-up documentado)*
