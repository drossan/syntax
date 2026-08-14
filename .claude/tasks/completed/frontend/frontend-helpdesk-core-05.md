---
id: frontend-helpdesk-core-05
package: frontend
plan: helpdesk-core
status: done
priority: 1
depends_on: [frontend-helpdesk-core-03, backend-skeleton-foundation-02]
estimate: 4h
actual: 4h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# RBAC en cliente + contexto de tenant + tenant switcher

## Description

Autorización en cliente por **capacidad+ámbito** (replicando `rbac.md`, no reinventando) y el contexto de
tenant: menús/rutas/acciones se muestran según capacidades; Soporte (Syntax) puede cambiar de tenant; el
cliente queda fijado a su tenant. El enforcement real lo hace la API; esto es UX + defensa en profundidad.

## Spec

- `useCan(capability, scope?)` derivado de la sesión (03); `<Can>` wrapper para acciones/enlaces.
- Guard de rutas por capacidad (redirect/403 view si falta).
- Contexto de tenant + **tenant switcher** visible solo para capacidad `scope=global` (Soporte); el cliente
  no lo ve y su `tenant_id` es fijo.
- Filtro de visibilidad de mensajes (`internal` solo con `note.internal.read`) se apoya en `useCan`.

## Fuera de alcance

- Role builder (18, read-only). Enforcement (lo hace la API). Composer de roles (diferido).

## Scenarios (Gherkin)

```gherkin
Feature: Autorización y tenant en cliente

  Scenario: Una acción se oculta sin la capacidad
    Given una usuaria sin la capacidad "ticket.assign"
    When abre un ticket
    Then la acción de asignar no está disponible

  Scenario: Soporte de Syntax cambia de tenant
    Given un agente de soporte con ámbito global
    When selecciona otro tenant en el switcher
    Then la vista pasa a mostrar los datos de ese tenant

  Scenario: El cliente está fijado a su tenant
    Given una usuaria cliente
    When navega por la aplicación
    Then no ve el selector de tenant y solo accede a su propio dominio

  Scenario: Ruta sin capacidad requerida
    Given una usuaria sin la capacidad "tenant.manage"
    When intenta acceder a la administración de clientes
    Then se le muestra una vista de acceso denegado
```

## Refuerzos (scenario-coverage)

```gherkin
Feature: Refuerzos RBAC/tenant

  Scenario: Sin capacidades resueltas se falla en cerrado
    Given una sesión cuyas capacidades no se pudieron determinar
    When se renderiza la interfaz
    Then no se ofrece ninguna acción ni ruta privilegiada

  Scenario: Capacidad de ámbito de tenant no aplica a otro tenant
    Given una agente con "ticket.assign" acotada a su tenant
    When abre un ticket de otro tenant
    Then la acción de asignar no está disponible

  Scenario: Cliente no accede a otro tenant por enlace directo
    Given una usuaria cliente fijada a su tenant
    When abre un enlace con el identificador de otro tenant
    Then se le deniega y solo ve datos de su propio tenant
```

## Provides

- `useCan`, `<Can>`, guard de rutas, contexto de tenant + switcher. 06+ (shell/features) los consumen.

## Definition of Done

- [x] Tests ANTES (TDD); cada escenario con ≥1 test (capacidad presente/ausente, tenant global/fijo). 13 tests.
- [x] RBAC por capacidad+ámbito coherente con `rbac.md`; switcher solo para ámbito global.
- [x] Lint + typecheck OK; gate de mutation (90.76% ≥ 80); estados + a11y (aria-label switcher, role alert AccessDenied).
- [x] `Provides` disponible; `fact-checker` (13/13); docs 3 capas + session log.
