# CU-BE-02 — Recuperación e invitación de contraseña

> **SDD** (Cockburn + Gherkin). CÓMO para FR-007…FR-009 de [`../spec.md`](../spec.md) (B.3). Datos:
> [`../data-model.md`](../data-model.md) §4.1 (`auth_token`). Email en **stub** en Fase 1.

- **Ámbito**: backend (API de auth / password)
- **Nivel**: objetivo de usuario
- **Actor primario**: usuario invitado o que olvidó su contraseña
- **Interesados e intereses**:
  - Usuario — recuperar el acceso o aceptar una invitación de forma segura.
  - Plataforma — tokens de un solo uso, caducables, sin filtrar existencia de cuentas.

## Precondiciones

- Existe un `user` (`invited` para invitación; cualquier estado con email para reset).

## Garantía mínima

- Un token inválido/caducado/usado no fija ninguna contraseña ni revela si el usuario existe.

## Garantía de éxito (postcondición)

- La contraseña queda fijada (Argon2id); el `auth_token` queda marcado `used_at`.

## Disparador

- Se solicita un reset (`/auth/forgot`) o un admin invita a un usuario.

## Escenario principal (éxito)

1. Se solicita reset / se crea una invitación.
2. El sistema emite un `auth_token` de un solo uso con caducidad y (stub) "envía" el correo.
3. El usuario canjea el token y fija su contraseña.
4. El sistema marca el token `used_at` y activa la cuenta si era `invited`.

## Extensiones (flujos alternativos y de error)

- **2a.** Email inexistente en reset: el sistema responde igual (no revela existencia); no emite token útil.
- **3a.** Token caducado o ya usado: el sistema rechaza el canje.
- **3b.** Token de otro `kind` (reset vs invitación) usado en el flujo equivocado: el sistema lo rechaza.

## Reglas de negocio

- **RN-1** — El `auth_token` se guarda **hasheado**, tiene `kind` (`password_reset|invitation`) y caducidad.
- **RN-2** — Canjear un token es **idempotente-seguro**: un segundo canje del mismo token falla (ya `used_at`).

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

  Scenario: Aceptación de invitación activa la cuenta
    Given un usuario en estado invitado con un token de invitación vigente
    When acepta la invitación fijando su contraseña
    Then la cuenta pasa a activa y el token queda usado

  Scenario: Solicitud de reset para un email inexistente no revela existencia
    Given un email que no corresponde a ninguna cuenta
    When se solicita un reset para ese email
    Then la respuesta es indistinguible de la de un email existente

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
