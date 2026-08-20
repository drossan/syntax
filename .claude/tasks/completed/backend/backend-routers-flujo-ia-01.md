---
id: backend-routers-flujo-ia-01
package: backend
plan: routers-flujo-ia
status: done
priority: 1
depends_on: []
estimate: 6h
actual: 6h
issue:
created: 2026-08-20
updated: 2026-08-20
---

# AgentRunner.trigger() + CAS + rate-limit in-memory + agent_service + router agent

## Description

Primer punto de contacto HTTP con el flujo-IA, con el grafo real (15/16) aún sin existir. Amplía el
puerto `AgentRunner` (plan `domain-services`, solo tenía `resume()`) con `trigger()`, añade el adaptador
`StubAgentRunner` (no ejecuta ningún grafo — mismo criterio que `StubVectorStore`/`StubSlaPolicy` de
`routers-core`) y el `agent_service` nuevo que compone: rate-limit → comprobación de run activo (CAS real,
no solo check-then-act) → creación del `AgentRun`. Spec: `agent-graph.md` §6.1 (`thread_id`), FR-022
(disparo, sin ejecutar el grafo — eso es 15/16), CU-BE-06 (ampliado por esta tarea con los escenarios de
disparo, que hoy no cubre).

## Spec

- **Migración Alembic nueva**: índice único parcial `ix_agent_run_active_per_ticket` en
  `agent_run(ticket_id)` `WHERE status IN ('queued','running')` — CAS real contra dos runs concurrentes
  para el mismo ticket (mismo nivel de garantía que `decide_if_pending`/`rotate_if_active`).
- **`app/domain/ports/agent_runner.py`**: `AgentRunner` gana `trigger(tenant_id, ticket_id, run_seq,
  thread_id) -> AgentRun` (junto al `resume()` ya existente).
- **`app/infra/agent_runner/stub.py`** (nuevo): `StubAgentRunner.trigger()` construye y devuelve el
  `AgentRun` (`status=queued`, `confidence=None`, `sources=None`) sin ejecutar ningún nodo del grafo — sin
  ninguna rama condicional (mutation N/A documentado, mismo criterio M4 de planes anteriores).
- **`app/domain/ports/repositories.py`**: `AgentRunRepository` gana `get_active_for_ticket(ticket_id) ->
  AgentRun | None` (lee el último run no terminal, si existe).
- **`app/infra/db/repositories/agent_run.py`** (nuevo): `SqlAlchemyAgentRunRepository` — adaptador de
  `AgentRunRepository` completo (`get`/`add`/`update_status`/`next_run_seq`/`get_active_for_ticket`).
  `add()` captura la violación del índice único parcial (`IntegrityError`, vía asyncpg) y la traduce a
  `app.domain.errors.Conflict` — el CAS real vive en la constraint, no en un check previo del servicio.
- **`app/domain/ports/rate_limiter.py`** (nuevo): `RateLimiter.check_and_increment(key: str) -> bool` —
  `True` si la petición cabe en la ventana, `False` si excede.
- **`app/infra/rate_limit/in_memory.py`** (nuevo): `InMemoryRateLimiter` — ventana fija de 1 minuto,
  contador `dict[str, tuple[int, float]]` en memoria del proceso (no compartido entre workers/instancias
  — limitación documentada, no resuelta en esta tarea).
- **`app/domain/errors.py`**: nuevo `RateLimited(DomainError)` (`code="rate_limited"`). **`app/api/
  errors.py`**: mapeo `RateLimited`→429 (mensaje localizado es/en, mismo patrón que el resto de la tabla).
- **`app/core/config.py`**: nuevo `ai_draft_rate_limit_per_minute: int = 10`. **Se elimina**
  `ai_draft_max_per_ticket` (B.1, nunca implementado, redundante con el CAS de arriba) y su test en
  `tests/test_config.py`.
- **`app/domain/services/agent_service.py`** (nuevo). `trigger()` ordena los chequeos de **más barato a
  más caro** — nada que vaya a fallar gratis consume cuota de rate-limit ni toca la constraint de BD
  (`scenario-coverage` #1, #3, orden de comprobaciones):
  - `trigger(tenant_id, ticket_id) -> AgentRun`: 1) `tickets.get(ticket_id)` (puerto `TicketRepository`,
    ya inyectado) — `NotFound` (404) si no existe o pertenece a otro tenant (scope ya resuelto por el
    router, mismo patrón que `ticket_service.get`); 2) `agent_runs.get_active_for_ticket(ticket_id)` — si
    devuelve un run, `Conflict` (409); **pre-check best-effort, no atómico** — le da un uso real al
    método del puerto (antes huérfano) y evita gastar cuota de rate-limit en un disparo que iba a
    fallar, pero **no sustituye** la garantía real; 3) `rate_limiter.check_and_increment(str(tenant_id))`
    — si `False`, `RateLimited` (429); 4) `agent_runs.next_run_seq(ticket_id)` → `run_seq`; 5)
    `thread_id = f"ticket_{ticket_id}_run_{run_seq}"`; 6) `agent_runner.trigger(tenant_id, ticket_id,
    run_seq, thread_id)` — si el adaptador lanza `Conflict` (índice único parcial), se propaga tal cual:
    esta es la garantía **atómica** real bajo concurrencia, el pre-check del paso 2 es solo optimización.
  - `get(agent_run_id) -> AgentRun`: `agent_runs.get(agent_run_id)`, `NotFound` si `None`.
