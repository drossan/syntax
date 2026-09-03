---
id: frontend-ticket-thread-live-refresh
package: frontend
status: completed
branch: plan/frontend/ticket-thread-live-refresh
issue:
created: 2026-08-31
updated: 2026-08-31
---

# El hilo del ticket no se refresca cuando la IA auto-responde

## Contexto y problema

Cuando el grafo del agente auto-responde (confianza alta, `tenant.auto_approve=true`), el mensaje
ya se publica en el backend de inmediato. Pero el tenant que abrió el ticket no lo ve "al momento":

- `frontend/src/features/tickets/use-ticket.ts` (`useTicketMessages`, líneas 47-61) no hace polling
  ni se invalida por ningún evento — solo se refetchea si algo más llama a
  `queryClient.invalidateQueries({ queryKey: ticketMessagesKey(...) })`.
- `frontend/src/features/ai-flow/use-agent-draft.ts` (`useAgentRun`, líneas 108-124) ya sondea el
  `AgentRun` hasta que es terminal (incluye `succeeded`), pero nada conecta esa transición con el
  hilo de mensajes.

Resultado: el usuario tiene que recargar la página a mano para ver una respuesta que el sistema ya
publicó — la "auto-respuesta al momento" que pide el negocio no se percibe como tal.

Este plan es independiente del plan `backend/auto-resolve-ticket` (mismo feature, sin dependencia
dura entre ambos: esta pieza vale igual aunque el ticket no cambie de estado).

## Objetivos

1. **El hilo de mensajes se refresca solo cuando el `AgentRun` de ese ticket llega a `succeeded`**,
   sin que el usuario recargue ni interactúe.
   - *Criterio de éxito*: test que simula la transición de `useAgentRun` a `succeeded` y comprueba
     que `useTicketMessages` se re-consulta; verificación manual contra el backend real (crear
     ticket con auto-respuesta, ver el mensaje aparecer sin recargar).
2. **No se añade polling permanente del hilo** cuando no hay ningún run en curso (coste de red
   innecesario).
   - *Criterio de éxito*: sin un `AgentRun` activo, `useTicketMessages` no gana ningún
     `refetchInterval`.

## Alcance y fuera de alcance

### Dentro del alcance
- **Mecanismo simplificado en `design-review` (2026-08-31, revierte 2 decisiones de `grilling` —
  ver Registro de cambios)**: invalidar, no polling nuevo — eso se mantiene. Pero la lógica vive en
  **`AiDraftPanel`** (ya tiene `ticketId` como prop, sin cambiar la firma de `useAgentRun`), y la
  invalidación usa el **prefijo** `queryClient.invalidateQueries({ queryKey: ["ticket"] })` — mismo
  patrón ya probado en `use-approval-decision.ts:25` para el mismo tipo de evento (mensaje
  publicado → refrescar cabecera+hilo), sin necesitar `ticketId` ni `activeTenantId` (que
  `ticketKey`/`ticketMessagesKey` sí exigen, y que ni `useAgentRun` ni `AiDraftPanel` tienen hoy —
  gap de corrección real que este cambio evita en vez de arreglar).
- Implementación: un `useEffect` en `AiDraftPanel` que compara el `status` anterior/actual del run
  (vía `ref`) y, en la transición a `succeeded`, llama a `invalidateQueries`. **No** es el patrón
  "compara y ajusta sin efecto" de `useActiveAgentRun` (`use-agent-draft.ts:84-94`) — ese evita
  cascadas de `setState` local; aquí el efecto colateral es una llamada de red externa
  (`invalidateQueries`), que si corriera en el cuerpo del render violaría la pureza de render y se
  duplicaría en StrictMode. Un `useEffect` normal es lo correcto, no una excepción a evitar.
- Un run que llega a `escalated`/HITL (`requires_approval=true`) **no** dispara esta invalidación —
  verificado que no hace falta: ese camino no publica mensaje hasta que un humano decide, y
  `use-approval-decision.ts` ya invalida `["ticket"]` al aprobar/editar/rechazar.
