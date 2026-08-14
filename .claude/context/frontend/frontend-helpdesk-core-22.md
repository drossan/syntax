# Session log — frontend-helpdesk-core-22 (Transversales de helpdesk)

## 2026-08-13 — arranque
- Gate TDD: `status: active`; depends_on [07, 08] en `done`; rama del plan. Baseline 274 tests.

### Decisiones de diseño
- Cuatro utilidades reutilizables (núcleo puro `.ts` → mutación; hooks/componentes finos):
  - **URL-state (T5)**: `lib/list-state.ts` (`readListState`/`writeListState` puros) + `useUrlListState`. En la bandeja: **lee el estado inicial de la URL** (compartible / sobrevive a recarga) y **escribe** los cambios (router.replace); el estado interno sigue gobernando la query (no rompe los tests de 07).
  - **No leído (T10)**: `lib/unread.ts` (`isUnread(updatedAt, lastVisit)` puro; ISO lexicográfico) + `useTicketReads` (store en localStorage). Indicador en la bandeja; el detalle (09) marca visitado al abrir. Gap: el contrato no expone "leído" server-side → derivación en cliente (documentada).
  - **Nav-guard (T6)**: `useUnsavedGuard(dirty)` (beforeunload). Aplicado al alta (08). Guard de nav soft en App Router: limitación documentada (beforeunload cubre recarga/cierre).
  - **Offline (T7)**: `useOnlineStatus()` + `OfflineBanner` (aviso global + invalida queries al reconectar → reintenta lecturas). En el app-shell.
- Ubicación: puros en `src/lib/`, hooks/componentes en `src/features/cross-cutting/`.

## 2026-08-13 — cierre
- **Nuevos**: `src/lib/{list-state.ts, unread.ts}` + tests; `src/features/cross-cutting/{use-online-status.ts, use-unsaved-guard.ts, use-ticket-reads.ts, use-url-list-state.ts, offline-banner.tsx}` + tests. **Modificados**: `tickets-inbox.tsx` (+useUrlListState +unread), `tickets-table.tsx` (+unreadIds/SubjectCell), `ticket-create-form.tsx` (+useUnsavedGuard), `ticket-detail.tsx` (+markVisited), `app-shell.tsx` (+OfflineBanner), `messages/{es,en}.json` (offline + tickets.unread), y los tests de bandeja/home (+mock next/navigation por useUrlListState).
- **Tests (salida real)**: `pnpm test` → **297 passed / 68 files**; typecheck limpio; lint `No issues found`.
- **Mutación**: Stryker sobre los 6 `.ts` → **82.61% ≥ 80** (lib 95%; hooks de API de navegador con survivors de wiring de listeners difíciles de matar en jsdom — el total supera el umbral).
- **Decisiones técnicas**: `useOnlineStatus` deja `setState` solo en handlers (no en cuerpo de efecto → `react-hooks/set-state-in-effect`); `useTicketReads` con `useSyncExternalStore` (lint-clean + sin mismatch de hidratación, snapshot de servidor vacío); `useUrlListState` mantiene estado interno inicializado desde la URL (re-render + testeable con mock estático).
- **Fact-checker** (sonnet): **11/11 VERIFICADO** (incl. sin dependencias nuevas).
- **Limitaciones documentadas**: nav-guard cubre recarga/cierre (beforeunload); el guard de nav *soft* del App Router queda pendiente de un hook estable del router. "Leído" derivado en cliente (localStorage) porque el contrato no lo expone server-side. **Tiempo real**: ~2h.
