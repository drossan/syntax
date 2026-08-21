# CU-FE-01 — Login y sesión de cliente

> **SDD** (Cockburn + Gherkin). CÓMO para FR-003…FR-007, FR-028 de [`../spec.md`](../spec.md). Decisiones:
> [[../../adr/0003-frontend-spa-client-rendered]], [[../../adr/0004-auth-jwt-access-memoria-refresh-cookie-rotacion]].
> Backend: [CU-BE-01](../../backend/casos-de-uso/CU-BE-01-autenticacion-y-sesiones.md).

- **Ámbito**: frontend (auth core)
- **Nivel**: objetivo de usuario
- **Actor primario**: usuario/agente
- **Interesados e intereses**:
  - Usuario — entrar y no ser expulsado por expiraciones de token.
  - Plataforma cliente — no exponer el token ni dejar datos de sesión tras el logout.

## Precondiciones

- La app está cargada; el usuario tiene credenciales válidas o una cookie refresh vigente.

## Garantía mínima

- El access token nunca se persiste en almacenamiento legible; ante fallo de sesión no se muestran datos privados.

## Garantía de éxito (postcondición)

- El usuario navega autenticado; la sesión se renueva de forma transparente; el logout limpia el estado.

## Disparador

- El usuario inicia sesión, o el bootstrap detecta la cookie refresh, o expira un access.

## Escenario principal (éxito)

1. El usuario inicia sesión; el access queda en memoria.
2. Al arrancar con cookie refresh, la app hace bootstrap `/auth/refresh` y entra sin re-login.
3. Al expirar el access, el interceptor renueva y reintenta la petición.
4. El usuario cierra sesión; la app resetea el `queryClient` y detiene el polling.

## Extensiones (flujos alternativos y de error)

- **1a.** Ruta privada sin cookie refresh: el `middleware.ts` redirige al login (UX, no seguridad).
- **1b.** El usuario tiene **2+ membresías `active`** en tenants distintos: en vez de entrar
  directamente, la app ofrece elegir uno de los tenants disponibles (sin cookie de refresh todavía).
- **1c.** Tras elegir un tenant, la app completa la sesión igual que en el login de un solo tenant.
- **1d.** Elegir un tenant es rechazado (token de elección inválido/caducado, o la membership dejó de
  estar `active`): la app informa el error sobre la propia pantalla de elección — no vuelve al
  formulario de login ni descarta las demás opciones —, y el usuario puede reintentar o volver a
  iniciar sesión desde ahí (botón visible solo tras ese error, que descarta la elección en curso).
- **1e.** Mientras se resuelve una elección de tenant, la pantalla queda deshabilitada (no se puede
  elegir un segundo tenant a la vez ni repetir la misma elección con un doble click).
- **1f.** El usuario recarga la página (o navega directo a la URL) estando en la pantalla de
  elección de tenant: al no existir una ruta propia para ese paso, la app degrada al formulario de
  login en vez de romperse.
- **1g.** Al completar la sesión (login directo o tras elegir tenant), la consulta de la identidad
  (`/auth/me`) falla pese a tener tokens válidos: la app **no** marca la sesión como autenticada y
  lo trata como un error de login, sin dejar un estado a medias.
- **3a.** **N 401 concurrentes**: el interceptor renueva **una sola vez** (single-flight) y reintenta todas.
- **3b.** Reuse-detection en la renovación (refresh robado): la app hace **logout limpio**.

## Reglas de negocio

- **RN-1** — Todo dato privado se pide client-side vía TanStack Query + cliente tipado.
- **RN-2** — El logout es un límite de caché: no deben sobrevivir datos de la sesión anterior.

## Criterios de aceptación (Gherkin)

```gherkin
Feature: Login y sesión de cliente

  Scenario: Login exitoso
    Given un usuario con credenciales válidas
    When inicia sesión
    Then accede a la aplicación autenticado

  Scenario: Reanudación de sesión al arrancar
    Given un usuario con una sesión de refresh vigente
    When abre la aplicación
    Then entra sin volver a introducir credenciales

  Scenario: Renovación única ante 401 concurrentes
    Given una sesión cuyo access token ha expirado
    When se disparan varias peticiones que reciben 401 a la vez
    Then la sesión se renueva una sola vez y las peticiones se reintentan

  Scenario: Reuse-detection cierra la sesión
    Given una renovación que detecta un refresh comprometido
    When falla la renovación por reuse-detection
    Then la aplicación cierra la sesión de forma limpia

  Scenario: Logout limpia el estado
    Given un usuario con datos cargados en caché
    When cierra sesión
    Then la caché de datos se resetea y el polling se detiene

  Scenario: Redirect por ruta privada sin sesión
    Given un visitante sin cookie de refresh
    When intenta abrir una ruta privada
    Then es redirigido a la pantalla de login

  Scenario: Login con 2+ tenants ofrece elegir uno
    Given un usuario con 2+ membresías active en tenants distintos
    When inicia sesión con sus credenciales correctas
    Then puede elegir uno de los tenants disponibles antes de entrar

  Scenario: Elegir un tenant completa la sesión
    Given un usuario que acaba de elegir un tenant tras el login
    When la elección se confirma
    Then accede a la aplicación autenticado en ese tenant

  Scenario: Error al elegir tenant permite reintentar sin volver a loguearse
    Given un usuario en la pantalla de elección de tenant
    When la elección de un tenant es rechazada
    Then ve un aviso del error, con un botón para volver al login, y puede reintentar

  Scenario: Volver al login desde la pantalla de elección tras un error
    Given un usuario que ve el aviso de error tras una elección rechazada
    When decide volver a iniciar sesión
    Then vuelve al formulario de login y se descarta la elección en curso

  Scenario: La pantalla de elección se deshabilita mientras resuelve
    Given un usuario que acaba de elegir un tenant
    When la elección todavía no se ha resuelto
    Then no puede elegir otro tenant ni repetir la misma elección a la vez

  Scenario: Recargar en la pantalla de elección degrada al login
    Given un usuario en la pantalla de elección de tenant
    When recarga la página
    Then vuelve al formulario de login en vez de romperse

  Scenario: Fallo al confirmar la identidad tras tokens válidos no autentica
    Given un login o una elección de tenant que obtuvo tokens válidos
    When la consulta de la identidad del usuario falla
    Then la sesión no se marca como autenticada y se trata como un error de login
```