- Tests unitarios (MSW) cubriendo: invalidación tras `succeeded`, ausencia de invalidación en
  `failed`/`escalated`, y que sin ningún run activo `useTicketMessages` no gana ningún
  `refetchInterval` nuevo (objetivo 2, sigue sin tocarse ese hook).

### Fuera de alcance
- Cambiar la firma de `useAgentRun` (descartado en `design-review` — la lógica vive en `AiDraftPanel`).
- Invalidación "precisa" por tenant+ticket (descartada — se usa el prefijo `["ticket"]`, ya probado).
- Rediseñar `AiDraftPanel` más allá del `useEffect` necesario para disparar la invalidación.
- Polling del hilo cuando NO hay ningún run activo.
- Cualquier cambio de backend (RBAC, estado del ticket) — va en `plans/*/backend/auto-resolve-ticket.md`.

## Recursos externos

- `frontend/src/features/tickets/use-ticket.ts` — `ticketKey`/`ticketMessagesKey`/`useTicketMessages`.
- `frontend/src/features/approvals/use-approval-decision.ts:25` — patrón ya probado de
  `invalidateQueries({ queryKey: ["ticket"] })` a reutilizar.
- `frontend/src/features/ai-flow/use-agent-draft.ts` — `useAgentRun`, sin tocar su firma.
- `frontend/src/features/ai-flow/ai-draft-panel.tsx` — donde vive el nuevo `useEffect`.

## Estimación global

- **Tareas totales**: 1 (ver lista al final).
- **Esfuerzo estimado**: 0.5-1 sesión.
- **Recursos**: ninguno nuevo; MSW/Vitest ya configurados.

## Criterios de calidad y verificación

- TDD en todas las capas; tests antes de la implementación.
- `pnpm lint` y `pnpm test` en verde tras la tarea.
- Gate de mutation testing (Stryker, `break: 80`).
- Verificación manual contra el backend real (no solo MSW): crear un ticket con `auto_approve=true`
  desde un tenant demo, confirmar que el mensaje aparece en el hilo sin recargar.

## Tasks

- [x] `frontend-ticket-thread-live-refresh-01` (P1) — Invalidar el hilo cuando el AgentRun llega a `succeeded`  · depends_on: —

## Registro de cambios del plan

- 2026-08-31: creado, a partir de un plan combinado (harness plan mode) aprobado por el owner. Pieza
  3 del feature de auto-respuesta IA (las otras dos, backend, viven en
  `plans/*/backend/auto-resolve-ticket.md`).
- 2026-08-31: refinado con `grilling` (3 preguntas, 3 decisiones): (1) invalidar en vez de polling
  nuevo; (2) invalidar mensajes+cabecera juntos, no solo mensajes; (3) la lógica vive dentro de
  `useAgentRun`, no en `AiDraftPanel` — cambia su firma para aceptar `ticketId`.
- 2026-08-31: revisado con `design-review` (subagente adversario, 4 hallazgos, model routing caído a
  inherit por el mismo motivo que el plan backend). Cambios aplicados, decididos con el owner —
  **revierten las decisiones (2) y (3) de `grilling`**:
  1. **Bug real detectado**: `ticketKey`/`ticketMessagesKey` exigen `activeTenantId`, que ni
     `useAgentRun` ni `AiDraftPanel` tienen hoy — el mecanismo tal como se había fijado en `grilling`
     no era implementable sin un cambio no planeado (añadir `useTenant()` en un sitio nuevo).
  2. En vez de arreglar ese gap, se simplifica: se reutiliza el patrón ya probado de
     `use-approval-decision.ts:25` (`invalidateQueries({ queryKey: ["ticket"] })`, prefijo, sin
     tenant/id) — mismo resultado (mensajes+cabecera), menos código, sin el bug.
  3. La lógica vuelve a `AiDraftPanel` (ya tenía `ticketId`), no a `useAgentRun` — evita acoplar un
     hook genérico de `ai-flow` a lógica de negocio de `tickets`, y evita el cambio de firma.
  4. Se aclara que el mecanismo es un `useEffect` normal (compara status vía `ref`), no el patrón
     "compara y ajusta sin efecto" de `useActiveAgentRun` — ese resuelve otro problema (cascadas de
     `setState`), no aplica a un efecto colateral externo como `invalidateQueries`.
