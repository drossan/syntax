# Session log — frontend-helpdesk-core-13 (Cola de aprobaciones)

## 2026-08-13 — arranque
- Gate TDD: `status: active`; depends_on [09, backend-05, backend-06] en `done`; rama del plan. Baseline 168 tests.

### Gap de contrato (alcance)
- `ApprovalTask` no trae `confidence`/`sla_due`/`domain` (solo `ticket_id`, `agent_run_id`, `status`, `draft_body`, `created_at`…). Confianza/SLA/dominio viven en `AgentRun`/`Ticket` (no embebidos). → La cola muestra ticket (link), preview del draft y fecha; el enriquecido (confianza/SLA por ítem) queda diferido para no forzar N+1. El **orden** es server-driven (`GET /approvals` default `sla_due,confidence`; contrato: paginación estable) → el frontend pide ese orden y renderiza en el orden recibido (no re-ordena).

### Decisiones de diseño
- Lógica pura `.ts` (mutación): `approvals-query.ts` → `buildApprovalsQuery({page})` (status=pending, sort=sla_due,confidence, page/page_size) + `approvalsQueryKey`.
- Hook `.ts`: `use-approvals.ts` → `useApprovals()`.
- Presentación `.tsx`: `approvals-queue.tsx` (lista + estados + botón refrescar). Página `app/(app)/approvals/page.tsx` guard `approval.decide` (el cliente no accede).

## 2026-08-13 — cierre
- **Nuevos**: `src/features/approvals/{approvals-query.ts, use-approvals.ts, approvals-queue.tsx}` + tests; `app/(app)/approvals/{page.tsx,page.test.tsx}`; fixtures `approvalTaskFixture`/`approvalPageFixture`. **Modificados**: `messages/{es,en}.json` (namespace `approvals`).
- **Tests (salida real)**: `pnpm test` → **179 passed / 39 files**; typecheck limpio; lint `No issues found`.
- **Mutación**: Stryker sobre `approvals-query.ts` + `use-approvals.ts` → **93.33% ≥ 80** (query 100%; hook 87.5% — 1 survivor `if(error) throw` = equivalente por react-query undefined→error).
- **Fact-checker** (sonnet): **9/9 VERIFICADO** (confirma el gap: ApprovalTask sin confidence/sla_due).
- **Qué falta**: enriquecido por ítem (confianza/SLA/dominio) diferido para no forzar N+1 hasta que el contrato lo embeba. **Tiempo real**: ~50min.
