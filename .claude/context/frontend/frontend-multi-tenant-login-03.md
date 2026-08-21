# Session log — `frontend-multi-tenant-login-03` — `Me.available_tenants` + `switchTenant`

> Append-only. Registro canónico de la tarea (task-lifecycle §Cerrar una tarea).

## 2026-08-21 — Arranque

- **Tarea 03** movida `pending → active`. `depends_on: [frontend-multi-tenant-login-01]` → `done`.
  Única tarea activa del plan.
- Alcance: `Me.available_tenants: TenantChoice[]` en el contrato (mismo patrón que
  `Me.active_tenant_id`, sin endpoint nuevo) + `auth-context.tsx`: `availableTenants` expuesto +
  `switchTenant(tenantId)` reutilizando `completeSession` (tarea `-01`). NO toca `tenant-context.tsx`/
  `TenantSwitcher` (eso es `-04`).

## 2026-08-21 — Implementación y cierre

### Qué se hizo

- **Contrato**: `api-contract.yaml` — `Me.available_tenants: TenantChoice[]`, añadido a `required`
  (mismo patrón que `active_tenant_id`). `pnpm gen:api` regeneró `src/types/api.ts` +
  `src/mocks/contract/openapi.json`. `meFixture()` (fixtures.ts) actualizado con un `available_tenants`
  por defecto (1 tenant, mismo `id` que `active_tenant_id`) — campo ahora requerido por el tipo.
  Un test preexistente (`tickets-inbox.test.tsx`) construía un `Me` literal sin pasar por `meFixture`;
  cambiado a `meFixture({...})` para que siga compilando (mismo dato, solo la vía de construcción).
- **TDD real**: tests de `switchTenant`/`availableTenants` escritos y corridos contra el `auth-context.tsx`
  de la tarea `-01`/`-02` (sin estos símbolos) → 5/5 en rojo (13 regresiones en verde); implementados
  `availableTenants` (estado + poblado en bootstrap/`completeSession`/reseteado en `logout`/`onLogout`)
  y `switchTenant(tenantId)` (`POST /auth/switch-tenant` → `completeSession` en éxito) → verde.
- **Bug real corregido durante el TDD** (no un mock defectuoso — reproducido con el test antes de
  tocar nada): un test de "fallo de `/auth/me` tras `switchTenant`" falló porque `completeSession`
  solo limpiaba `token`/`status` en su rama de error, dejando `user`/`sessionTenantId`/`capabilities`/
  `availableTenants` con los datos VIEJOS — inofensivo mientras solo lo llamaban `login`/`selectTenant`
  (ya `unauthenticated`, sin nada que limpiar), pero `switchTenant` se llama YA autenticado: sin este
  fix quedaba un estado a medias (`status: unauthenticated` con un `user` no nulo). Corregido: la rama
  de error de `completeSession` limpia las 4 piezas de estado de sesión, no solo el token.
- **Tests añadidos**: 5 en `auth-context.test.tsx` (los 4 escenarios Gherkin de la tarea + el body real
  enviado a `/auth/switch-tenant`) + mutation-hardening sobre código ya existente (availableTenants
  también limpiado en reuse-detection/logout, vía `Probe` con un nuevo `<span>avail:…</span>`).

### Verificación (comandos corridos en esta sesión)

- `pnpm exec vitest run` (repo frontend) → **68 ficheros, 321 tests, todos en verde**.
- `pnpm exec tsc --noEmit` → exit 0. Lint/prettier limpios.
- `pnpm exec stryker run --mutate "src/features/auth/auth-context.tsx"` → **98.81%** (76 killed, 7
  timeout, 1 survived — el mismo `if (!active) return` del bootstrap ya documentado en `-01`, no
  perseguido).
- Gate `sdd-lint`: sin artefactos SDD tocados (el contrato OpenAPI no es su ámbito) → limpio.
- Gate `fact-checker` (subagente fresco): **9/9 VERIFICADO** (incl. confirmación de que
  `gen:api:check` fallará hasta comitear/stagear los ficheros regenerados — esperado, no es un fallo
  real).

### Cierre

- Tarea `active → done` (`actual: 2h`), movida a `.claude/tasks/completed/frontend/`. Checkbox `[x]`
  en el plan.
- Commit `frontend-multi-tenant-login-03: ...` con el código + contrato + tipos regenerados +
  movimientos de tarea/session-log. Tras comitear, `pnpm gen:api:check` queda en verde (regenerar ==
  lo ya comiteado). `CU-FE-02` (aún de la tarea `-04`) y `backend/docs/domain-services-explicado.md`
  siguen sin comitear.
- **Follow-ups para `-04`**: `TenantSwitcher` debe leer `availableTenants` de `auth-context` (no de
  `use-tenants.ts`, que sigue sirviendo a `tenants-admin.tsx`) y usar `switchTenant`; `canSwitchTenant`
  pasa a `availableTenants.length > 1`.
