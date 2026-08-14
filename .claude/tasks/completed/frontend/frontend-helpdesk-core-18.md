---
id: frontend-helpdesk-core-18
package: frontend
plan: helpdesk-core
status: done
priority: 3
depends_on: [frontend-helpdesk-core-17, backend-skeleton-foundation-02]
estimate: 2h
actual: 1.1h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# Roles y capacidades (read-only + asignación de roles semilla)

## Description

Vistas **read-only** del catálogo de roles/capacidades y **asignación de roles semilla** a usuarios. El
**composer** de roles custom se difiere (design-review C6) hasta que exista enforcement real en el backend.

## Spec

- Vista read-only del catálogo de capacidades y de los roles semilla (qué capacidades incluye cada uno).
- Asignar/retirar un rol semilla a un usuario (con `role.manage`), acotado por tenant.
- **Sin** UI de composición de roles custom en Fase 1 (placeholder que lo anuncia como próximo).

## Fuera de alcance

- Composer capacidades→roles custom (diferido). Enforcement (API).

## Scenarios (Gherkin)

```gherkin
Feature: Roles y capacidades

  Scenario: Ver el catálogo de roles y capacidades
    Given un admin con acceso a la gestión de roles
    When abre la vista de roles
    Then ve los roles semilla y las capacidades que incluye cada uno (solo lectura)

  Scenario: Asignar un rol semilla a un usuario
    Given un usuario del tenant sin un rol concreto
    When el admin le asigna un rol semilla
    Then el usuario pasa a tener las capacidades de ese rol

  Scenario: El composer de roles custom no está disponible aún
    Given la vista de roles en Fase 1
    When el admin busca crear un rol custom combinando capacidades
    Then no hay composer y se indica que llegará con el enforcement real
```

## Provides

- Vistas de roles/capacidades (read-only) + asignación de roles semilla.

## Definition of Done

- [x] Tests ANTES (TDD): ver catálogo read-only, asignar rol semilla (PATCH roles, sin duplicar), ausencia de composer + aviso enforcement, guards de página.
- [x] Read-only (roles+capacidades) + asignación de rol semilla; sin composer; acotado por `role.manage` + tenant (server-side).
- [x] Lint + typecheck OK; gate de mutation 88% (break 80); a11y (selects etiquetados, listas).
- [x] `Provides` disponible; `fact-checker` 10/10 VERIFICADO; docs 3 capas + session log.
