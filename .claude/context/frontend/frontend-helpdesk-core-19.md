# Session log — frontend-helpdesk-core-19 (Dashboard / analytics)

## 2026-08-13 — arranque
- Gate TDD: `status: active`; depends_on [07, 13] en `done`; rama del plan. Baseline 258 tests.

### Notas de contrato / alcance
- `GET /analytics/summary` → `AnalyticsSummary` {tickets_by_status, approvals_pending, avg_confidence, sla_breaches}. **Sin params** de rango ni tenant → el server escopa por sujeto/tenant activo. La queryKey incluye `activeTenantId` (cross-cutting §3: al cambiar de tenant, refetch). Rango/export → fuera de alcance.

### Decisiones de diseño
- Lógica pura `.ts` (mutación): `analytics.ts` → `totalTickets(byStatus)`, `isEmptySummary(summary)`. Reuso `formatConfidencePercent` (ai-flow) para `avg_confidence` (no duplicar).
- Hook `.ts`: `use-analytics.ts` → `useAnalyticsSummary()` (queryKey `["analytics", activeTenantId]`).
- Presentación `.tsx`: `dashboard.tsx` (tarjetas de métricas + barras por estado accesibles, sin lib nueva; estados loading/empty/error). Página `app/(app)/dashboard/page.tsx` guard `analytics.read`.

## 2026-08-13 — cierre
- **Nuevos**: `src/features/analytics/{analytics.ts, use-analytics.ts, dashboard.tsx}` + tests; página `app/(app)/dashboard/{page.tsx,page.test.tsx}`. **Modificados**: `messages/{es,en}.json` (namespace dashboard).
- **Tests (salida real)**: `pnpm test` → **268 passed / 60 files**; typecheck limpio; lint `No issues found`.
- **Mutación**: Stryker sobre `analytics.ts` + `use-analytics.ts` → **88.46% ≥ 80** (analytics 100%; use-analytics 62.5% — 3 survivors en queryKey/throw inline, total supera el umbral).
- **Fact-checker** (sonnet): **10/10 VERIFICADO**. Reuso de `formatConfidencePercent` (ai-flow) confirmado sin duplicar.
- **Alcance**: rango/export fuera; el server escopa por tenant. **Tiempo real**: ~0.9h.
