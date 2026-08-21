---
id: frontend-multi-tenant-login-01
package: frontend
plan: multi-tenant-login
status: done
priority: 1
depends_on: []
estimate: 2h
actual: 3h
created: 2026-08-21
updated: 2026-08-21
---

# auth-context: selección de tenant en login + `selectTenant` + helper común de sesión

## Description

`auth-context.tsx.login()` asume siempre `access_token`; hoy, ante `LoginTenantSelection` (2+
membresías `active`), devuelve un error fijo `"Selección de tenant no disponible"` (fix de drift de
una sesión anterior, PR #6). Esta tarea completa el flujo de verdad: `login()` devuelve la rama de
selección en vez de ese error, y se añade `selectTenant(identityToken, tenantId)` que canjea la
elección por una sesión real (`POST /auth/select-tenant`). Se extrae un helper común
(`completeSession`) que complete la sesión desde un `TokenResponse` — hoy usado por el tramo final de
`login()`, reutilizado por `selectTenant` aquí y por `switchTenant` en la tarea 03. `completeSession`
debe manejar el caso en que `GET /auth/me` falle pese a tener tokens válidos (hallazgo de
`scenario-coverage`, transversal a `-03`/`-04`): devuelve `{ error }` y NO marca `authenticated` — hoy
el código no tiene esa rama.

## Spec

`.claude/specs/frontend/casos-de-uso/CU-FE-01-login-y-sesion.md` (FR-003…FR-007, FR-028 de
`../spec.md`) — extensiones 1b/1c/1d/1g (1e/1f son de UI, tarea `-02`).

## Fuera de alcance

- La UI de selección (cards) — tarea `frontend-multi-tenant-login-02`.
- `switchTenant`/`available_tenants`/wiring del switcher — tareas `-03`/`-04`.
- Cambios al contrato: `LoginTenantSelection`, `TenantChoice` y `/auth/select-tenant` ya existen.
- Nueva ruta/URL para la pantalla de selección (descartado en el plan: el `identity_token` no debe
  viajar por URL/historial).

## Scenarios (Gherkin)

Fuente única (SDD): `CU-FE-01-login-y-sesion.md`, sección `## Criterios de aceptación (Gherkin)`.
Esta tarea cubre, a nivel **unit** (`auth-context.test.tsx`):

- `Login con 2+ tenants ofrece elegir uno` — `login()` devuelve `tenantSelection` (identity_token +
  tenants) en vez de completar la sesión, cuando el backend responde `LoginTenantSelection`.
- `Elegir un tenant completa la sesión` — `selectTenant(identityToken, tenantId)` en éxito deja
  `status: "authenticated"`, `user`, `sessionTenantId` poblados (mismo efecto que un login directo).
- `Error al elegir tenant permite reintentar sin volver a loguearse` — `selectTenant` en error
  (401/422) devuelve `{ error }` sin tocar el estado de sesión (sigue `unauthenticated`), y puede
  volver a llamarse con el MISMO `identityToken` (no se invalida en el cliente tras un fallo).
- `Fallo al confirmar la identidad tras tokens válidos no autentica` — con un `TokenResponse` válido
  (de `login()` o de `selectTenant`), si `GET /auth/me` falla, `completeSession` devuelve `{ error }`
  y el estado permanece `unauthenticated` (no queda un estado a medias con token pero sin sesión).

Los escenarios de `login-form.test.tsx`/`auth-context.test.tsx` ya existentes (login single-tenant,
bootstrap, logout) son regresión: deben seguir en verde sin modificarlos.

## Provides

- `useAuth().selectTenant(identityToken: string, tenantId: string): Promise<{ error?: Problem }>`.
- `login()` amplía su tipo de retorno con `tenantSelection?: { identityToken: string; tenants:
  TenantChoice[] }` (aditivo; el `{ error }` existente no cambia de forma).
- Helper interno `completeSession(tokenResponse)` — reutilizable por la tarea `-03` para
  `switchTenant`.

## Definition of Done

- [x] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [x] Cada escenario Gherkin tiene al menos un test (camino feliz + bordes/errores)
- [x] Todos los tests en verde
- [x] Spec cumplida; lo declarado en `Provides` queda disponible para las dependientes
- [x] Lint / format / typecheck OK
- [x] Gate de mutation testing superado (Stryker, umbral `break: 80`) — 98.61% (auth-context.tsx)
- [x] Gate de `sdd-lint` superado (spec/CU tocados en esta tarea) — 2 ERROR corregidos, 4 AVISO reconocidos
- [x] Gate de `fact-checker`: afirmaciones de la sesión verificadas (INCORRECTO bloquea) — 11/11 VERIFICADO
- [x] Documentación — TSDoc en símbolos públicos nuevos + CU-FE-01 ya extendido + session log
