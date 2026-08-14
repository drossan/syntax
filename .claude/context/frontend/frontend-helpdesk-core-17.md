# Session log — frontend-helpdesk-core-17 (Admin: tenants + usuarios + invitación)

## 2026-08-13 — arranque
- Gate TDD: `status: active`; depends_on [06, backend-02/03/06] en `done`; rama del plan. Baseline 226 tests.

### Notas de contrato / alcance
- Tenants: `GET /admin/tenants` + `POST /admin/tenants {slug,name}`. **NO hay DELETE ni PATCH de tenant** → el CRUD de tenants es list+create; el refuerzo "borrar tenant pide confirmación" no tiene endpoint → el patrón confirm-destructivo se realiza sobre **deshabilitar usuario** (`PATCH /admin/users/{id}` status=disabled, el único destructivo del contrato; "soft-delete = status disabled").
- Users: `GET /admin/users` (server-scoped por sujeto → un client_admin solo ve su tenant; el frontend no envía param de tenant), `POST /admin/users` (UserInvite {email, roles}), `PATCH /admin/users/{id}` (UserUpdate {status, roles}). `GET /admin/roles` para el selector de rol semilla.
- Reutilizo `useTenants` (features/tenant, del switcher 05) para el listado admin (no duplicar).

### Decisiones de diseño
- Lógica pura `.ts` (mutación): `admin-schemas.ts` → `tenantCreateSchema`, `userInviteSchema` + `toTenantCreateBody`, `toUserInviteBody` (roles: [roleId]).
- Hooks `.ts`: `use-admin.ts` → `useCreateTenant`, `useUsers`, `useInviteUser`, `useUpdateUser`, `useRoles` (invalidan las listas en éxito).
- Presentación `.tsx`: `tenants-admin.tsx` (lista + form create), `users-admin.tsx` (lista + invitar + deshabilitar con confirm). Páginas `admin/tenants` (guard `tenant.manage`) y `admin/users` (guard `user.manage`).

## 2026-08-13 — cierre
- **Nuevos**: `src/features/admin/{admin-schemas.ts, use-admin.ts, tenants-admin.tsx, users-admin.tsx}` + tests; páginas `app/(app)/admin/{tenants,users}/page.tsx` + `admin-pages.test.tsx`. **Modificados**: `confirm-dialog.tsx` (+labels opcionales, reuso sin duplicar), `messages/{es,en}.json` (namespaces adminTenants/adminUsers).
- **Tests (salida real)**: `pnpm test` → **246 passed / 54 files**; typecheck limpio; lint `No issues found`.
- **Mutación**: Stryker sobre `admin-schemas.ts` + `use-admin.ts` → **86.67% ≥ 80** (schemas 83.33%, hooks 87.72%). Requirió test unitario de los 5 hooks (bodies/params/invalidación/403) + casos de trim en schemas.
- **Fact-checker** (sonnet): **10/10 VERIFICADO** (confirma gap: no hay DELETE/PATCH de /admin/tenants/{id}).
- **Qué falta**: borrado/edición de tenant no está en el contrato → el confirm-destructivo se realiza sobre deshabilitar-usuario (soft-delete). **Tiempo real**: ~1.6h.