- 2026-08-31: revisado con `scenario-coverage` (subagente QA, 7 hallazgos en alcance + 3 fuera de
  alcance contrastados). Decisiones aplicadas, con el owner:
  1. 4 escenarios nuevos: el `ref` no dispara invalidación en su primera lectura si el run ya está
     `succeeded` al montar (evita falsos positivos en cada visita/remontaje); el `ref` se resetea al
     cambiar `ticketId` sin desmontar; un segundo run tras reintento vuelve a disparar la
     invalidación igual que el primero; el mecanismo es explícitamente un `useEffect` (no el cuerpo
     del render), para no duplicarse bajo StrictMode.
  2. Confirmado sin hallazgo nuevo: la invalidación por prefijo `["ticket"]` (imprecisa por
     tenant/ticket) es la decisión ya aceptada en la pasada anterior de `design-review`; ninguna
     otra tarea de backend queda afectada.
  3. Nombrado, no incorporado: falta de señal a11y/visual (toast, `aria-live`) cuando el mensaje
     llega en silencio — cae contra "no rediseñar `AiDraftPanel` más allá del `useEffect`
     necesario"; el owner no lo pidió, queda fuera de esta tarea.
- 2026-08-31: tarea `01` cerrada. TDD + mutation (Stryker 84.48%) + `sdd-lint` + `fact-checker` (10/10)
  + verificación manual contra el backend real. Plan movido a `completed/` (única tarea).

## Nota retro

- **Estimación vs. real**: 3h estimadas, ~4h reales. El exceso no vino del mecanismo en sí (la
  implementación inicial del `useEffect` fue rápida) sino de dos rondas de endurecimiento que NINGUNA
  fase de planificación (`grilling`/`design-review`/`scenario-coverage`) podía haber anticipado sin
  ejecutar código: (1) el mutation testing reveló que `stryker.config.json` excluye TODOS los `.tsx`
  del repo (`"!src/**/*.tsx"` en `mutate`) — este componente nunca había sido mutado de verdad hasta
  esta tarea, así que además de las mutaciones de mi código nuevo, aparecieron ~15 survivors en
  código YA EXISTENTE sin cubrir; (2) la verificación manual contra el backend real reprodujo un bug
  genuino (`POST /ai-draft` corre síncrono, un run puede llegar `succeeded` en el primer poll) que el
  diseño original no contemplaba — ninguna de las 3 pasadas de revisión lo vio porque ninguna ejecuta
  código contra un backend real.
- **Hallazgo de proceso, no solo de código**: la pasada de `scenario-coverage` fijó explícitamente el
  Gherkin 5c ("montar con un run ya succeeded no invalida por sí solo") sin que nadie notara que la
  implementación más simple para cumplirlo (exigir un `status` previo definido) rompía el escenario
  MÁS común del feature (el botón "Generar borrador", camino 5a) — los dos escenarios son
  indistinguibles a nivel de transición de `status` observada, y solo la verificación manual contra
  el backend REAL (no MSW) lo sacó a la luz. Refuerza el valor de la verificación manual como gate
  no-opcional, no solo ritual: aquí encontró un bug que 15 tests con mocks no habían detectado porque
  el mock, sin querer, siempre modelaba una transición `running→succeeded` en vez del `succeeded`
  directo que el backend real produce.
- **Config del repo, no de esta tarea (señalado, no corregido)**: `frontend/stryker.config.json`
  excluye todos los `.tsx` de mutation — probablemente un descuido de bootstrap del repo (el patrón
  `"!src/**/*.tsx"` anula la inclusión de `.tsx` de la línea anterior). Corregirlo activaría mutation
  real en TODOS los componentes React del repo de golpe, con un volumen de survivors pendientes fuera
  del alcance de esta tarea — decisión del owner, no tomada aquí.
- **Dependencias no vistas**: ninguna con el plan backend paralelo (`auto-resolve-ticket`) — se
  verificó en vivo que ambos funcionan juntos (ticket auto-resuelto + hilo refrescado sin recargar)
  sin fricción.
