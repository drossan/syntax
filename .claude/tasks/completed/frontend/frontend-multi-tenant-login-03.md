---
id: frontend-multi-tenant-login-03
package: frontend
plan: multi-tenant-login
status: done
priority: 2
depends_on: [frontend-multi-tenant-login-01]
estimate: 2h
actual: 2h
created: 2026-08-21
updated: 2026-08-21
---

# Contrato `Me.available_tenants` + `auth-context`: `availableTenants` expuesto + `switchTenant`

## Description

El switcher de tenant es hoy cosmético (`tenant-context.tsx`: `setActiveTenant` solo cambia un
`useState` local; nunca llama a `POST /auth/switch-tenant`, que ya existe en el contrato). Además,
solo lo ve Soporte (ámbito `global`), pero `data-model.md` (líneas 30, 75) confirma que `user_tenant`
(membership) es la misma tabla para cliente y Soporte — cualquier usuario con 2+ membresías tiene el
mismo problema.

Esta tarea prepara la base (sin tocar aún `tenant-context.tsx`/`TenantSwitcher`, eso es `-04`):
`Me` gana `available_tenants: TenantChoice[]` (mis propias membresías `active` en tenants
no-`disabled`, **incluido el tenant activo actual** — el switcher lo necesita para marcar la opción
seleccionada, hallazgo de `scenario-coverage`) en `api-contract.yaml` — mismo patrón que
`Me.active_tenant_id` (PR #6), NO un endpoint nuevo (evita crear un endpoint de auth desde un plan de
frontend; hallazgo de `design-review`). Como `Me` ya se pide siempre en el bootstrap y en
`completeSession` (login, `selectTenant`, `switchTenant`), `available_tenants` llega gratis, sin
petición adicional. Se añade `switchTenant(tenantId)` en `auth-context.tsx`, reutilizando
`completeSession` (de la tarea `-01`, ya con su manejo de fallo de `/auth/me` tras tokens válidos).

## Spec

`.claude/specs/frontend/casos-de-uso/CU-FE-02-rbac-cliente-y-cambio-de-tenant.md` (FR-008…FR-011) —
escenario principal 3, extensiones 3a/3b/3c/3e, RN-3.

## Fuera de alcance

- Wiring de `tenant-context.tsx`/`TenantSwitcher` (visibilidad, estado pendiente/error, sustituir
  `use-tenants.ts`) — tarea `-04`.
- `GET /admin/tenants` y la pantalla de administración de tenants — sin tocar.
- Refrescar `available_tenants` fuera de un login/select/switch/bootstrap — riesgo aceptado,
  documentado en el plan (no se resuelve aquí).

## Scenarios (Gherkin)

Fuente única (SDD): `CU-FE-02-rbac-cliente-y-cambio-de-tenant.md`. Esta tarea cubre, a nivel **unit**
(`auth-context.test.tsx`):

- `Cualquier usuario con 2+ tenants ve el selector` (la parte de datos: tras el bootstrap/login,
  `availableTenants` contiene las membresías `active` del usuario — la parte de UI es `-04`).
- `Con una sola membresía no hay selector que mostrar` (`availableTenants` con longitud 1).
- `Cambiar de tenant falla sin alterar la vista actual` — `switchTenant(tenantId)` en error (401/403)
  devuelve `{ error }` sin tocar `sessionTenantId`/`user`/`capabilities` (la sesión sigue en el
  tenant anterior); en éxito, los actualiza igual que `completeSession`.
- `El selector incluye el tenant activo actual` — `availableTenants` contiene el `TenantChoice` del
  tenant en el que ya está la sesión, no solo los demás.

## Provides

- `Me.available_tenants: TenantChoice[]` en el contrato/tipos generados (`src/types/api.ts`,
  `src/mocks/contract/openapi.json`).
- `useAuth().availableTenants: TenantChoice[]`.
- `useAuth().switchTenant(tenantId: string): Promise<{ error?: Problem }>`.

## Definition of Done

- [x] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [x] Cada escenario Gherkin tiene al menos un test (camino feliz + bordes/errores)
- [x] Todos los tests en verde
- [x] Spec cumplida; lo declarado en `Provides` queda disponible para las dependientes
- [x] Lint / format / typecheck OK; `pnpm gen:api:check` en verde (contrato == generado == commiteado)
- [x] Gate de mutation testing superado (Stryker, umbral `break: 80`) — 98.81%
- [x] Gate de `sdd-lint` superado — sin artefactos SDD tocados
- [x] Gate de `fact-checker`: afirmaciones de la sesión verificadas (INCORRECTO bloquea) — 9/9 VERIFICADO
- [x] Documentación — TSDoc en símbolos públicos nuevos + session log
