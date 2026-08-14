# CU-BE-03 — Autorización por capacidad y aislamiento tenant

> **SDD** (Cockburn + Gherkin). CÓMO para FR-010…FR-015 de [`../spec.md`](../spec.md). Decisiones:
> [[../../adr/0005-rbac-por-capacidad-y-ambito]], [[../../adr/0006-aislamiento-multi-tenant-app-level-mas-rls]].
> Detalle: [`../rbac.md`](../rbac.md).

- **Ámbito**: backend (capa de autorización + repos/RLS)
- **Nivel**: subfunción (transversal a toda operación de negocio)
- **Actor primario**: sujeto autenticado (cliente o Soporte)
- **Interesados e intereses**:
  - Cliente — no ver ni tocar datos de otro tenant.
  - Soporte — operar cross-tenant cuando su ámbito es `global`.
  - Plataforma — deny-all por defecto; sin fugas cross-tenant.

## Precondiciones

- El sujeto está autenticado; su conjunto efectivo de `(capability, scope)` es resoluble server-side.

## Garantía mínima

- Ante cualquier duda de permisos, se **deniega** (fail-closed); nunca se abre por defecto.

## Garantía de éxito (postcondición)

- La operación se ejecuta solo si el sujeto tiene la capacidad en el ámbito del recurso, dentro de su tenant.

## Disparador

- El sujeto invoca cualquier endpoint de negocio.

## Escenario principal (éxito)

1. El sujeto solicita una acción sobre un recurso de su tenant.
2. El sistema resuelve sus capacidades server-side y evalúa `authorize(subject, capability, scope, resource)`.
3. La capacidad existe en el ámbito del recurso → la acción procede, filtrada por `tenant_id` (app-level + RLS).

## Extensiones (flujos alternativos y de error)

- **2a.** Falta la capacidad: el sistema responde **403** (`problem+json`).
- **2b.** Sujeto sin ningún rol: el sistema deniega todo (deny-all).
- **1a.** Recurso de **otro** tenant (sujeto sin `global`): el sistema responde **404** (no revela existencia).
- **1b.** Sujeto de Soporte con ámbito `global`: opera cross-tenant (o sobre el tenant del switcher).

## Reglas de negocio

- **RN-1** — Se decide por **capacidad + ámbito**, nunca por el nombre del rol.
- **RN-2** — El aislamiento es **doble**: filtro app-level en repos **y** RLS de Postgres.
- **RN-3** — La KB es global (sin RLS de tenant); accesible con `kb.read` desde cualquier tenant.

## Criterios de aceptación (Gherkin)

```gherkin
Feature: Autorización por capacidad y aislamiento tenant

  Scenario: Acción permitida dentro del tenant
    Given un sujeto con la capacidad "ticket.reply" en su tenant
    When responde a un ticket de su tenant
    Then la respuesta se registra correctamente

  Scenario: Acción sin la capacidad requerida
    Given un sujeto sin la capacidad "ticket.transition"
    When intenta cambiar el estado de un ticket
    Then la operación se deniega con 403

  Scenario: Sujeto sin ningún rol
    Given un sujeto autenticado sin roles asignados
    When intenta cualquier acción de negocio
    Then todas las acciones se deniegan (deny-all)

  Scenario: Recurso de otro tenant no se revela
    Given un sujeto de un tenant A sin ámbito global
    When solicita un ticket que pertenece a un tenant B
    Then el sistema responde 404 sin revelar que el ticket existe

  Scenario: Soporte opera cross-tenant
    Given un sujeto de Soporte con capacidades de ámbito global
    When gestiona un ticket de un cliente distinto
    Then la operación procede sobre el tenant del cliente

  Scenario: Fallo al resolver capacidades cierra el acceso
    Given un sujeto cuyas capacidades no pueden resolverse
    When intenta una acción privilegiada
    Then el sistema deniega la acción (fail-closed)
```
