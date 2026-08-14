# Session log — `frontend-helpdesk-core-05` — RBAC en cliente + contexto de tenant + switcher

> Append-only. Registro canónico de la tarea (task-lifecycle §Cerrar una tarea).

## 2026-08-13 — Ejecución

### Precondición y modelo

- `depends_on`: `frontend-helpdesk-core-03` (done) + `backend-skeleton-foundation-02` (done). Modelo
  `rbac.md`: **capacidad + ámbito** (`tenant`/`global`); Soporte (Syntax) = ámbito global cross-tenant;
  cliente = tenant fijo. **Fail-closed** (§8): sin capacidades resueltas → deny. La sesión (03) ya expone
  `capabilities: [{capability, scope}]` (de `GET /auth/me`).

### Qué se hizo (TDD rojo→verde)

- **`hasCapability(capabilities, capability, {resourceTenantId?, context})`** (`features/rbac/
  capabilities.ts`, lógica pura): decide por capacidad+ámbito, nunca por rol. `null`/`undefined`/ausente
  → deny (fail-closed). `global` aplica cross-tenant; `tenant` solo dentro del tenant del sujeto y sobre
  recursos de ESE tenant.
- **`useCan(capability, {resourceTenantId?})`** (hook) + **`<Can>`** (wrapper de acción) + **`<RequireCapability>`**
  (guard de ruta → `<AccessDenied>`).
- **`TenantProvider` / `useTenant()`**: `subjectTenantId` (= `user.tenant_id`), `activeTenantId`,
  `canSwitchTenant` (= alguna capacidad `global`), `setActiveTenant` (no-op para clientes; al cambiar
  resetea la caché de Query — cross-cutting §3).
- **`TenantSwitcher`**: visible solo si `canSwitchTenant`; lista tenants vía `useTenants()` (`GET
  /admin/tenants`, TanStack Query); el cliente no lo ve.
- **Wiring**: `TenantProvider` añadido a `providers.tsx` (dentro de `AuthProvider`); **el auth-context
  ahora expone `client`** (el openapi-fetch autenticado) para el data-fetching de las features.

### Escenarios Gherkin → tests (1:1)

- «acción oculta sin capacidad» / «con capacidad» → `can.test.tsx`.
- «ruta sin capacidad → acceso denegado» → `can.test.tsx` (`RequireCapability`).
- «Soporte cambia de tenant» → `tenant-switcher.test.tsx` (select cambia el tenant activo).
- «cliente fijado a su tenant, no ve el switcher» → `tenant-switcher.test.tsx`.
- Refuerzos scenario-coverage: fail-closed, ámbito global cross-tenant, ámbito tenant NO aplica a otro
  tenant, subject nulo → `capabilities.test.ts` (7 casos, lógica pura).

### Verificación (comandos corridos en esta sesión)

- `pnpm --filter frontend test` → **66 passed (14 ficheros)**.
- `tsc --noEmit` → 0. `eslint` → 0/0. `prettier --check .` → limpio.
- `stryker run` → **90.76%** (break 80): capabilities.ts 96.67; use-can/use-tenants más bajos (plumbing
  de hooks de fetch, cubierto por RTL). `.tsx` excluidos (política task 03).
- `next build` → OK.

### Decisiones técnicas y gaps

- **Gap de contrato (anotado)**: `GET /admin/tenants` exige `tenant.manage`, pero un `support_agent`
  (ámbito global) **sin** `tenant.manage` no puede listar tenants para el switcher. La visibilidad del
  switcher se decide por ámbito global; la lista por el endpoint. Un Soporte global sin `tenant.manage`
  recibiría 403 → lista vacía (fail-closed). **A resolver en backend** (endpoint de tenants para Soporte).
- `setActiveTenant` resetea la caché de Query (`queryClient.clear()`) — simple y seguro mientras no haya
  queries por-tenant; cuando las haya (07+), se puede afinar a `invalidateQueries` por clave.
- Helper de test compartido `src/test/render-with-session.tsx` (monta MSW de bootstrap + providers) —
  lo reutilizarán las tareas de feature.

### Cierre

- **Gate `fact-checker`** (subagente fresco, sonnet): **13/13 VERIFICADO** (ejecutó test/tsc/eslint/
  prettier/stryker/build). 0 INCORRECTO, 0 NO VERIFICABLE.
- Tarea `active → done` (`actual: 4h`), movida a `completed/`; `[x]` en el plan; commit
  `frontend-helpdesk-core-05: …`.
