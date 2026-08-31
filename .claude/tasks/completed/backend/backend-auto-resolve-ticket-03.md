---
id: backend-auto-resolve-ticket-03
package: backend
plan: auto-resolve-ticket
status: done
priority: 2
depends_on: [backend-auto-resolve-ticket-01]
estimate: 3h
actual: 3h
issue:
created: 2026-08-31
updated: 2026-08-31
---

# RBAC: nueva capacidad `ticket.reopen` + endpoint dedicado

## Description

`client_agent` (rol que normalmente abre tickets) no puede reabrir un ticket `resolved`/`closed` —
`reopen()` ya existe en `TicketService`, pero solo `client_admin` tiene `ticket.transition` (que,
además, es más amplia de lo necesario: da acceso a cualquier destino válido, no solo reabrir).
`design-review` del plan (`.claude/plans/pending/backend/auto-resolve-ticket.md`, Registro de
cambios 2026-08-31) descartó ampliar `ticket.transition` a `client_agent` — es un rol de sistema
inmutable (`rbac.md §4`) y la capacidad completa habilitaría `pending→resolved`/`resolved→closed`,
no solo reabrir. En su lugar: una capacidad nueva y estrecha, `ticket.reopen`, con su propio
endpoint.

## Spec

- Nueva capacidad `ticket.reopen` en el catálogo (`app/infra/db/seed.py` `CAPABILITIES`, ámbito
  `tenant` — mismo ámbito que `ticket.transition`).
- Nuevo endpoint `POST /tickets/{id}/reopen` (`app/api/v1/routers/tickets.py`), gateado por
  `require_capability("ticket.reopen")`, que llama a `TicketService.reopen()` directo (ya existe,
  `resolved/closed→reopened` únicamente vía `_VALID_TRANSITIONS`) — mismo patrón que
  `POST /{id}/assign`. **No** reutiliza el genérico `POST /{id}/transition`.
- `client_agent` gana `ticket.reopen` en `seed.py:98` (además de sus capacidades actuales).
- Sincronizar `.claude/specs/backend/rbac.md`: añadir `ticket.reopen` al catálogo de capacidades
  (prosa + tabla), y `client_agent` a su lista de capacidades y a la matriz.
- `reopen()`/el nuevo endpoint pasan el `Subject` real que decide como `actor_id` en el audit log
  (a diferencia del camino auto de la tarea `02`, que usa `actor_id=None`) — aquí SÍ hay un humano
  detrás de la acción. Requiere la tarea `01` (`TicketService.reopen()` acepta `actor_id` desde ahí).
- El endpoint distingue explícitamente **403** (sin `ticket.reopen`) de **409** (con la capacidad,
  pero el ticket no está en `resolved`/`closed` — `InvalidTransition` de `reopen()`) — no colapsar
  ambos casos en el mismo código de estado.
- Aislamiento cross-tenant: mismo criterio que el resto de endpoints de ticket — un ticket de otro
  tenant, o un `id` inexistente, da **404** (nunca 403 ni 200).

## Fuera de alcance

- Cambiar el comportamiento de `POST /{id}/transition` o de `ticket.transition` para ningún rol.
- Dar `ticket.reopen` a ningún rol además de `client_agent` (los que ya tienen `ticket.transition`
  ya pueden reabrir por esa vía; no se duplica).
- FR-030 (lanzar un `agent_run` nuevo al reabrir) — hueco nombrado y ya documentado como fuera de
  esta capa (`ticket_service.py`), no se resuelve en esta tarea.
- El camino auto de `respond.py` (tarea `02`).
- **Riesgos aceptados, sin mitigar** (`scenario-coverage`, decisión del owner 2026-08-31): (1) no se
  notifica a soporte cuando un cliente reabre un ticket auto-resuelto (a diferencia de
  `assign_ticket`, que sí notifica) — el ticket queda `reopened` visible en la bandeja, sin alerta
  activa; (2) sin locking optimista entre el camino auto (tarea `02`) y un `reopen()` simultáneo, el
  orden final de escritura ante una carrera real es indeterminado — ventana muy corta, mismo
  criterio de riesgo ya aceptado en `approval_service.py`. Ninguno se mitiga en esta pasada.

## Scenarios (Gherkin)

Criterios de aceptación (Gherkin) en el caso de uso:
- [CU-BE-06 — Draft IA y aprobación HITL](../../../specs/backend/casos-de-uso/CU-BE-06-draft-ia-y-aprobacion-hitl.md)
  — extensiones 4e, 4f, 4g y los escenarios: "El cliente reabre un ticket auto-resuelto que no le
  vale" (Scenario Outline, `resolved` y `closed`), "Reabrir sin la capacidad adecuada se rechaza",
  "ticket.reopen no habilita ninguna otra transición", "Reabrir un ticket que no está en un estado
  válido para ello es un conflicto" (409), "Reabrir un ticket de otro tenant no revela que existe"
  (404), "Reabrir un ticket inexistente da 404".

## Provides

- `POST /tickets/{id}/reopen` — endpoint real, capacidad `ticket.reopen` en el catálogo RBAC,
  concedida a `client_agent`. Cierra el objetivo 2 del plan (el cliente puede objetar una
  auto-respuesta sin pasar por un admin).

## Definition of Done

- [x] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [x] Cada escenario Gherkin tiene al menos un test (camino feliz + bordes/errores) — incl. los 3
      casos negativos distintos: 403 (sin `ticket.reopen`), 409 (con la capacidad, estado inválido),
      404 (cross-tenant / inexistente) — no colapsados en uno solo
- [x] Todos los tests en verde (89: 40 `test_router_tickets.py` + 49 `test_ticket_service.py`)
- [x] Spec cumplida; `rbac.md` y `seed.py` sincronizados (prosa + tabla + código, sin divergencia)
- [x] Lint / format / typecheck OK (`ruff check`, `ruff format --check`, `mypy app` strict)
- [x] Gate de mutation testing superado con `cosmic-ray` (91.94%, 114/124 killed, break: 80) — 10
      survivors, todos en código PREEXISTENTE sin tocar por esta tarea (`list_tickets`,
      `update_ticket`, `assign_ticket`, `_parse_status`, `_trigger_ai_draft_in_background`); 0
      survivors en `reopen_ticket` (código nuevo de esta tarea)
- [x] Gate `sdd-lint` superado — mecánico limpio (sin contenido SDD nuevo en esta tarea)
- [x] Gate de `fact-checker` superado — 9/9 afirmaciones VERIFICADO (incluye su propia verificación
      manual independiente contra el backend real)
- [x] Verificación manual contra el backend real: login como `client_agent` (tenant demo), reabrir un
      ticket `resolved` propio, confirmar 200 y `status=reopened`; confirmar 403 contra cualquier
      otro destino.
- [x] Documentación actualizada:
  - [x] TSDoc/docstrings en el nuevo endpoint y en el catálogo de `seed.py`
  - [x] `.claude/specs/backend/rbac.md` actualizado (prosa + matriz)
  - [x] Histórico de la tarea — session log en `.claude/context/backend/backend-auto-resolve-ticket-03.md`
- [x] Docs de dev / usuario final + `pnpm changeset` donde aplique (N/A — backend no usa changesets)
