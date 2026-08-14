# CU-FE-02 — RBAC de cliente y cambio de tenant

> **SDD** (Cockburn + Gherkin). CÓMO para FR-008…FR-011 de [`../spec.md`](../spec.md). Decisión:
> [[../../adr/0005-rbac-por-capacidad-y-ambito]]. Políticas: [`../cross-cutting.md`](../cross-cutting.md) §3, §5.
> Backend: [CU-BE-03](../../backend/casos-de-uso/CU-BE-03-autorizacion-y-aislamiento-tenant.md).

- **Ámbito**: frontend (RBAC cliente + contexto de tenant)
- **Nivel**: objetivo de usuario
- **Actor primario**: usuario (cliente) / agente de Soporte (multi-tenant)
- **Interesados e intereses**:
  - Usuario — ver solo lo que su rol permite (UX coherente).
  - Soporte — cambiar de tenant sin arrastrar datos del anterior.
  - Plataforma — la API es la fuente de verdad; el cliente es defensa en profundidad.

## Precondiciones

- La sesión resolvió las capacidades del sujeto.

## Garantía mínima

- Si las capacidades no se resuelven, no se ofrece ninguna acción/ruta privilegiada (fail-closed).

## Garantía de éxito (postcondición)

- Menús, rutas y acciones reflejan las capacidades; al cambiar de tenant, las vistas muestran el nuevo tenant.

## Disparador

- Se renderiza la navegación, se intenta una acción, o Soporte cambia de tenant.

## Escenario principal (éxito)

1. La app muestra rutas/menús/acciones **según las capacidades** de la sesión.
2. El usuario ejecuta una acción permitida; procede.
3. Soporte cambia de tenant en el switcher; la app invalida las cachés dependientes de tenant.

## Extensiones (flujos alternativos y de error)

- **2a.** La API deniega con **403** una acción visible: la app informa **sin mutar estado** (reconciliación).
- **1a.** Capacidades no resueltas: la app no ofrece acciones/rutas privilegiadas (fail-closed).
- **3a.** Respuestas en vuelo del tenant anterior llegan tras el switch: se **descartan** (no "pisan" la vista nueva).

## Reglas de negocio

- **RN-1** — La visibilidad se decide por **capacidad**, nunca por nombre de rol.
- **RN-2** — El cambio de tenant invalida bandeja, detalle, dashboard y cola.

## Criterios de aceptación (Gherkin)

```gherkin
Feature: RBAC de cliente y cambio de tenant

  Scenario: La navegación refleja las capacidades
    Given un usuario sin la capacidad de aprobar borradores
    When abre la aplicación
    Then no ve la entrada ni las acciones de la cola de aprobaciones

  Scenario: Acción denegada por la API se reconcilia
    Given una acción visible para el usuario
    When la API la deniega con 403
    Then la interfaz informa del rechazo sin cambiar el estado mostrado

  Scenario: Fail-closed si no se resuelven capacidades
    Given una sesión cuyas capacidades no pueden resolverse
    When se renderiza la aplicación
    Then no se ofrece ninguna acción ni ruta privilegiada

  Scenario: Cambio de tenant invalida las cachés dependientes
    Given un agente de Soporte viendo la bandeja de un tenant
    When cambia al tenant de otro cliente
    Then las vistas dependientes de tenant se recargan para el nuevo tenant

  Scenario: Respuestas del tenant anterior se descartan
    Given un cambio de tenant con peticiones aún en vuelo del tenant anterior
    When esas respuestas llegan después del cambio
    Then se descartan y no alteran la vista del nuevo tenant
```
