---
id: frontend-multi-tenant-login-04
package: frontend
plan: multi-tenant-login
status: pending
priority: 2
depends_on: [frontend-multi-tenant-login-03]
estimate: 4h
actual:
created: 2026-08-21
updated: 2026-08-21
---

# `tenant-context`/`TenantSwitcher`: switch real + visibilidad para cualquier usuario 2+ tenants + docs

## Description

Con `availableTenants`/`switchTenant` ya en `auth-context` (`-03`), esta tarea conecta el switcher de
verdad: `tenant-context.tsx` calcula `canSwitchTenant = availableTenants.length > 1` (ya no por
capacidad `global` — cualquier usuario con 2+ membresías lo ve); `setActiveTenant` pasa a ser async,
llama a `switchTenant`, y solo hace `queryClient.clear()` **tras éxito** (decisión de `grilling`: sin
optimismo — si falla, la vista se queda con los datos, válidos, del tenant anterior; el `<select>`
vuelve a mostrar el tenant anterior, nunca se queda en la opción fallida). Mientras el cambio está
pendiente, el `<select>` queda deshabilitado (no se puede elegir un segundo tenant a la vez).

**Corrección importante sobre `use-tenants.ts` (hallazgo de `scenario-coverage`, revierte una
verificación incorrecta de `design-review`/del plan original)**: NO se retira. Solo se deja de usar
desde `TenantSwitcher` (que pasa a leer `availableTenants`); `frontend/src/features/admin/
tenants-admin.tsx` importa el mismo hook (`useTenants` de `use-tenants.ts`, sobre `GET
/admin/tenants`) para la pantalla de administración de tenants y **debe seguir funcionando** sin
cambios.

**`use-approvals.ts` (hallazgo de `scenario-coverage`, decisión del owner)**: su `queryKey` no está
escopada por tenant, a diferencia de `use-tickets.ts`/`use-analytics.ts`, pese a que `CU-FE-02`
(RN-2/RN-4) ya promete invalidar la cola de aprobaciones al cambiar de tenant. Con el switch real
(clear solo tras éxito), una respuesta tardía de aprobaciones del tenant anterior podría pisar la
vista del nuevo — se corrige aquí, incluyendo el tenant en su `queryKey` igual que las demás.

También corrige un hallazgo de `design-review`: `subjectTenantId`/`activeTenantId` quedan siempre
iguales tras un switch real (`sessionTenantId` se re-deriva de un `/auth/me` fresco en cada
`completeSession`) — se actualizan los docstrings de `tenant-context.tsx` y de `hasCapability`
(`capabilities.ts`) para dejar de describirlos como valores que pueden diferir hoy; los campos NO se
colapsan (decisión explícita del plan, para no romper `use-can.ts`/`capabilities.ts`).

## Spec

`.claude/specs/frontend/casos-de-uso/CU-FE-02-rbac-cliente-y-cambio-de-tenant.md` (FR-008…FR-011,
RN-3, RN-4) — escenario principal 3, extensiones 3a/3b/3c/3d.

## Fuera de alcance

- `GET /admin/tenants` y la pantalla de administración de tenants (`admin/tenants/page.tsx`,
  `use-admin.ts`, `tenants-admin.tsx`) — sin tocar; siguen usando `use-tenants.ts` tal cual.
- Colapsar `subjectTenantId`/`activeTenantId` en un solo campo — solo se corrige la documentación,
  no la forma del `TenantContextValue`.
- E2E (Playwright) del flujo — opcional, fuera del gate por tarea.
- Integración RTL de punta a punta encadenando login-con-selección (`-01`/`-02`) → uso del switcher
  en la misma sesión — cada pieza se testea aislada (decisión del owner en `scenario-coverage`).
- Investigar la hipótesis (sin reproducir) de que cambiar de tenant en una pestaña pueda mover
  también a otra pestaña abierta vía el refresh compartido — anotada como riesgo conocido en el
  plan, no se investiga en esta tarea.

## Scenarios (Gherkin)

Fuente única (SDD): `CU-FE-02-rbac-cliente-y-cambio-de-tenant.md`. Esta tarea cubre, a nivel **RTL**
(`tenant-switcher.test.tsx`):

- `Cualquier usuario con 2+ tenants ve el selector` — un usuario **cliente** (no solo Soporte) con
  2 membresías ve el `<select>`; la fuente es `availableTenants` (`TenantSwitcher` deja de usar
  `useTenants`/`use-tenants.ts`, que sigue vivo para `tenants-admin.tsx`).
- `Con una sola membresía no hay selector que mostrar` — regresión explícita del caso actual (hoy
  ya pasa por capacidad; debe seguir pasando por conteo de tenants).
- `Cambiar de tenant falla sin alterar la vista actual` — elegir un tenant en el switcher, que
  `switchTenant` rechaza: la vista sigue mostrando los datos del tenant anterior, el `<select>`
  vuelve a mostrar esa opción, y aparece un aviso de error; la caché de Query **no** se limpia.
- `El selector se deshabilita mientras resuelve` — tras elegir un tenant, no se puede elegir otro a
  la vez hasta que el cambio resuelve.
- `El selector incluye el tenant activo actual` — a nivel RTL: el `<select>` muestra la opción del
  tenant en el que ya está la sesión, marcada como seleccionada.
- `La cola de aprobaciones no se filtra entre tenants` — con una petición de `use-approvals.ts` en
  vuelo del tenant anterior, si el switch tiene éxito antes de que resuelva, esa respuesta tardía no
  sobrescribe la cola del tenant nuevo (verifica el fix de `queryKey` de esta tarea).
- Regresión: el escenario ya existente de éxito (`tenant-switcher.test.tsx`) se extiende para
  aserear que, tras elegir un tenant, los datos que se cargan corresponden al tenant nuevo (hoy solo
  aserea que cambia el `value` del `<select>` — el gap que motivó este plan).

## Provides

- Switcher de tenant funcional end-to-end para cualquier usuario con 2+ membresías `active`.
- `use-approvals.ts` con `queryKey` escopada por tenant (igual que tickets/analytics).

## Definition of Done

- [ ] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [ ] Cada escenario Gherkin tiene al menos un test (camino feliz + bordes/errores)
- [ ] Todos los tests en verde
- [ ] Spec cumplida; lo declarado en `Provides` queda disponible para las dependientes
- [ ] Lint / format / typecheck OK
- [ ] Gate de mutation testing superado (Stryker, umbral `break: 80`)
- [ ] Gate de `sdd-lint` superado
- [ ] Gate de `fact-checker`: afirmaciones de la sesión verificadas (INCORRECTO bloquea)
- [ ] Documentación — TSDoc actualizado (incl. los docstrings corregidos de `subjectTenantId`/
  `activeTenantId`/`hasCapability`) + session log + cierre del plan (última tarea)
