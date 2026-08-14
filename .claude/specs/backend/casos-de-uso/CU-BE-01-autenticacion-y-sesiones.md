# CU-BE-01 — Autenticación y sesiones

> **SDD** (Cockburn *fully-dressed* + Gherkin). CÓMO del actor para las user stories de auth de
> [`../spec.md`](../spec.md) (FR-001…FR-006). Decisión:
> [[../../adr/0004-auth-jwt-access-memoria-refresh-cookie-rotacion]]. Detalle de datos:
> [`../data-model.md`](../data-model.md) §4.1 (`refresh_session`).

- **Ámbito**: backend (API de auth)
- **Nivel**: objetivo de usuario
- **Actor primario**: usuario autenticable (cliente o Soporte)
- **Interesados e intereses**:
  - Usuario — entrar y permanecer con sesión sin re-loguear cada poco.
  - Plataforma — sesiones revocables, robo de refresh detectable, logout durable.

## Precondiciones

- El usuario existe con `status=active` y `password_hash` fijado.

## Garantía mínima

- Un intento fallido no altera la sesión vigente ni revela si el email existe.

## Garantía de éxito (postcondición)

- El sujeto tiene un access válido (memoria) y un refresh rotatorio en cookie httpOnly; la sesión es
  revocable server-side.

## Disparador

- El usuario envía credenciales a `/auth/login`, o el cliente refresca/cierra sesión.

## Escenario principal (éxito)

1. El usuario presenta email + contraseña válidos.
2. El sistema verifica el hash (Argon2id) y emite access (Bearer, TTL corto, sin capacidades) + refresh en cookie httpOnly.
3. Al expirar el access, el cliente presenta el refresh; el sistema lo **rota** y emite un access nuevo.
4. El usuario cierra sesión; el sistema **revoca** el refresh vigente server-side.

## Extensiones (flujos alternativos y de error)

- **1a.** Credenciales inválidas: el sistema deniega con error genérico (no revela existencia del usuario).
- **1b.** Demasiados intentos: el sistema aplica throttling de login (B.1).
- **3a.** Refresh ya `rotated`/`revoked` reaparece: el sistema revoca **toda la `family_id`** (reuse-detection) y deniega.
- **3b.** Refresh caducado: el sistema deniega y exige re-login.

## Reglas de negocio

- **RN-1** — El access **no** porta capacidades; se resuelven server-side por request (FR-005).
- **RN-2** — El refresh se guarda **hasheado**; la rotación encadena `parent_id` dentro de `family_id`.

## Criterios de aceptación (Gherkin)

```gherkin
Feature: Autenticación y sesiones

  Scenario: Login con credenciales válidas
    Given un usuario activo con contraseña fijada
    When inicia sesión con sus credenciales correctas
    Then obtiene un access token de vida corta y una sesión de refresh httpOnly

  Scenario: Login con credenciales inválidas
    Given un usuario activo
    When intenta iniciar sesión con una contraseña incorrecta
    Then la autenticación se rechaza con un error genérico que no revela si el email existe

  Scenario: Rotación del refresh
    Given una sesión con un refresh token vigente
    When el cliente renueva la sesión con ese refresh
    Then el refresh anterior queda rotado y se emite un access nuevo

  Scenario: Reuse-detection de un refresh robado
    Given un refresh token que ya fue rotado
    When se presenta de nuevo ese refresh ya rotado
    Then toda la familia de refresh se revoca y la sesión se deniega

  Scenario: Logout revoca la sesión server-side
    Given una sesión activa
    When el usuario cierra sesión
    Then el refresh vigente queda revocado y no puede renovar de nuevo

  Scenario: Throttling tras varios fallos de login
    Given un usuario que ha superado el número de intentos permitidos
    When vuelve a intentar iniciar sesión
    Then el sistema limita el intento por throttling
```
