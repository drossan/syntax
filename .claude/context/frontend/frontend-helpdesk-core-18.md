# Session log — frontend-helpdesk-core-18 (Roles read-only + asignación de rol semilla)

## 2026-08-13 — arranque
- Gate TDD: `status: active`; depends_on [17, backend-02] en `done`; rama del plan. Baseline 246 tests.

### Decisiones de diseño
- Read-only: catálogo de roles (`GET /admin/roles`, reuso `useRoles` de 17) + capacidades (`GET /admin/capabilities`, `useCapabilities`). **Sin composer** (diferido C6) → placeholder que anuncia que llegará con el enforcement.
- Asignación de rol semilla: `PATCH /admin/users/{id}` {roles} → generalizo `useUpdateUser` (17) para aceptar `{status?, roles?}` (task 17 sigue verde: body {status} sin roles se preserva).
- Lógica pura `.ts` (mutación): `role-assignment.ts` → `addRole(current, roleId)` (sin duplicar), `removeRole`, `isSystemRole(kind)`.
- Presentación `.tsx`: `roles-catalog.tsx` (roles+capacidades read-only + placeholder composer), `role-assignment.tsx` (`<RoleAssignment user seedRoles>` → añade rol, PATCH). Página `app/(app)/admin/roles/page.tsx` guard `role.manage` (catálogo + asignación por usuario, reutilizando `useUsers`; vista de gestión de roles distinta de la de usuarios 17 para no colisionar).

## 2026-08-13 — cierre
- **Nuevos**: `src/features/admin/{role-ops.ts, roles-catalog.tsx, role-assignment.tsx}` + tests; página `app/(app)/admin/roles/page.tsx` (+guard test en admin-pages.test.tsx). **Modificados**: `use-admin.ts` (`useUpdateUser` acepta status?/roles?; eliminado `useCapabilities` no usado), `messages/{es,en}.json` (namespace adminRoles).
- **Renombre**: lógica pura `role-ops.ts` (no `role-assignment.ts`) para no colisionar con `role-assignment.tsx` (lección de la 15: `.ts`/`.tsx` no comparten basename).
- **Tests (salida real)**: `pnpm test` → **256 passed / 57 files** (258 tras añadir 2 guard tests de roles); typecheck limpio; lint `No issues found`.
- **Mutación**: Stryker sobre `role-ops.ts` + `use-admin.ts` → **88% ≥ 80** (role-ops 100%, use-admin 85.48%).
- **Fact-checker** (sonnet): **10/10 VERIFICADO**; se añadió el guard test de RolesPage que faltaba.
- **Alcance**: sin composer (placeholder que anuncia Fase 2 con enforcement). **Tiempo real**: ~1.1h.
