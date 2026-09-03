# 0019. Auto-respuesta IA transiciona el ticket a `resolved`; nueva capacidad `ticket.reopen` (refina 0009)

- **Estado**: accepted
- **Fecha**: 2026-08-31
- **Decisores**: Owner; `grilling` + `design-review` backend (plan `auto-resolve-ticket`).

## Contexto y planteamiento del problema

0009 fija que, con confianza suficiente y `tenant.auto_approve=true`, el sistema **auto-responde**
sin HITL. Pero no fija qué le pasa al `ticket.status` cuando eso ocurre: `respond.py` publica el
`message` y nunca toca el estado — un ticket auto-respondido queda indistinguible de uno recién
creado sin tocar. Falta, además, un mecanismo para que el cliente diga "esta respuesta no vale".

## Decision drivers

- El cliente necesita una señal de "esto ya se respondió" y una vía para objetar sin pasar por un
  admin de tenant.
- `_VALID_TRANSITIONS` (CU-BE-04) no tiene aristas directas hacia `resolved` desde `new`/`open` —
  cualquier solución debe respetar la máquina de estados existente, no añadirle aristas nuevas.
- `client_agent` es un **rol de sistema inmutable** (rbac.md §4): una capacidad que se le concede no
  es revocable puntualmente sin clonar el rol — el coste de conceder de más es alto y permanente.

## Opciones consideradas

- **Opción 1** — Encadenar `→open→pending→resolved` (reutilizando el patrón ya usado por
  `approval_service.decide()` para `→pending`) + nueva capacidad estrecha `ticket.reopen`
  (`{resolved,closed}→reopened` únicamente) para `client_agent`, vía endpoint dedicado.
- **Opción 2** — Introducir un estado nuevo (p.ej. `awaiting_confirmation`) distinto de `resolved`,
  con sus propias aristas y semántica.
- **Opción 3** — Dar a `client_agent` la capacidad `ticket.transition` completa (genérica, cualquier
  destino válido desde el estado actual), reutilizando el endpoint `POST /{id}/transition` existente.

## Resultado de la decisión

Elegida: **Opción 1**, porque reutiliza la máquina de estados y el precedente de encadenado ya
existentes (sin tocar `_VALID_TRANSITIONS`) y acota el RBAC a lo mínimo necesario (objetar una
auto-respuesta), evitando la superficie amplia e irrevocable de la Opción 3 (que habría permitido a
`client_agent` auto-resolver o cerrar unilateralmente sus propios tickets, sin relación con el
problema real) y el coste de diseño/migración de la Opción 2 (estado nuevo, sin necesidad
demostrada frente a reutilizar `resolved`+`reopened`).

### Confirmación

`CU-BE-06` (escenarios de auto-respuesta → `resolved`, ticket ya terminal, reapertura por
`client_agent`); tests de integración del plan `backend/auto-resolve-ticket` (Postgres real, RLS);
gate de mutation testing por tarea.

## Consecuencias

- **Buenas**: la máquina de estados no cambia de forma; el cliente puede objetar sin admin; la
  capacidad nueva es estrecha y auditable por separado de `ticket.transition`.
- **Malas / coste**: **asimetría** entre caminos — el camino auto (sin revisión humana) llega a
  `resolved`, un salto más allá que el camino HITL aprobado (que se detiene en `pending`); la
  respuesta menos escrutada queda más "cerrada" que la más escrutada. Aceptada explícitamente, no
  resuelta en este ADR (ver plan). Requiere un endpoint nuevo (`POST /{id}/reopen`) en vez de
  reutilizar el genérico `/transition`, y extraer el encadenado a un método compartido
  (`TicketService.advance_to()`) para no duplicar la lógica de recorrido en `approval_service.py`
  y en `respond.py`.

## Pros y contras de las opciones

- **Opción 1**: 👍 sin tocar la FSM, RBAC mínimo y auditable · 👎 asimetría auto-vs-HITL sin resolver; endpoint nuevo.
- **Opción 2**: 👍 semántica más precisa ("aún no confirmado" ≠ "resuelto") · 👎 estado nuevo = migración + UI + RBAC nuevos, sin pedido explícito de esa precisión.
- **Opción 3**: 👍 cero endpoints nuevos, reutiliza `/transition` · 👎 RBAC irrevocable y desproporcionado (auto-resolver/cerrar unilateral), descartada en `design-review`.
