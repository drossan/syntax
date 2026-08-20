# CU-BE-02 — Recuperación e invitación de contraseña

> **SDD** (Cockburn + Gherkin). CÓMO para FR-007…FR-009 de [`../spec.md`](../spec.md) (B.3), ampliado
> con `change_password` (plan 11/`backend-routers-core-02`). Datos: [`../data-model.md`](../data-model.md)
> §4.1 (`auth_token`, `user` global, `user_tenant`). Email en **stub** en Fase 1.

- **Ámbito**: backend (API de auth / password)
- **Nivel**: objetivo de usuario
- **Actor primario**: usuario invitado, que olvidó su contraseña, o que quiere cambiarla
- **Interesados e intereses**:
  - Usuario — recuperar el acceso, aceptar una invitación, o cambiar su contraseña de forma segura.
  - Plataforma — tokens de un solo uso, caducables, sin filtrar existencia de cuentas; contraseña
    **global** (una sola por usuario, compartida entre todas sus membresías de tenant).

## Precondiciones

- **Crear invitación**: existe (o se crea en el propio flujo) un `user` global identificado por email;
  no requiere una membership previa en el tenant que invita.
- **Aceptar invitación**: existe una `UserTenantMembership` `invited` con un token de invitación vigente.
- **Reset**: existe un `user` global con ese email (cualquier estado).
- **`change_password`**: el usuario está autenticado y tiene `password_hash` ya fijado.

## Garantía mínima

- Un token inválido/caducado/usado no fija ninguna contraseña ni revela si el usuario existe.
  `change_password` con la contraseña actual incorrecta no modifica nada.

## Garantía de éxito (postcondición)

- La contraseña global queda fijada (Argon2id); el `auth_token` queda marcado `used_at` (reset/
  invitación) o se actualiza directamente (`change_password`).

## Disparador

- Se solicita un reset (`/auth/password/forgot`), un admin invita a un usuario a un tenant, o un
  usuario autenticado pide `/auth/password/change`.

## Escenario principal (éxito)

1. Se solicita reset / se crea una invitación (a un tenant concreto) / el usuario autenticado pide
   cambiar su contraseña.
2. Reset/invitación: el sistema emite un `auth_token` de un solo uso con caducidad y (stub) "envía" el
   correo. `change_password`: el sistema verifica la contraseña actual en el momento.
3. El usuario canjea el token y fija su contraseña (reset/invitación), o la nueva se aplica
   directamente (`change_password`).
4. El sistema marca el token `used_at` y activa la membership invitada si aplica.

## Extensiones (flujos alternativos y de error)

- **1a.** El email invitado ya existe como `user` global: el sistema crea SOLO la
  `UserTenantMembership(invited)` en el tenant que invita, sin tocar su `password_hash` existente (una
  sola contraseña, compartida entre todas sus membresías).
- **2a.** Email inexistente en reset: el sistema responde igual (no revela existencia); no emite token útil.
- **3a.** Token caducado o ya usado: el sistema rechaza el canje.
- **3b.** Token de otro `kind` (reset vs invitación) usado en el flujo equivocado: el sistema lo rechaza.
- **3c.** `change_password` con la contraseña actual incorrecta: el sistema rechaza (`Validation`), sin
  modificar la contraseña.

## Reglas de negocio

- **RN-1** — El `auth_token` se guarda **hasheado**, tiene `kind` (`password_reset|invitation`) y caducidad.
- **RN-2** — Canjear un token es **idempotente-seguro**: un segundo canje del mismo token falla (ya `used_at`).
- **RN-3** — La contraseña es **global**: `accept_invitation`/`reset_password`/`change_password` la
  fijan para TODAS las membresías del usuario, nunca solo para un tenant.

## Criterios de aceptación (Gherkin)

```gherkin
Feature: Recuperación e invitación de contraseña

  Scenario: Solicitud de reset emite un token de un solo uso
    Given un usuario con una cuenta existente
    When solicita restablecer su contraseña
    Then se emite un token de un solo uso con caducidad y se notifica por el canal stub

  Scenario: Canje válido fija la contraseña
    Given un token de reset vigente y no usado
    When el usuario canjea el token con una contraseña nueva
    Then la contraseña queda fijada y el token queda marcado como usado

  Scenario: Aceptación de invitación fija la contraseña global y activa esa membership
    Given un usuario con una membership invited en un tenant y un token de invitación vigente
    When acepta la invitación fijando su contraseña
    Then la membership pasa a active, la contraseña global queda fijada y el token queda usado

  Scenario: Invitar un email que ya existe solo crea la membership, sin tocar su contraseña
    Given un email que ya es un usuario global con contraseña fijada, sin membership en el tenant B
    When se le invita al tenant B
    Then se crea la membership invited en B sin modificar su contraseña existente

  Scenario: Solicitud de reset para un email inexistente no revela existencia
    Given un email que no corresponde a ninguna cuenta
    When se solicita un reset para ese email
    Then la respuesta es indistinguible de la de un email existente

  Scenario: Cambiar la contraseña con la actual correcta la actualiza
    Given un usuario autenticado con contraseña conocida
    When solicita change_password con la contraseña actual correcta y una nueva
    Then su contraseña global se actualiza

  Scenario: Cambiar la contraseña con la actual incorrecta se rechaza
    Given un usuario autenticado con contraseña conocida
    When solicita change_password con la contraseña actual incorrecta
    Then se rechaza y la contraseña no cambia

  Scenario Outline: Canje de un token inutilizable se rechaza
    Given un token de contraseña <estado>
    When el usuario intenta canjearlo
    Then el canje se rechaza y la contraseña no cambia

    Examples:
      | estado     |
      | caducado   |
      | ya usado   |
      | de otro kind |
```
