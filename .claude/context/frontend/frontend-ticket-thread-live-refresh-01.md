# Session log — frontend-ticket-thread-live-refresh-01

## 2026-08-31
- Verificado antes de implementar: `useTicketMessages`/`useTicket` (`use-ticket.ts`) usan claves
  `["ticket", activeTenantId, ticketId, ...]` — el prefijo `["ticket"]` invalida ambas. Patrón ya
  probado en `use-approval-decision.ts:25`.
- Red: 15 tests nuevos en `ai-draft-panel.test.tsx` (Gherkin 5a-5e: transición a `succeeded` invalida;
  `failed`/`escalated` no; montaje con run ya `succeeded` no invalida; cambio de ticket sin desmontar
  resetea la detección; reintento tras fallo vuelve a disparar). Necesitó `wrapWithSession` nuevo en
  `render-with-session.tsx` (el `rerender` de Testing Library no re-envuelve providers).
- Green inicial: `useEffect` con `previousRef` comparando `status` anterior/actual por `ticketId`,
  más un ajuste de estado durante el render (no `useEffect`, por `react-hooks/set-state-in-effect`)
  para resetear `triggeredRunId` al cambiar de ticket — bug real encontrado en el propio Green (el
  panel seguía mostrando el run del ticket anterior tras navegar sin desmontar).
- Mutation testing (Stryker, scope `ai-draft-panel.tsx` completo): primera pasada 75.70% (bajo 80%)
  — 22 survivors, la mayoría en código PREEXISTENTE nunca cubierto por mutation (el `mutate` del
  `stryker.config.json` del repo excluye TODOS los `.tsx` con `"!src/**/*.tsx"`, así que esta era la
  primera vez que este fichero se mutaba de verdad, vía el `--mutate` acotado de la skill). Añadidos
  9 tests más para las ramas preexistentes sin cubrir (fuentes/confianza/traza ausentes, error sin
  mensaje del servidor, estado "comprobando", aria-label) y un test que precarga la caché de React
  Query para matar el mutante de `sameTicket` (sin precarga, el hueco async natural de una query
  nueva ya lo mataba por otra vía, enmascarando el mutante real). Segunda pasada: 85.05%.
- **Bug real reproducido y corregido durante la verificación manual contra el backend real** (no en
  tests): `POST /tickets/{id}/ai-draft` corre SÍNCRONO (`agent.py`, docstring: "la respuesta 202
  puede llegar con el run ya succeeded") — un run disparado por el botón "Generar borrador" puede
  llegar a `succeeded` en el PRIMER poll, sin pasar por `running`. La guarda original
  (`previous.status !== undefined`, para bloquear el falso positivo de 5c) también bloqueaba este
  caso real y mucho más común. Confirmado en vivo: creé un ticket, pulsé "Generar borrador", el panel
  llegó a "Borrador listo" pero el hilo no se actualizó sin recargar — 0 llamadas nuevas a
  `GET /tickets/{id}/messages` en la pestaña Network. Fix: distinguir un run disparado por ESTE
  cliente (`triggeredRunId === runId`, invalida en cuanto ve `succeeded`, sin exigir transición previa
  observada) de un run descubierto (`activeRun.data`, sigue exigiendo `previous.status` definido, para
  no invalidar en cada visita a un ticket con un run ya resuelto). Añadidos 2 tests más (succeeded sin
  "running" intermedio; descubierto en "running" y luego succeeded, para no perder el caso multi-
  usuario). Reverificado en el navegador: la respuesta de la IA apareció en el hilo sin recargar,
  confirmado también por red (`GET /agent-runs/{id}` → inmediatamente `GET /tickets/{id}` +
  `GET /tickets/{id}/messages`).
- Verificación manual: backend real (`uvicorn --reload` ya corriendo de esta sesión) + frontend en un
  puerto temporal (3011, arrancado desde el propio working dir de la tarea — el worktree dedicado a
  servir frontend, `syntax-frontend-dev`, no podía cambiar a esta rama porque ya estaba checked out
  en el working dir principal). `tenant.demo.auto_approve` activado temporalmente (estaba en `false`),
  3 tickets de prueba creados y borrados al terminar, flag revertido a `false`.
- Suite completa: 376 tests en verde (73 ficheros). `pnpm lint`/`pnpm typecheck` limpios.
- `sdd-lint`: mecánico limpio. CU-FE-06 ya traía los escenarios 5a-5e desde la planificación del plan.
- `fact-checker`: 10/10 VERIFICADO (efecto de invalidación, distinción disparado/descubierto, reset de
  `triggeredRunId` durante el render, `wrapWithSession`, 17+376 tests en verde, lint/typecheck limpios,
  test del caso "succeeded sin running intermedio", `TicketDetail` sin `key` en `AiDraftPanel`,
  docstring de `agent.py` sobre la respuesta síncrona).
- **Hallazgo fuera de alcance, no corregido**: keys duplicadas (`UC-API-022`, `UC-API-020`) en el
  `<li key={source.uc_id}>` de las fuentes del draft — warning de React observado en consola durante
  la verificación manual, preexistente, no introducido ni tocado por esta tarea.

## Cierre
- DoD completa. Tarea movida a `completed/`, `status: done`, `[x]` en el plan. Plan cerrado (única
  tarea) → `completed/`.
- Ficheros tocados: `frontend/src/features/ai-flow/ai-draft-panel.tsx`,
  `frontend/src/features/ai-flow/ai-draft-panel.test.tsx`, `frontend/src/test/render-with-session.tsx`.
- Follow-ups: ninguno nuevo abierto por esta tarea. Limitación preexistente confirmada en vivo (no
  introducida ni agravada): la visibilidad tardía de `agent_run` en el camino `ai_auto_draft`
  (transacción de fondo, `use-agent-draft.ts`) puede agotar los 30s de descubrimiento antes de que el
  run sea visible — ya documentada como follow-up explícito en ese fichero, fuera de esta tarea.
