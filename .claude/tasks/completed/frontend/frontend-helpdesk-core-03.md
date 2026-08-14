---
id: frontend-helpdesk-core-03
package: frontend
plan: helpdesk-core
status: done
priority: 1
depends_on: [frontend-helpdesk-core-02, backend-skeleton-foundation-06]
estimate: 4h
actual: 5h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# Auth core (login, middleware, refresh single-flight)

## Description

Autenticación usuario/contraseña y ciclo de sesión: login, `middleware.ts` (redirect por cookie refresh),
bootstrap del access token vía `/auth/refresh`, interceptor 401 con **single-flight**, y contexto/hooks de
sesión. App **client-rendered** (el access token vive en memoria).

## Spec

- Login (RHF+Zod) → `POST /auth/login`; access token en memoria (contexto), refresh en cookie httpOnly.
- `middleware.ts`: si no hay cookie refresh en rutas protegidas → redirect a `/login` (redirect UX, no seguridad).
- Bootstrap: al montar la app, `POST /auth/refresh` para obtener access; si falla → estado no-autenticado.
- **Interceptor 401 single-flight**: N peticiones con 401 concurrente disparan **una sola** renovación; se
  reintentan todas al terminar. **Reuse-detection** (401 de refresh) → logout limpio + redirect a `/login`.
- Contexto `useAuth()` (sesión, capacidades, tenant) + `useLogout()`.

## Fuera de alcance

- UI de contraseña/invitación (tarea 04). RBAC de menús/rutas (05). SSO (Fase 2).

## Scenarios (Gherkin)

```gherkin
Feature: Autenticación y sesión

  Scenario: Login correcto abre sesión
    Given un usuario con credenciales válidas
    When inicia sesión
    Then queda autenticado y es llevado a la bandeja

  Scenario: Acceso a ruta protegida sin sesión
    Given una visita sin cookie de refresh
    When solicita una ruta protegida
    Then es redirigida a /login

  Scenario: Un access expirado se renueva una sola vez ante peticiones concurrentes
    Given una sesión cuyo access token ha expirado
    And tres peticiones autenticadas se lanzan a la vez
    When todas reciben 401
    Then se ejecuta exactamente un /auth/refresh y las tres peticiones se reintentan con el nuevo token

  Scenario: Reuse-detection cierra la sesión
    Given un refresh token invalidado por reuse-detection
    When la app intenta renovar el access token
    Then la sesión se cierra limpia y la persona es llevada a /login
```

## Provides

- `useAuth()`, `useLogout()`, `middleware.ts`, cliente con interceptor de refresh. 04/05 y toda ruta
  protegida dependen de esta sesión.

## Definition of Done

- [x] Tests ANTES (TDD); cada escenario con ≥1 test (incl. single-flight y reuse-detection con MSW stateful). 45 tests verdes.
- [x] Middleware, bootstrap y contexto según Spec; app client-rendered.
- [x] Lint + typecheck OK; gate de mutation (92.20% ≥ break 80); estados error/loading (login-form aria-busy/alert).
- [x] `Provides` disponible; `fact-checker` (13/13 VERIFICADO); docs 3 capas + session log.
