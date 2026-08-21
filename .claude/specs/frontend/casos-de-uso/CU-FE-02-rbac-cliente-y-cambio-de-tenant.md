# CU-FE-02 — RBAC de cliente y cambio de tenant

> **SDD** (Cockburn + Gherkin). CÓMO para FR-008…FR-011 de [`../spec.md`](../spec.md). Decisión:
> [[../../adr/0005-rbac-por-capacidad-y-ambito]]. Políticas: [`../cross-cutting.md`](../cross-cutting.md) §3, §5.
> Backend: [CU-BE-03](../../backend/casos-de-uso/CU-BE-03-autorizacion-y-aislamiento-tenant.md).

- **Ámbito**: frontend (RBAC cliente + contexto de tenant)
- **Nivel**: objetivo de usuario
- **Actor primario**: usuario (cliente) / agente de Soporte (multi-tenant)
- **Interesados e intereses**:
  - Usuario — ver solo lo que su rol permite (UX coherente).
  - Usuario con 2+ tenants (cliente o Soporte) — cambiar de tenant sin arrastrar datos del anterior.
  - Plataforma — la API es la fuente de verdad; el cliente es defensa en profundidad.

## Precondiciones

- La sesión resolvió las capacidades del sujeto.

## Garantía mínima

- Si las capacidades no se resuelven, no se ofrece ninguna acción/ruta privilegiada (fail-closed).

## Garantía de éxito (postcondición)

- Menús, rutas y acciones reflejan las capacidades; al cambiar de tenant, las vistas muestran el nuevo tenant.

## Disparador

- Se renderiza la navegación, se intenta una acción, o el usuario cambia de tenant.

## Escenario principal (éxito)

1. La app muestra rutas/menús/acciones **según las capacidades** de la sesión.
2. El usuario ejecuta una acción permitida; procede.
3. Con 2+ membresías `active`, el usuario ve el selector de tenant; al elegir uno, la app cambia de
   verdad de sesión (`POST /auth/switch-tenant`) e invalida las cachés dependientes de tenant.

## Extensiones (flujos alternativos y de error)

- **2a.** La API deniega con **403** una acción visible: la app informa **sin mutar estado** (reconciliación).
- **1a.** Capacidades no resueltas: la app no ofrece acciones/rutas privilegiadas (fail-closed).
- **3a.** Respuestas en vuelo del tenant anterior llegan tras el switch: se **descartan** (no "pisan" la vista nueva).
- **3b.** Con una sola membresía `active`, no hay selector que mostrar.
- **3c.** El cambio de tenant es rechazado por la API (membership ya no `active`, tenant `disabled`):
  la app informa el error y la vista **permanece** con los datos del tenant anterior — la caché solo
  se limpia tras confirmar el éxito, nunca de forma optimista. El selector vuelve a mostrar el tenant
  anterior (nunca se queda mostrando la opción que falló).
- **3d.** Mientras se resuelve un cambio de tenant, el selector queda deshabilitado (no se puede
  elegir otro tenant a la vez).
- **3e.** El selector siempre incluye el tenant activo actual entre las opciones (para poder marcarlo
  como seleccionado), no solo "los otros" tenants.

## Reglas de negocio

- **RN-1** — La visibilidad se decide por **capacidad**, nunca por nombre de rol.
- **RN-2** — El cambio de tenant invalida bandeja, detalle, dashboard y cola.
- **RN-3** — El selector de tenant se ofrece a **cualquier** usuario con 2+ membresías `active`
  (cliente o Soporte), no solo a Soporte — la visibilidad depende de cuántos tenants tiene, no de
  su rol.
- **RN-4** — "Bandeja, detalle, dashboard y cola" (RN-2) incluye explícitamente la **cola de
  aprobaciones**: sus consultas están escopadas por tenant igual que las de tickets/analytics, para
  que una respuesta tardía del tenant anterior no pueda pisar la vista del nuevo.

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

  Scenario: Cualquier usuario con 2+ tenants ve el selector
    Given un usuario con 2+ membresías active en tenants distintos
    When abre la aplicación
    Then puede elegir a qué tenant conectarse

  Scenario: Con una sola membresía no hay selector que mostrar
    Given un usuario con una sola membresía active
    When abre la aplicación
    Then no ve ningún selector de tenant

  Scenario: Cambiar de tenant falla sin alterar la vista actual
    Given un usuario cambiando de tenant desde el selector
    When el cambio de tenant es rechazado por la API
    Then la vista se queda con los datos del tenant anterior, el selector lo sigue mostrando, y se informa del error

  Scenario: El selector se deshabilita mientras resuelve
    Given un usuario que acaba de elegir un tenant en el selector
    When el cambio todavía no se ha resuelto
    Then no puede elegir otro tenant a la vez

  Scenario: El selector incluye el tenant activo actual
    Given un usuario con 2+ membresías active, una de ellas la de su sesión actual
    When abre el selector de tenant
    Then el tenant activo actual aparece entre las opciones, marcado como seleccionado

  Scenario: La cola de aprobaciones no se filtra entre tenants
    Given la cola de aprobaciones cargando datos del tenant anterior
    When el usuario cambia de tenant antes de que esa petición resuelva
    Then la respuesta tardía del tenant anterior no altera la cola del tenant nuevo
```
