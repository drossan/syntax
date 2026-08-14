---
id: frontend-helpdesk-core-17
package: frontend
plan: helpdesk-core
status: done
priority: 3
depends_on: [frontend-helpdesk-core-06, backend-skeleton-foundation-02, backend-skeleton-foundation-03, backend-skeleton-foundation-06]
estimate: 4h
actual: 1.6h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# Admin — clientes (tenants) y usuarios + invitación

## Description

Administración: CRUD de tenants (clientes/dominios) y de usuarios, con **invitación** al crear usuario
(B.3). Alcance por capacidad: `support_admin` gestiona todos los tenants; `client_admin` solo el suyo.

## Spec

- CRUD tenants (nombre, dominio(s), settings incl. `auto_approve`) — solo `tenant.manage` (Soporte).
- CRUD usuarios del tenant + asignación de rol semilla + **invitación** (`user.manage`); `client_admin` acotado a su tenant.
- Tablas (TanStack Table) con estados empty/loading/error; formularios RHF+Zod con mapeo de errores.

## Fuera de alcance

- Composer de roles custom (18 es read-only + asignación). Envío real de email (stub).

## Scenarios (Gherkin)

```gherkin
Feature: Administración de clientes y usuarios

  Scenario: Crear un tenant (Soporte)
    Given un support_admin
    When crea un tenant con nombre y dominio válidos
    Then el tenant aparece en el listado

  Scenario: client_admin acotado a su tenant
    Given un client_admin
    When abre la administración de usuarios
    Then solo ve y gestiona usuarios de su propio tenant

  Scenario: Invitar a un usuario nuevo
    Given un admin con capacidad de gestión de usuarios
    When crea un usuario y le asigna un rol semilla
    Then se genera una invitación para que fije su contraseña

  Scenario: Cliente sin capacidad de gestión de tenants
    Given un client_admin
    When intenta acceder al CRUD de tenants
    Then se le deniega el acceso
```

## Refuerzos (scenario-coverage)

```gherkin
Feature: Refuerzos admin (destructivo + escalada)

  Scenario: Borrar un tenant pide confirmación
    Given un support_admin en la administración de tenants
    When intenta borrar un tenant
    Then se le pide confirmación antes de aplicar el borrado

  Scenario: Un client_admin no gestiona otro tenant por enlace directo
    Given un client_admin
    When abre un enlace de gestión de un usuario de otro tenant
    Then se le deniega el acceso
```

## Provides

- Páginas de admin (tenants/usuarios) + invitación. 18 (roles) enlaza desde aquí.

## Definition of Done

- [x] Tests ANTES (TDD): crear tenant, scope client_admin (server-scoped), invitación (rol semilla), denegado (client sin tenant.manage), deshabilitar+confirm, cancelar confirm.
- [x] List+create tenants (no hay delete/patch en contrato), users list+invite+deshabilitar(confirm); acotación por capacidad/tenant (server-scoped); RHF+Zod con mapeo de errores.
- [x] Lint + typecheck OK; gate de mutation 86.67% (break 80); estados empty/loading/error + a11y (tabla con scope, alertdialog).
- [x] `Provides` disponible; `fact-checker` 10/10 VERIFICADO; docs 3 capas + session log.
