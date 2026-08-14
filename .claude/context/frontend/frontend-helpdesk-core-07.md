# Session log — frontend-helpdesk-core-07 (Bandeja de tickets)

## 2026-08-13 — arranque
- Gate TDD verificado: `status: active`; depends_on (06, backend-03, backend-06) en `done`; rama `plan/frontend/helpdesk-core`.
- Baseline verde: 71 tests / 17 files.
- Contexto leído en sesión: lifecycle, plan, HOW-TO, cross-cutting, api-contract (.yaml), rbac, coding-standards, código existente (client API, rbac, tenant, auth, shell, fixtures, handlers) y patrones de test (RTL+MSW, renderWithSession).

### Decisiones de diseño (task 07)
- Lógica en `.ts` (mutación Stryker solo cubre `.ts`; `.tsx` excluidos por config): `sla.ts`, `tickets-query.ts`, `use-tickets.ts`. Presentación en `.tsx`: `tickets-table.tsx`, `tickets-inbox.tsx`.
- **Gap de contrato reconocido**: `GET /tickets` (OpenAPI v0.1.0) NO expone `q` (búsqueda) ni `tag` ni parámetro de `tenant`. Se implementan solo filtros del contrato: `status`, `priority`, `domain`, `assignee_id`, `sort`, `page`, `page_size`. Búsqueda/tag → diferidos (no se inventan params). Aislamiento de tenant: el request NO lleva param de tenant; el server escopa por sujeto → un cliente no puede ampliar alcance. `activeTenantId` va solo en la queryKey (aislamiento de caché, cross-cutting §3).
- Orden por defecto `-updated_at` (contrato). Página fuera de rango → items vacíos → estado vacío sin error (rama "o el estado vacío" del refuerzo).
- SLA: `slaLevel(sla_due, now, window=1h)` → `none|normal|imminent|overdue`. Solo indicador visual (cómputo es backend, 18).
- TanStack Table v9 (`useTable`/`tableFeatures`/`createColumnHelper`/`table.FlexRender`) — API verificada en `node_modules/.../skills/getting-started`.

## 2026-08-13 — cierre
- **Ficheros nuevos**: `src/features/tickets/{sla.ts, sla-badge.tsx, tickets-query.ts, use-tickets.ts, tickets-table.tsx, tickets-inbox.tsx}` + tests `{sla.test.ts, tickets-query.test.ts, tickets-inbox.test.tsx}`.
- **Modificados**: `src/app/(app)/page.tsx` (home = bandeja, guard `ticket.read`) + su test; `src/test/render-with-session.tsx` (QueryClient de test con `retry:false` → rutas de error resuelven sin backoff x3); `messages/{es,en}.json` (namespace `tickets`).
- **Decisiones técnicas**:
  - `now` del SLA se lee una sola vez con `useState` lazy en `TicketsTable` (evita `Date.now()` en render → `react-hooks/purity`); `SlaBadge` recibe `now` como prop pura (determinista en tests).
  - Columnas dentro de `useMemo([effectiveNow])` porque el schema `Ticket` del contrato tiene todos los campos opcionales (`getValue()` → `T | undefined`), con guardas en las celdas.
  - `keepPreviousData` en `useTickets` → filtrar/paginar no parpadea a vacío.
- **Tests corridos (salida real en sesión)**: `pnpm test` → **96 passed / 20 files**; `pnpm typecheck` limpio; `pnpm lint` `No issues found`.
- **Gate de mutación**: Stryker sobre los 3 `.ts` → **98.04% ≥ 80** (sla.ts 95.45 / tickets-query.ts 100 / use-tickets.ts 100). 1 survivor en `sla.ts:22` (`if(!slaDue)`) = **mutante equivalente**: con `null`/`undefined`, `Date.parse` da NaN y la función devuelve `"none"` igualmente.
- **Gate fact-checker** (subagente sonnet, independiente): 9/10 VERIFICADO; 1 INCORRECTO = conteo obsoleto (dije 95, real 96) → corregido y re-ejecutado (96). Sin INCORRECTO pendiente.
- **Gap de contrato documentado**: `GET /tickets` no expone `q`/`tag`/tenant → búsqueda y filtro por tag diferidos (no se inventan params). Filtros implementados: status (UI) + priority/domain/assignee (contrato-listos en `buildTicketQuery`).
- **Tiempo real**: ~1.2h. **Follow-ups**: filtros priority/domain/assignee sin UI aún (solo status); búsqueda/tag esperan ampliación del contrato.
- **Docs**: TSDoc en todos los símbolos públicos; este session log; sin cambios de doc técnica de repo necesarios (specs ya cubren el contrato).
