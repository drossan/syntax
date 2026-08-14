# CU-BE-09 — Administración de tenants, usuarios y roles

> **SDD** (Cockburn + Gherkin). CÓMO para FR-036…FR-037 de [`../spec.md`](../spec.md). Decisión:
> [[../../adr/0005-rbac-por-capacidad-y-ambito]]. Detalle: [`../rbac.md`](../rbac.md) §4, [`../data-model.md`](../data-model.md) §4.1.

- **Ámbito**: backend (servicios admin + RBAC)
- **Nivel**: objetivo de usuario (administrador)
- **Actor primario**: `support_admin` (tenants) / `client_admin` (usuarios y roles de su tenant)
- **Interesados e intereses**:
  - Admin — dar de alta usuarios y adaptar permisos a su organización.
  - Plataforma — sin escalada de privilegios; sin hard-delete en el flujo normal.

## Precondiciones

- El sujeto tiene `tenant.manage` (Soporte) o `user.manage`/`role.manage` en su tenant.

## Garantía mínima

- Ninguna composición de rol concede más de lo que el componedor posee ni capacidades `global`.

## Garantía de éxito (postcondición)

- Los usuarios/roles reflejan el cambio dentro del ámbito; los tenants se desactivan (soft) en vez de borrarse.

## Disparador

- El admin crea/edita un tenant/usuario/rol o invita a alguien.

## Escenario principal (éxito)

1. `support_admin` crea un tenant (cliente = dominio).
2. `client_admin` invita usuarios a su tenant ([CU-BE-02](./CU-BE-02-recuperacion-e-invitacion-de-contrasena.md)).
3. `client_admin` compone un rol custom a partir del catálogo de capacidades y lo asigna a usuarios de su tenant.

## Extensiones (flujos alternativos y de error)

- **3a.** El rol intenta incluir una capacidad `global` (`approval.decide`, `note.internal.*`, `tenant.manage`): se **rechaza**.
- **3b.** El rol intenta incluir una capacidad que el componedor **no posee**: se **rechaza** (no escalada).
- **3c.** El rol custom se intenta asignar a un usuario de **otro** tenant: se **rechaza**.
- **1a.** Baja de usuario/tenant: se aplica **soft-delete** por `status` (no hard-delete).
- **2a.** Editar un rol de **sistema**: se rechaza (inmutable; se clona para variar).

## Reglas de negocio

- **RN-1** — Roles de sistema inmutables; roles custom **tenant-scoped**.
- **RN-2** — Invariantes fail-closed: sin `global`, sin escalada, mismo tenant.
- **RN-3** — Soft-delete por `status` (`user_status.disabled`/`tenant_status.disabled`); hard-delete = procedimiento GDPR explícito.

## Criterios de aceptación (Gherkin)

```gherkin
Feature: Administración de tenants, usuarios y roles

  Scenario: Alta de un tenant por Soporte
    Given un sujeto con capacidad de gestionar tenants
    When crea un tenant nuevo
    Then el tenant queda disponible en estado activo

  Scenario: Composición válida de un rol custom
    Given un administrador de tenant que posee ciertas capacidades de ámbito tenant
    When compone un rol con un subconjunto de esas capacidades
    Then el rol queda disponible para asignarse a usuarios de su tenant

  Scenario: Un rol custom no puede conceder capacidades globales
    Given un administrador de tenant
    When intenta incluir una capacidad de ámbito global en un rol custom
    Then la composición se rechaza

  Scenario: Un rol custom no puede escalar privilegios
    Given un administrador que no posee cierta capacidad
    When intenta conceder esa capacidad en un rol custom
    Then la composición se rechaza

  Scenario: Baja de usuario es soft-delete
    Given un usuario activo
    When un administrador lo da de baja
    Then el usuario queda desactivado por estado y no se borra físicamente

  Scenario: Los roles de sistema son inmutables
    Given un rol de sistema semilla
    When se intenta editarlo
    Then la edición se rechaza
```
