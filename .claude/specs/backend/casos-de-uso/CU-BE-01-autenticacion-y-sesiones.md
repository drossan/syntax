# CU-BE-01 — Autenticación y sesiones

> **SDD** (Cockburn *fully-dressed* + Gherkin). CÓMO del actor para las user stories de auth de
> [`../spec.md`](../spec.md) (FR-001…FR-006, ampliadas por el rediseño de identidad multi-tenant,
> plan 11/`backend-routers-core`). Decisión:
> [[../../adr/0004-auth-jwt-access-memoria-refresh-cookie-rotacion]]. Detalle de datos:
> [`../data-model.md`](../data-model.md) §4.1 (`user` global, `user_tenant`, `refresh_session`).

- **Ámbito**: backend (API de auth)
- **Nivel**: objetivo de usuario
- **Actor primario**: usuario autenticable (cliente o Soporte), que puede pertenecer a **varios
  tenants** con una sola contraseña
- **Interesados e intereses**:
  - Usuario — entrar y permanecer con sesión sin re-loguear cada poco; elegir tenant sin fricción si
    pertenece a varios.
  - Plataforma — sesiones revocables, robo de refresh detectable, logout durable.

## Precondiciones

- El usuario existe (identidad global) con `password_hash` fijado y al menos una `UserTenantMembership`
  en estado `active` de un tenant no `disabled`.

## Garantía mínima

- Un intento fallido no altera la sesión vigente ni revela si el email existe ni en qué tenants tiene
  membership.

## Garantía de éxito (postcondición)

- El sujeto tiene un access válido (memoria) y un refresh rotatorio en cookie httpOnly **para un tenant
  concreto**; la sesión es revocable server-side.

## Disparador

- El usuario envía credenciales a `/auth/login` (sin tenant), elige tenant en `/auth/select-tenant` o
  `/auth/switch-tenant`, o el cliente refresca/cierra sesión.

## Escenario principal (éxito)

1. El usuario presenta email + contraseña válidos (sin tenant).
2. El sistema verifica el hash (Argon2id) global y cuenta sus membresías `active` en tenants no
   `disabled`: con **una sola**, emite access (Bearer, TTL corto, sin capacidades) + refresh en cookie
   httpOnly para ESE tenant, igual que antes.
3. Al expirar el access, el cliente presenta el refresh; el sistema lo **rota** (mismo tenant) y emite
   un access nuevo.
4. El usuario cierra sesión; el sistema **revoca** el refresh vigente server-side.

## Extensiones (flujos alternativos y de error)

- **1a.** Credenciales inválidas: el sistema deniega con error genérico (no revela existencia del usuario).
- **1b.** Demasiados intentos: el sistema aplica throttling de login (B.1).
- **2a.** El usuario tiene **2+ membresías `active`** en tenants no-`disabled`: el sistema emite un
  `identity_token` corto (`purpose=tenant_selection`, reutilizable dentro de su TTL) + la lista de esos
  tenants, **sin** refresh-cookie. El usuario elige uno con `POST /auth/select-tenant`, que valida de
  nuevo la membership `active` + tenant no-`disabled` y emite el `TokenResponse` real de 2.
- **2b.** El usuario **no tiene ninguna** membership `active` en un tenant no-`disabled` (0 tras el
  filtro): el sistema deniega con el MISMO error genérico que credenciales inválidas.
- **2c.** Con una sesión ya autenticada, el usuario cambia a otra de sus membresías con
  `POST /auth/switch-tenant` (access token válido, sin repetir credenciales) — mismas validaciones de
  membership `active` + tenant no-`disabled` que `select-tenant`.
- **3a.** Refresh ya `rotated`/`revoked` reaparece: el sistema revoca **toda la `family_id`** (reuse-detection) y deniega.
- **3b.** Refresh caducado: el sistema deniega y exige re-login.

## Reglas de negocio

- **RN-1** — El access **no** porta capacidades; se resuelven server-side por request (FR-005).
- **RN-2** — El refresh se guarda **hasheado**; la rotación encadena `parent_id` dentro de `family_id`.
- **RN-3** — El `identity_token` (`purpose=tenant_selection`) nunca lleva `tenant_id` ni emite
  refresh-cookie; es **reutilizable** dentro de su TTL corto (no de un solo uso).

## Criterios de aceptación (Gherkin)

```gherkin
Feature: Autenticación y sesiones

  Scenario: Login con credenciales válidas y una sola membership activa
    Given un usuario activo con contraseña fijada y UNA membership active
    When inicia sesión con sus credenciales correctas
    Then obtiene un access token de vida corta y una sesión de refresh httpOnly para ese tenant

  Scenario: Login con credenciales inválidas
    Given un usuario activo
    When intenta iniciar sesión con una contraseña incorrecta
    Then la autenticación se rechaza con un error genérico que no revela si el email existe

  Scenario: Login con varias membresías activas emite un identity_token
    Given un usuario con DOS membresías active en tenants distintos
    When inicia sesión con sus credenciales correctas
    Then recibe un identity_token corto y la lista de esos tenants, sin refresh-cookie

  Scenario: Login sin ninguna membership activa se rechaza con el mismo error genérico
    Given un usuario activo sin ninguna membership active en un tenant no-disabled
    When inicia sesión con sus credenciales correctas
    Then se rechaza con el mismo error genérico que unas credenciales inválidas

  Scenario: Selección de tenant tras el identity_token
    Given un identity_token válido de un usuario con membresías active en los tenants A y B
    When selecciona el tenant A con /auth/select-tenant
    Then recibe el TokenResponse real (access + refresh-cookie) para el tenant A

  Scenario: Cambio de tenant con una sesión ya activa
    Given un access token válido de un usuario con membership active en los tenants A y B
    When llama a /auth/switch-tenant con el tenant B
    Then recibe tokens nuevos para el tenant B, sin repetir credenciales

  Scenario: Rotación del refresh
    Given una sesión con un refresh token vigente
    When el cliente renueva la sesión con ese refresh
    Then el refresh anterior queda rotado y se emite un access nuevo

  Scenario: Reuse-detection de un refresh robado
    Given un refresh token que ya fue rotado
    When se presenta de nuevo ese refresh ya rotado
    Then toda la familia de refresh se revoca y la sesión se deniega

  Scenario: Refresh caducado exige re-login sin activar reuse-detection
    Given una sesión de refresh activa cuyo expires_at ya pasó
    When el cliente intenta renovar la sesión con ese refresh
    Then el sistema deniega y exige iniciar sesión de nuevo, sin revocar la family_id

  Scenario: Logout revoca la sesión server-side
    Given una sesión activa
    When el usuario cierra sesión
    Then el refresh vigente queda revocado y no puede renovar de nuevo

  Scenario: Throttling tras varios fallos de login
    Given un usuario que ha superado el número de intentos permitidos
    When vuelve a intentar iniciar sesión
    Then el sistema limita el intento por throttling
```
