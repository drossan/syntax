---
id: frontend-helpdesk-core-06
package: frontend
plan: helpdesk-core
status: done
priority: 2
depends_on: [frontend-helpdesk-core-05]
estimate: 3h
actual: 4h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# App shell / layout

## Description

El armazón de la app autenticada: navegación lateral (según rol), cabecera (usuario, tenant switcher,
notificaciones, switch de idioma, tema/dark), y el layout responsive del grupo `(app)`.

## Spec

- Layout `(app)` con nav + header + slot de contenido; responsive (colapsa en móvil).
- Nav construida desde capacidades (usa `useCan`): solo entradas permitidas.
- Header: menú de usuario (logout), tenant switcher (05), campana de notificaciones (placeholder→20),
  selector de idioma (next-intl), toggle de tema.

## Fuera de alcance

- Contenido de cada sección (features). Lógica de notificaciones (20).

## Scenarios (Gherkin)

```gherkin
Feature: Armazón de la aplicación

  Scenario: La navegación refleja las capacidades del rol
    Given una usuaria cuyo rol no puede administrar clientes
    When ve la navegación
    Then no aparece la entrada de administración de clientes

  Scenario: Cambio de idioma
    Given la interfaz en español
    When cambia el idioma a inglés
    Then los textos de la interfaz pasan a inglés

  Scenario: Cambio de tema
    Given el tema claro activo
    When activa el tema oscuro
    Then la interfaz se muestra en modo oscuro y persiste la preferencia
```

## Provides

- Layout `(app)`, nav por capacidades, header con controles. Todas las páginas de feature viven dentro.

## Definition of Done

- [x] Tests ANTES (TDD); cada escenario con ≥1 test (nav por capacidad, idioma, tema). 5 tests.
- [x] Layout responsive; nav derivada de `useCan`; controles de header cableados.
- [x] Lint + typecheck OK; gate de mutation (90.76% ≥ 80, lógica .ts); a11y (nav aria-label, aria-pressed toggle, roles).
- [x] `Provides` disponible; `fact-checker` (12/13 + matiz timeZone corregido); docs 3 capas + session log.
