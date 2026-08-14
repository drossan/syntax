---
id: frontend-helpdesk-core-04
package: frontend
plan: helpdesk-core
status: done
priority: 2
depends_on: [frontend-helpdesk-core-03]
estimate: 3h
actual: 3h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# UI de contraseña e invitación (B.3)

## Description

Flujos de contraseña e invitación (promovido B.3): solicitar reset, fijar nueva contraseña vía token, y
aceptar una invitación fijando la contraseña inicial. Forms RHF+Zod contra los endpoints de contraseña.

## Spec

- Reset: form de email → `POST /auth/password/forgot` (respuesta neutra, no revela si el email existe).
- Set: página con token de URL → `POST /auth/password/reset` (validación de fuerza vía Zod).
- Invitación: página con token → fijar contraseña inicial → sesión iniciada o redirect a login.
- Errores mapeados con `problemToUi` (token inválido/caducado → mensaje claro).

## Fuera de alcance

- Envío real de email (stub del backend). Cambio de contraseña autenticado (puede ir en perfil, futuro).

## Scenarios (Gherkin)

```gherkin
Feature: Gestión de contraseña e invitación

  Scenario: Solicitud de reset con respuesta neutra
    Given una persona en la página de "olvidé mi contraseña"
    When solicita el reset para un email
    Then ve un mensaje neutro que no revela si el email está registrado

  Scenario: Fijar nueva contraseña con token válido
    Given un token de reset válido
    When fija una contraseña que cumple la política
    Then la contraseña queda actualizada y puede iniciar sesión

  Scenario: Token de reset caducado
    Given un token de reset caducado
    When intenta fijar una nueva contraseña
    Then ve un error claro de token inválido/caducado y se le ofrece re-solicitar

  Scenario: Aceptar invitación fija la contraseña inicial
    Given una invitación válida
    When la persona fija su contraseña inicial
    Then su cuenta queda activa
```

## Provides

- Páginas/forms de reset/set/invitación. Complementa el alta de usuarios del admin (17).

## Definition of Done

- [x] Tests ANTES (TDD); cada escenario con ≥1 test (incl. token caducado). 8 tests de forms (53 total).
- [x] Forms RHF+Zod + mapeo de errores; respuesta neutra en forgot.
- [x] Lint + typecheck OK; gate de mutation (92.20% ≥ 80, lógica `.ts`); estados error/éxito + a11y (role status/alert, aria-busy).
- [x] `Provides` disponible; `fact-checker` (10/10); docs 3 capas + session log.
