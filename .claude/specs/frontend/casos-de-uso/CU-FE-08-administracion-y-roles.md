# CU-FE-08 — Administración y roles

> **SDD** (Cockburn + Gherkin). CÓMO para FR-022 de [`../spec.md`](../spec.md). Decisión:
> [[../../adr/0005-rbac-por-capacidad-y-ambito]]. Backend:
> [CU-BE-09](../../backend/casos-de-uso/CU-BE-09-administracion-tenants-usuarios-roles.md). **Composer diferido**.

- **Ámbito**: frontend (feature admin)
- **Nivel**: objetivo de usuario (administrador)
- **Actor primario**: `support_admin` (tenants) / `client_admin` (usuarios de su tenant)
- **Interesados e intereses**:
  - Admin — gestionar tenants/usuarios e invitar; ver qué concede cada rol.
  - Plataforma — no ofrecer en cliente lo que el backend no permite (fail-closed).

## Precondiciones

- El sujeto tiene `tenant.manage` / `user.manage` / `role.manage` según el caso.

## Garantía mínima

- Las acciones destructivas piden confirmación; las vistas de roles son **read-only** (composer diferido).

## Garantía de éxito (postcondición)

- Los tenants/usuarios reflejan los cambios; se puede invitar y asignar roles semilla.

## Disparador

- El admin gestiona tenants/usuarios/roles o invita.

## Escenario principal (éxito)

1. `support_admin` gestiona tenants (CRUD, con confirmación en borrado).
2. `client_admin` da de alta/invita usuarios de su tenant.
3. El admin consulta roles/capacidades (read-only) y **asigna roles semilla** a usuarios.

## Extensiones (flujos alternativos y de error)

- **1a.** Borrado de tenant/usuario: pide **confirmación** (destructiva).
- **3a.** Composición de roles custom: **no disponible** en Fase 1 (composer diferido; solo asignación de semilla).
- **2a.** Error de API (`problem+json`): se mapea a errores de campo + toast.

## Reglas de negocio

- **RN-1** — Las vistas de roles son de solo lectura; solo se asignan roles de sistema.
- **RN-2** — Toda acción admin visible asume enforcement del backend (defensa en profundidad).

## Criterios de aceptación (Gherkin)

```gherkin
Feature: Administración y roles

  Scenario: Invitación de un usuario
    Given un administrador de tenant con permiso de gestión de usuarios
    When invita a un usuario nuevo
    Then el usuario queda invitado y recibe su enlace de invitación (stub)

  Scenario: Confirmación al borrar
    Given un administrador que va a borrar un tenant
    When intenta borrar el tenant
    Then se le pide confirmación antes de aplicar

  Scenario: Vista read-only de roles
    Given un administrador consultando los roles
    When abre la vista de roles y capacidades
    Then ve qué concede cada rol sin poder editar su composición

  Scenario: Asignación de un rol semilla
    Given un usuario de un tenant
    When el administrador le asigna un rol de sistema
    Then el usuario obtiene las capacidades de ese rol
```
