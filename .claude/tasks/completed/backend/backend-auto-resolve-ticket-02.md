---
id: backend-auto-resolve-ticket-02
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

# Encadenar el camino auto a `resolved` en `respond.py`

## Description

El grafo ya publica la respuesta automáticamente cuando `decide.requires_approval=False`
(`app/agents/nodes/respond.py:26-28`), pero nunca toca `ticket.status` — el ticket se queda donde
estuviera (típicamente `new`). Esta tarea hace que el camino auto deje el ticket en `resolved`,
reutilizando `TicketService.advance_to()` (tarea `01`) y el patrón ya existente en
`approval_service.decide()`, con el orden transición-antes-de-publicar fijado en `grilling`
(`.claude/plans/pending/backend/auto-resolve-ticket.md`, Registro de cambios).

Requiere inyectar `TicketService` en `make_respond_node()` y threadearlo por
`build_graph()` → `LangGraphAgentRunner.__init__()` hasta `app/core/deps.py::_get_agent_runner()`
(que ya construye el runner con la misma `session` que usa `get_ticket_service(session)` en
`get_approval_service()` — mismo patrón, sin ambigüedad).

## Spec

- `make_respond_node(messages_repo, ticket_service)` — nueva firma; `graph.py::build_graph()` acepta
  y pasa `ticket_service`; `runner.py::LangGraphAgentRunner.__init__()` acepta `ticket_service` y lo
  pasa a `build_graph()`; `deps.py::_get_agent_runner()` pasa `ticket_service=get_ticket_service(session)`.
- En el nodo `respond`, camino auto (`not state["requires_approval"]`):
  1. Si `ticket.status` ya es `resolved` o `closed` → no transicionar, publicar directo (caso 4d del CU).
  2. Si no → `ticket_service.advance_to(state["ticket_id"], TicketStatus.resolved, actor_id=None)`
     **antes** de `_publish()` — `actor_id=None` explícito (parámetro añadido en la tarea `01`;
     documentado como "sistema", no un `Subject` humano). Si `advance_to()` lanza, no se publica el
     mensaje (propaga el error); por la semántica fijada en la tarea `01`, un fallo a mitad dejaría
     el ticket en el último estado alcanzado con éxito, no en un estado a medias arbitrario.
  3. `_publish()` sigue sin `actor_id` (el `Message` no tiene ese campo — es distinto del audit log
     de la transición) — ya es el comportamiento actual de `_publish()`, verificar que se mantiene.
- Actualizar el docstring de `app/agents/nodes/__init__.py`: documentar `respond` como la excepción a
  "los nodos solo reciben puertos" (recibe un servicio de dominio), con el porqué (orden
  transición-antes-de-publicar).
- Actualizar `test_runner.py` (único otro constructor de `LangGraphAgentRunner`) para pasar el nuevo
  parámetro.

## Fuera de alcance

- La nueva capacidad `ticket.reopen` (tarea `03`).
- Cambiar el camino HITL (`approval_service.py`) más allá del refactor ya hecho en la tarea `01`.
- Cualquier estado nuevo distinto de `resolved`.
- Resolver la asimetría auto-vs-HITL (`resolved` vs `pending`) — aceptada y documentada en el CU/ADR,
  no se toca aquí.
- **Riesgo aceptado, sin mitigar** (`scenario-coverage`, decisión del owner 2026-08-31): si el proceso
  crashea entre `advance_to()` y `_publish()` y LangGraph reintenta el nodo `respond` desde el
  checkpoint, `_publish()` no es idempotente (genera un `uuid4()` nuevo cada vez) — un reintento
  podría publicar un mensaje duplicado. Riesgo preexistente al plan (no introducido por esta tarea),
  ventana de fallo pequeña; no se mitiga en esta pasada.

## Scenarios (Gherkin)

Criterios de aceptación (Gherkin) en el caso de uso:
- [CU-BE-06 — Draft IA y aprobación HITL](../../../specs/backend/casos-de-uso/CU-BE-06-draft-ia-y-aprobacion-hitl.md)
  — extensiones 4c, 4d y los escenarios: "La auto-respuesta encadena hasta resolved desde cualquier
  estado de partida" (Scenario Outline, los 4 estados de partida), "La auto-respuesta no publica si
  un salto de la transición falla", "Auto-respuesta sobre un ticket ya resuelto no toca el estado".

## Provides

- El camino auto deja el ticket en `resolved` con el mensaje publicado — precondición real para que
  la tarea `03` (RBAC `ticket.reopen`) tenga sentido de negocio (hoy no hay nada que reabrir).
- `make_respond_node`/`build_graph`/`LangGraphAgentRunner` con la nueva firma — cualquier otro
  llamante futuro debe pasar `ticket_service`.

## Definition of Done

- [x] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [x] Cada escenario Gherkin tiene al menos un test (camino feliz + bordes/errores) — **integración
      real contra Postgres** para el camino auto completo (footgun RLS/`tenant_scope`, no solo fakes)
- [x] Todos los tests en verde (43 passed: `test_graph.py`+`test_runner.py`+`test_node_respond.py`)
- [x] Spec cumplida; lo declarado en `Provides` queda disponible para la tarea `03`
- [x] Lint / format / typecheck OK (`ruff check`, `ruff format --check`, `mypy app` strict)
- [x] Gate de mutation testing superado con `cosmic-ray` (93.33%, 42/45 killed, break: 80) — 3
      survivors documentados como mutantes equivalentes (`is`/`==` sobre singletons de `Enum`)
- [x] Gate `sdd-lint` superado — mecánico limpio (sin contenido SDD nuevo en esta tarea)
- [x] Gate de `fact-checker` superado — 10/10 afirmaciones VERIFICADO
- [x] Verificación manual contra el backend real (no solo tests): crear un ticket con
      `auto_approve=true` y confianza alta desde el tenant demo, confirmar que queda `resolved` con
      el mensaje publicado.
- [x] Documentación actualizada:
  - [x] TSDoc/docstrings en `respond.py`, `graph.py`, `runner.py`, `deps.py` donde cambie la firma
  - [x] `app/agents/nodes/__init__.py` documenta `respond` como excepción a la convención de nodos
  - [x] Histórico de la tarea — session log en `.claude/context/backend/backend-auto-resolve-ticket-02.md`
- [x] Docs de dev / usuario final + `pnpm changeset` donde aplique (N/A — backend no usa changesets)
