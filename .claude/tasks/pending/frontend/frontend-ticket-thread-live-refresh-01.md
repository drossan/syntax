---
id: frontend-ticket-thread-live-refresh-01
package: frontend
plan: ticket-thread-live-refresh
status: pending
priority: 1
depends_on: []
estimate: 3h
actual:
issue:
created: 2026-08-31
updated: 2026-08-31
---

# Invalidar el hilo del ticket cuando el AgentRun llega a `succeeded`

## Description

Cuando el grafo del agente auto-responde, el mensaje ya se publica en el backend de inmediato, pero
el tenant que abrió el ticket no lo ve hasta recargar: `useTicketMessages`
(`frontend/src/features/tickets/use-ticket.ts`) no se invalida por ningún evento, y `useAgentRun`
(`frontend/src/features/ai-flow/use-agent-draft.ts`) sondea el run sin conectar su transición a
`succeeded` con el hilo de mensajes.

`design-review` simplificó el mecanismo fijado en `grilling`
(`.claude/plans/pending/frontend/ticket-thread-live-refresh.md`, Registro de cambios 2026-08-31): en
vez de precisar la key por tenant+ticket dentro de `useAgentRun` (que tenía un gap real —
`ticketKey`/`ticketMessagesKey` exigen `activeTenantId`, que ni el hook ni su consumidor tienen
hoy), se reutiliza el patrón ya probado de `use-approval-decision.ts:25`
(`invalidateQueries({ queryKey: ["ticket"] })`, prefijo) desde `AiDraftPanel`, que ya tiene
`ticketId` como prop.

## Spec

- `AiDraftPanel` (`frontend/src/features/ai-flow/ai-draft-panel.tsx`) añade un `useEffect` que
  compara el `status` del run anterior/actual (vía `ref`, no el patrón de
  "comparar-sin-efecto" de `useActiveAgentRun` — ese resuelve cascadas de `setState` local; aquí el
  efecto colateral es una llamada de red externa, `invalidateQueries`, que si corriera en el cuerpo
  del render violaría la pureza de render y se duplicaría en StrictMode).
- En la transición a `status === "succeeded"`: `queryClient.invalidateQueries({ queryKey: ["ticket"] })`.
- `escalated`/`failed`/cualquier otra transición: no dispara la invalidación.
- **Semánticas fijadas en `scenario-coverage` (2026-08-31, decisión del owner)**:
  - El `ref` de "status anterior" **no** dispara invalidación en su primera lectura (montaje) — solo
    una transición observada DESDE otro estado HACIA `succeeded` cuenta. Si el run ya está
    `succeeded` cuando el panel se monta, no se invalida nada por el simple montaje (5c).
  - El `ref` se resetea cuando cambia `ticketId` (el efecto depende de `[ticketId, runId, status]` o
    equivalente) — evita que una transición real en un ticket nuevo quede enmascarada por el
    `status` recordado de un ticket anterior si el panel no se desmonta entre uno y otro (5d).
  - Un segundo run (tras reintento) que llega a `succeeded` dispara la invalidación igual que el
    primero — no debe depender de un flag "ya invalidé una vez" que sobreviva al reintento (5e).
- **No** se cambia la firma de `useAgentRun` ni de `useTicketMessages`.
- **No** se añade polling nuevo — `useTicketMessages` sigue sin `refetchInterval` propio.

## Fuera de alcance

- Cambiar la firma de `useAgentRun` (descartado en `design-review`).
- Invalidación "precisa" por tenant+ticket (descartada — se usa el prefijo `["ticket"]`).
- Rediseñar `AiDraftPanel` más allá del `useEffect` necesario.
- Polling del hilo cuando no hay ningún run activo.
- Cualquier cambio de backend (RBAC, estado del ticket) — va en el plan `backend/auto-resolve-ticket`
  (independiente, sin dependencia dura con esta tarea).

## Scenarios (Gherkin)

Criterios de aceptación (Gherkin) en el caso de uso:
- [CU-FE-06 — Flujo IA: cola, ciclo de draft y decisiones](../../../specs/frontend/casos-de-uso/CU-FE-06-flujo-ia-cola-draft-decisiones.md)
  — extensiones 5a-5e y los escenarios: "El cliente ve la auto-respuesta sin recargar", "Un run
  escalado a HITL no refresca el hilo todavía", "Un run fallido no refresca el hilo", "Montar el
  panel con el run ya succeeded no invalida por sí solo", "Cambiar de ticket sin desmontar resetea
  la detección de transición", "Reintento tras fallo vuelve a disparar la invalidación".

## Provides

- `AiDraftPanel` invalida la caché del ticket al detectar `succeeded` — cierra el objetivo 1 del
  plan (auto-respuesta visible sin recargar). Nada aguas abajo depende de esta tarea dentro de este
  plan (única tarea).

## Definition of Done

- [ ] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [ ] Cada escenario Gherkin tiene al menos un test (camino feliz + bordes/errores)
- [ ] Todos los tests en verde
- [ ] Spec cumplida; comportamiento verificado con MSW (transición a `succeeded` invalida
      `["ticket"]`; `failed`/`escalated` no lo hacen; sin run activo, sin `refetchInterval` nuevo)
- [ ] Lint / format / typecheck OK (`pnpm lint`, `pnpm typecheck`)
- [ ] Gate de mutation testing superado (Stryker, `break: 80`)
- [ ] Gate `sdd-lint` superado — artefactos SDD sin ERROR de formato/completitud (AVISO se reconoce)
- [ ] Gate de `fact-checker` superado — afirmaciones de la sesión verificadas
- [ ] Verificación manual contra el backend real (no solo MSW): crear un ticket con
      `auto_approve=true` desde el tenant demo, confirmar que el mensaje aparece en el hilo sin
      recargar la página.
- [ ] Documentación actualizada:
  - [ ] TSDoc en el `useEffect`/función nueva de `AiDraftPanel`
  - [ ] Histórico de la tarea — session log en
        `.claude/context/frontend/frontend-ticket-thread-live-refresh-01.md`
- [ ] Docs de dev / usuario final + `pnpm changeset` donde aplique
