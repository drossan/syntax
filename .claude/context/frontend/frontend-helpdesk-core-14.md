# Session log — frontend-helpdesk-core-14 (Ciclo de draft IA: disparo + polling)

## 2026-08-13 — arranque
- Gate TDD: `status: active`; depends_on [13] en `done`; rama del plan. Baseline 179 tests.

### Notas de contrato / alcance
- `POST /tickets/{id}/ai-draft` → 202 `AgentRun` (409 si ya hay run en curso, 429 rate-limit). `GET /agent-runs/{id}` → `AgentRun` (status queued|running|succeeded|failed, confidence, sources[], error, langsmith_trace_url). El contrato usa **`succeeded`** (la tarea decía "done").
- `AgentRun` **no** trae `draft_body` → el panel muestra estado + fuentes (citas) + confianza + traza; el texto del draft y aprobar/editar/rechazar son la **15** (sobre `ApprovalTask`).
- **Sin endpoint "run actual por ticket"** → tras recargar no se recupera el runId de un run en curso; el polling vive dentro de la sesión (documentado; Fase 1).

### Decisiones de diseño
- Lógica pura `.ts` (mutación): `agent-run.ts` → `isTerminal(status)`, `draftPollInterval(status, pollMs)` (false en terminal → para el polling), `formatConfidencePercent(confidence)`.
- Hooks `.ts`: `use-agent-draft.ts` → `useTriggerDraft(ticketId)` (POST), `useAgentRun(runId, pollMs)` (GET con `refetchInterval` que para en terminal).
- Presentación `.tsx`: `ai-draft-panel.tsx` (disparo gated por `agent.trigger`; estados sin-draft/generando(live-region)/listo/fallido+reintentar; botón deshabilitado mientras hay run activo → idempotencia). Integrado en `ticket-detail.tsx`.

## 2026-08-13 — cierre
- **Nuevos**: `src/features/ai-flow/{agent-run.ts, use-agent-draft.ts, ai-draft-panel.tsx}` + tests; fixture `agentRunFixture`. **Modificados**: `ticket-detail.tsx` (+panel), `messages/{es,en}.json` (namespace `aiDraft`).
- **Tests (salida real)**: `pnpm test` → **192 passed / 42 files**; typecheck limpio (corregido el tipado del default `status` en el test); lint `No issues found`.
- **Mutación**: Stryker sobre `agent-run.ts` + `use-agent-draft.ts` → **87.76% ≥ 80** (agent-run 100%; hook 77.78% — survivors en internals de react-query, total pasa). Polling probado con MSW stateful (running→running→succeeded) + parada en terminal.
- **Fact-checker** (sonnet): **10/10 VERIFICADO**.
- **Qué falta**: sin endpoint "run actual por ticket" → tras recargar no se recupera un run en curso (polling vive en la sesión). El texto del draft + aprobar/editar/rechazar son la 15. **Tiempo real**: ~1.2h.
