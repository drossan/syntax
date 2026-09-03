# Session log — backend-auto-resolve-ticket-03

## 2026-08-31
- Verificado antes de implementar: `TicketService.reopen()` ya aceptaba `actor_id` (tarea `01`);
  `POST /{id}/assign` era el patrón de endpoint dedicado a replicar; `client_agent` no tenía
  `ticket.reopen` ni `ticket.transition` en `seed.py`.
- Red: 10 tests nuevos en `tests/test_router_tickets.py` — éxito `resolved`/`closed` (Scenario
  Outline), 403 sin capacidad, 403 en `/transition` con solo `ticket.reopen` (no habilita otra
  transición), 409 parametrizado sobre `new`/`open`/`pending`/`reopened`, 404 cross-tenant, 404
  inexistente. `404 Not Found` confirmado (el endpoint no existía).
- Green: capacidad `ticket.reopen` (`CapabilityScope.tenant`) en `CAPABILITIES`, añadida a
  `client_agent` en `SYSTEM_ROLES` (`seed.py`); endpoint `POST /{id}/reopen` (`reopen_ticket`) en
  `tickets.py`, gateado por `require_capability("ticket.reopen")`, llama directo a
  `ticket_service.reopen(id, actor_id=subject.id)` — no reutiliza `/transition`.
- 89 tests en verde (`test_router_tickets.py`+`test_ticket_service.py`). `ruff check`/`ruff format
  --check`/`mypy app` (strict) limpios en `tickets.py`/`seed.py`.
- `rbac.md` sincronizado: capacidad en el catálogo (§2), `client_agent` en §3, fila en la matriz —
  con nota explícita de que `support_agent`/`client_admin` NO tienen `ticket.reopen` en sí (ya
  reabren vía `ticket.transition`, capacidad más amplia que ya poseen).
- Verificación manual contra el backend real (uvicorn --reload ya corriendo en :8000 de esta
  sesión, seed re-ejecutado para propagar la capacidad nueva): ticket creado por `client_agent`,
  avanzado a `resolved` por `client_admin` (`new→open→pending→resolved`), reabierto por
  `client_agent` vía `/reopen` → 200 `status=reopened`; el mismo token contra `/transition` →
  403. Ticket de prueba borrado de la BD demo al terminar.
- Gate mutation (`cosmic-ray`, scope `app/api/v1/routers/tickets.py` completo — el fichero
  preexistente es grande, no solo lo tocado por esta tarea; ⚠️ invocación de referencia no
  verificada en este repo): 91.94% kill rate (114/124). 10 survivors, TODOS en código preexistente
  sin tocar por esta tarea (`list_tickets`, `update_ticket`, `assign_ticket`, `_parse_status`,
  `_trigger_ai_draft_in_background`) — huecos de test reales pero fuera de esta tarea, no se
  corrigen aquí (scope discipline). `reopen_ticket` (código nuevo, líneas 292-305): 0 survivors,
  sus 2 mutaciones (`RemoveDecorator`) fueron KILLED.
- `sdd-lint`: mecánico limpio (0 ERROR). Sin contenido SDD nuevo — CU-BE-06 ya tenía los escenarios
  4e-4g desde la planificación del plan.
- `fact-checker`: 9/9 VERIFICADO (capacidad+rol en `seed.py`, endpoint separado con `actor_id` real,
  10 tests del endpoint, 89 tests en verde, lint/format/mypy limpios, `cosmic-ray.toml`/
  `session.sqlite` sin residuo, `rbac.md` sincronizado, y una verificación manual PROPIA e
  independiente del subagente contra el backend real, con el mismo resultado 200/403).
- **Nota de alcance, no actuada**: `api-contract.yaml` no documenta `POST /tickets/{id}/reopen`
  (solo `/transition` y `/assign`) — fuera del `## Spec`/DoD de esta tarea, señalado al owner, no
  se actúa por cuenta propia.

## Cierre
- DoD completa. Tarea movida a `completed/`, `status: done`, `[x]` en el plan.
- Ficheros tocados: `backend/app/api/v1/routers/tickets.py`, `backend/app/infra/db/seed.py`,
  `backend/tests/test_router_tickets.py`, `.claude/specs/backend/rbac.md`.
- Follow-ups: ninguno nuevo. Cierra el plan `auto-resolve-ticket` en su parte backend (tareas
  01/02/03 completas). Pendiente: `api-contract.yaml` sin sincronizar con `/reopen` (decisión del
  owner); plan `frontend/ticket-thread-live-refresh` (paralelo, sin dependencia dura).