- **`app/core/deps.py`**: `get_agent_service` (ensambla con `SqlAlchemyAgentRunRepository` +
  `StubAgentRunner` + `InMemoryRateLimiter` + `SqlAlchemyTicketRepository`, singleton de proceso para el
  rate-limiter — no una instancia nueva por request, o el contador nunca acumula). Helper de capacidad
  **compuesta** `require_any_capability("agent.trigger", "ticket.read")` (nuevo — primer caso de
  capacidad OR en el backend): concede acceso si el subject tiene cualquiera de las dos; **precedencia de
  ámbito** (`scenario-coverage` #7, fijada ahora para no heredar la ambigüedad): se evalúa cada capacidad
  del OR con la misma regla que `get_tenant_context` (si alguna concede ámbito `global`, abre
  `global_scope`; si no, y alguna concede `tenant`, abre `tenant_scope`; si ninguna, `Deny`) — el orden
  de la tupla no importa, ámbito `global` siempre gana si existe en cualquiera de las dos.
- **Router `app/api/v1/routers/agent.py`**:
  - `POST /tickets/{id}/ai-draft` (capacidad `agent.trigger`) → `agent_service.trigger()`, 202 +
    `AgentRun`. 404 si el ticket no existe/es de otro tenant; 409 si `Conflict` (run activo); 429 si
    `RateLimited` (ya mapeados por el envelope central, sin `try/except` en el router).
  - `GET /agent-runs/{id}` (capacidad `agent.trigger` OR `ticket.read`) → `agent_service.get()`, 200 +
    `AgentRun`. 404 si de otro tenant (vía `tenant_scope`/`global_scope`, sin lógica extra).
- **`app/api/v1/schemas/agent.py`** (nuevo): `AgentRun` (espejo de `api-contract.yaml`, incl.
  `langsmith_trace_url`/`sources`/`error`).
- **`app/main.py`**: registra `agent_router` bajo `/api/v1`.
- **CU-BE-06 ampliado** (`.claude/specs/backend/casos-de-uso/CU-BE-06-draft-ia-y-aprobacion-hitl.md`):
  nuevos escenarios de disparo (409 por run activo, 429 por rate-limit) — hoy el CU empieza en `decide`
  con el run ya existente, no narra el disparo HTTP.

## Fuera de alcance

- Ejecutar `classify→retrieve→grade→generate→decide` (FR-022, grafo real) → planes 15/16.
- Interrupción real / creación de `ApprovalTask(pending)` desde el grafo → plan 16.
- Rate-limiting **compartido entre procesos** (Redis/almacén distribuido) → hueco sin dueño, mismo
  criterio que el throttling de `/auth/login`/`/auth/refresh` dejado abierto por `routers-core`.
- Streaming SSE del draft → Fase 1 es solo request/polling.
- Cola de aprobaciones (`/approvals`), notificaciones, analytics → tareas 02/03/05 de este plan.

## Scenarios (Gherkin)

Criterios de aceptación de base en el caso de uso (ampliado por esta tarea con los escenarios de disparo):
- [CU-BE-06 — Draft IA y aprobación HITL](../../../specs/backend/casos-de-uso/CU-BE-06-draft-ia-y-aprobacion-hitl.md)

```gherkin
Feature: disparo y lectura de un run de agente (grafo real aún no existe)

  Scenario: disparar un draft crea un AgentRun en cola
    Given un ticket sin ningún run activo y un subject con agent.trigger
    When hace POST /tickets/{id}/ai-draft
    Then recibe 202 con un AgentRun status=queued y thread_id=ticket_{id}_run_1

  Scenario: disparar dos veces el mismo ticket sin que el primero termine es un conflicto
    Given un ticket con un AgentRun status=queued ya creado
    When se dispara POST /tickets/{id}/ai-draft de nuevo
    Then recibe 409 y no se crea un segundo AgentRun

  Scenario: dos disparos concurrentes sobre el mismo ticket, solo uno gana
    Given un ticket sin ningún run activo
    When llegan dos POST /tickets/{id}/ai-draft al mismo tiempo
    Then como mucho uno recibe 202 y el otro recibe 409 (nunca dos 202)

  Scenario: exceder el límite de disparos del tenant devuelve 429
    Given un tenant que ya disparó ai_draft_rate_limit_per_minute veces en la ventana actual
    When dispara un ai-draft más dentro de la misma ventana
    Then recibe 429 y no se crea ningún AgentRun

  Scenario: el disparo número límite (el último permitido) se acepta
    Given un tenant que lleva ai_draft_rate_limit_per_minute - 1 disparos en la ventana actual
    When dispara un ai-draft más (el número límite exacto)
    Then recibe 202 y se crea el AgentRun

  Scenario: tras expirar la ventana, el tenant vuelve a poder disparar
    Given un tenant que agotó su cuota en una ventana ya expirada
    When dispara un ai-draft en la ventana nueva
    Then recibe 202 (la cuota de la ventana anterior no arrastra)

  Scenario: el límite de un tenant no afecta a otro
    Given un tenant que agotó su cuota en la ventana actual
    When otro tenant dispara un ai-draft en la misma ventana
    Then el segundo tenant recibe 202

  Scenario: disparar sobre un ticket inexistente devuelve 404, no 409
    Given un ticket_id que no existe
    When hace POST /tickets/{id}/ai-draft
    Then recibe 404 y no se consume cuota de rate-limit ni se crea ningún AgentRun

  Scenario: disparar sobre un ticket de otro tenant devuelve 404
    Given un ticket que pertenece a otro tenant
    When un subject sin ámbito global hace POST /tickets/{id}/ai-draft
    Then recibe 404 (no revela que el ticket existe en otro tenant)

  Scenario: un subject sin agent.trigger no puede disparar
    Given un subject sin la capacidad agent.trigger
    When hace POST /tickets/{id}/ai-draft
    Then recibe 403 y no se crea ningún AgentRun

  Scenario: reabrir un ticket con un run anterior no terminal sigue bloqueando un nuevo disparo
    Given un ticket con un AgentRun status=queued creado por un run anterior
    When se reabre el ticket y se dispara un nuevo ai-draft
    Then recibe 409 — limitación conocida y aceptada hasta que 15/16 exista y cierre el run anterior

  Scenario: leer el estado de un run existente
    Given un AgentRun ya creado
    When hace GET /agent-runs/{id}
    Then recibe 200 con su status/confidence/sources/error actuales

  Scenario: un run de otro tenant es invisible
    Given un AgentRun que pertenece a otro tenant
    When un subject sin ámbito global hace GET /agent-runs/{id}
    Then recibe 404 (no revela que el run existe en otro tenant)

  Scenario: un rol de solo lectura ve el estado sin poder disparar
    Given un subject con ticket.read pero sin agent.trigger, y un AgentRun de su tenant
    When hace GET /agent-runs/{id}
    Then recibe 200 (la capacidad compuesta agent.trigger OR ticket.read lo permite)

  Scenario: un subject sin agent.trigger ni ticket.read no puede leer el run
    Given un subject sin agent.trigger ni ticket.read
    When hace GET /agent-runs/{id}
    Then recibe 403
```

## Provides

- `app.domain.ports.agent_runner.AgentRunner.trigger()`, `app.domain.ports.rate_limiter.RateLimiter`,
  `app.domain.services.agent_service.AgentService` (o función equivalente), `app.core.deps.
  get_agent_service`, `app.core.deps.require_any_capability` (reutilizable por futuros endpoints con
  capacidad OR), router `agent.py` montado en `/api/v1`.

## Definition of Done

- [x] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [x] Cada escenario Gherkin tiene al menos un test (camino feliz + bordes/errores)
- [x] Todos los tests en verde
- [x] Spec cumplida; lo declarado en `Provides` queda realmente disponible para las tareas dependientes
- [x] Lint / format / typecheck OK
- [x] Gate de mutation testing superado (`cosmic-ray`, `break:80`) — `StubAgentRunner` documentado N/A
  (sin ramas condicionales), el resto sí entró en el gate (ver session log)
- [x] Gate `sdd-lint` superado (CU-BE-06 ampliado, sin ERROR; 1 AVISO de trazabilidad resuelto con FR-040)
- [x] Gate `fact-checker` superado (19/19 afirmaciones VERIFICADO)
- [x] Documentación — TSDoc + doc técnica (CU-BE-06, `spec.md` FR-040) + session log
- [x] Docs de dev/usuario donde aplique (N/A — sin superficie de usuario final nueva, solo API)
