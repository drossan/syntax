---
id: backend-routers-flujo-ia
package: backend
status: active
branch: plan/backend/routers-flujo-ia
created: 2026-08-19
updated: 2026-08-20
---

# Backend — Routers flujo-IA (agent · approvals · notifications · analytics)

## Contexto y problema

El plan `domain-services` (mergeado, PR #4) dejó cerrada la lógica de negocio pura: `approval_service`
(cola + `decide()`, compone `ApprovalRepository`/`TicketService`/`AgentRunner`), `notification_service`
(emitir/listar/marcar-leída/contar-no-leídas, desacoplado) y `classification` (contrato + `ChatModel.classify`
recortado). El plan `routers-core` (mergeado, PR #5) dejó los 7 routers "core" con código real
(`auth`/`tickets`/`messages`/`admin_*`/`kb`) y toda la infraestructura transversal que este plan reutiliza:
`app.core.deps` (`get_current_subject`/`get_tenant_context`/`require_capability`), el envelope de error
`problem+json` (`app.api.errors`), `Page`/`Problem` (`app.api.v1.schemas.common`), y el patrón de
adaptador SQLAlchemy (`app.infra.db.repositories.*`, `PortError` envolviendo fallos de infra).

Este es el **plan 12 del roadmap** (`IMPLEMENTATION-GUIDE.md §2`, bloque 4): los 4 routers marcados
**"→ tarea 12"** en su propio guión (`app/api/v1/routers/{agent,approvals,notifications,analytics}.py`,
verificado leyendo los 4 ficheros — hoy solo tienen el docstring "GUIÓN") + sus `schemas/`. Ninguno de los
dos consumidores reales del **grafo LangGraph** (planes **15**/definición del grafo y **16**/checkpointer+HITL)
existe todavía — es intencional: este plan solo conecta HTTP↔dominio hasta donde el dominio ya construido
(10) llega, dejando el resto como **hueco nombrado** para 15/16 (ver Fuera de alcance, Objetivo 0).

**Gaps reales detectados durante la exploración** (verificados leyendo el código, no supuestos):
1. `app/domain/ports/agent_runner.py` (`AgentRunner`) solo tiene `resume()` (nace en `domain-services`
   para `approval_service`). **No existe** ningún puerto/servicio para **disparar** un run (`POST
   /tickets/{id}/ai-draft`) ni para leerlo (`GET /agent-runs/{id}`) — ninguna tarea anterior los necesitaba.
2. `app/domain/ports/repositories.py` tiene `AgentRunRepository`/`ApprovalRepository`/
   `NotificationRepository` (puertos, `domain-services`) pero **cero adaptadores SQLAlchemy** — no están en
   `app/infra/db/repositories/__init__.py` (verificado: solo hay adaptadores de identidad + `ticket`/
   `message`/`audit_log`).
3. `ApprovalRepository.list_pending(tenant_id) -> list[...]` (sin paginar) no cubre lo que pide
   `api-contract.yaml` para `GET /approvals`: `Page` + filtro `status` + `sort` — necesita ampliarse (mismo
   criterio que `routers-core` decisión 3: "extensiones a domain-services que los routers necesitan de
   verdad se hacen dentro de este plan").
4. `NotificationRepository.list_for_user(user_id) -> list[...]` (sin paginar/filtrar) no cubre `GET
   /notifications` (`Page` + filtro `unread` + paginación) — mismo criterio de ampliación.
5. **`GET /analytics/summary` no tiene FR ni CU** en la capa SDD (`grep` sobre `spec.md`: cero menciones de
   "analytics"/"dashboard"). Decisión tomada con el owner: se añade **solo una FR nueva** a `spec.md`
   (sin CU dedicado — es una lectura agregada de un solo paso, sin actores/flujos alternativos que
   justifiquen un Cockburn completo).
6. `GET /agent-runs/{id}` no tiene capacidad propia en `rbac.md`. Decisión tomada con el owner: se protege
   con **`agent.trigger`** (misma capacidad que dispara el draft).
7. `routers-core` dejó explícitamente **FR-038 sin cablear** ("notificar tras `ticket.assign`/
   `ticket.reply`") como hueco nombrado para **este plan** ("que ya toca `notifications.py`") — entra como
   Objetivo 4.
8. Los 4 routers **no están registrados** en `app/main.py` (verificado: solo 7 `include_router` para los
   de `routers-core`).

## Objetivos

0. **Disparo y lectura de un run de agente, con el grafo aún sin existir (15/16)**.
   - Puerto `AgentRunner` **ampliado** con `trigger(tenant_id, ticket_id) -> AgentRun` (nuevo método,
     junto al `resume()` ya existente); adaptador `StubAgentRunner` (`app/infra/agent_runner/stub.py`,
     nuevo): crea el `AgentRun` (`status=queued`, `run_seq` vía `AgentRunRepository.next_run_seq`,
     `langgraph_thread_id=f"ticket_{ticket_id}_run_{run_seq}"`) y **no ejecuta ningún grafo** — mismo
     criterio que `StubVectorStore`/`StubSlaPolicy` de `routers-core` (adaptador real = tarea futura, aquí
     sin ninguna rama condicional).
   - `app/domain/services/agent_service.py` (nuevo, extiende dominio dentro de este plan — mismo criterio
     que la decisión 3 de `routers-core`): `trigger(tenant_id, ticket_id)` rechaza con `Conflict` (409) si
     ya hay un `AgentRun` no terminal (`queued`/`running`) para ese ticket (requiere un método nuevo en el
     puerto, `AgentRunRepository.get_active_for_ticket(ticket_id) -> AgentRun | None`); `get(agent_run_id)`
     lanza `NotFound` si no existe (mismo scope por tenant que `ticket_service.get` — un run de otro
     tenant es invisible, nunca 403, `grilling` P5).
   - **CAS real contra la carrera "dos runs activos a la vez"** (`design-review` #1, bloqueante): el check
     (`get_active_for_ticket`) + creación (`add`) es check-then-act, igual que el footgun que
     `decide_if_pending`/`rotate_if_active` evitan con CAS — con dos requests concurrentes sobre el mismo
     ticket, el 409 no es fiable sin más. **Migración Alembic nueva**: índice único parcial en
     `agent_run(ticket_id)` `WHERE status IN ('queued','running')`. El adaptador
     `SqlAlchemyAgentRunRepository.add()` captura la violación de esa constraint (`IntegrityError`) y la
     traduce a `Conflict` — mismo nivel de garantía real que los otros dos puertos con CAS del dominio.
   - **Rate-limiting mínimo, in-memory** (`grilling` P7/P7b, amplía el alcance original): puerto
     `RateLimiter` (recortado a `check_and_increment(key: str) -> bool`) + adaptador
     `InMemoryRateLimiter` (`app/infra/rate_limit/in_memory.py`, nuevo, ventana fija por proceso);
     `agent_service.trigger()` lo consulta **antes** de la comprobación de 409, con `key=str(tenant_id)`
     — límite **por tenant**, umbral configurable en `Settings` (`ai_draft_rate_limit_per_minute`,
     default `10`). Nuevo error de dominio `RateLimited` (`app/domain/errors.py`) mapeado a **429** en
     `app.api.errors` (mismo patrón que el resto de la taxonomía: `NotFound`→404, etc.).
     **`design-review` #2 (bloqueante, config duplicada)**: `app/core/config.py` **ya tenía**
     `ai_draft_max_per_ticket: int = 10` (nacido del refuerzo B.1 de `scenario-coverage` en
     `skeleton-foundation`, nunca implementado, semántica por-ticket/de-por-vida). Se **elimina** ese
     campo (junto con su test en `tests/test_config.py`) y se sustituye por
     `ai_draft_rate_limit_per_minute` — un único concepto de límite, sin dos campos de "límite" viviendo
     en paralelo sin infraestructura compartida.
     **Limitación documentada, no resuelta aquí**: al ser in-memory-por-proceso, con más de un
     worker/instancia el límite real es `N × nº de procesos` (sin estado compartido) — la solución real
     (Redis/almacén compartido) queda fuera de este plan, mismo criterio que otros huecos de infra ya
     documentados (incl. el throttling de `/auth/login`/`/auth/refresh`, que comparte el mismo `RateLimited`
     del contrato y sigue sin implementar).
   - **Capacidad de `GET /agent-runs/{id}` ampliada** (`design-review` #4): `agent.trigger` **por sí sola**
     dejaba ciegos a `support_viewer`/`client_viewer` (sin esa capacidad) frente al estado de un draft de
     un ticket que sí pueden leer. Se protege con **`agent.trigger` OR `ticket.read`** (basta una) — nuevo
     helper compuesto en `app/core/deps.py` (primer caso de capacidad compuesta en el backend; los routers
     existentes solo usan `require_capability(<una>)`).
   - Router `agent.py`: `POST /tickets/{id}/ai-draft` (capacidad `agent.trigger`, 202 + `AgentRun`, 409 si
     ya hay run en curso — ahora respaldado por el índice único parcial —, 429 si excede el rate-limit) ·
     `GET /agent-runs/{id}` (capacidad `agent.trigger` OR `ticket.read`, `grilling` P5: 404 si el run
     pertenece a otro tenant, nunca 403).
   - *Criterio de éxito*: dos disparos **concurrentes** sobre el mismo ticket → como mucho uno crea el
     `AgentRun`, el otro recibe 409 (garantizado por el índice único parcial, no solo por el check previo);
     más de `ai_draft_rate_limit_per_minute` disparos de un mismo tenant en la ventana → 429; el `AgentRun`
     creado queda `queued` para siempre hasta que 15/16 lo procesen — **limitación conocida y aceptada**
     (`grilling` P1): con este plan, un ticket solo puede disparar un `ai-draft` una vez hasta que 15/16
     exista y mueva el run a un estado terminal; un `support_viewer`/`client_viewer` con `ticket.read`
     puede consultar el estado del draft sin poder dispararlo.
   - **Fuera de alcance nombrado**: ejecutar `classify→retrieve→grade→generate→decide` (FR-022, grafo real)
     → 15/16. Rate-limiting **compartido entre procesos** (Redis/almacén distribuido) → hueco sin dueño,
     mismo criterio que el resto de rate-limiting de infra dejado abierto por `routers-core`.

1. **Cola de aprobación HITL completa por HTTP**.
   - `ApprovalRepository` **ampliado**: `list_pending(tenant_id)` se **reemplaza** por
     `list(tenant_id, *, status=None, sort, page, page_size) -> PageResult[ApprovalTask]` — sin `status`
     filtra solo `pending` (preserva el comportamiento actual por defecto), con `status` filtra por ese
     valor (`grilling` P2). **Corrección tras `design-review` #3**: la afirmación original ("sin
     consumidor real fuera de este plan, verificado") era incompleta — `ApprovalService.list_pending()`
     sí tiene un consumidor de **dominio** real (`tests/test_approval_service.py::
     test_list_pending_isolates_by_tenant`, de `domain-services`, ya mergeado). Este test **entra en el
     alcance de la tarea 02**: se actualiza (fake del puerto + expectativa de `PageResult`) junto con el
     reemplazo del método, no se descubre roto al cerrar. `approval_service` gana el método de cola
     equivalente sobre el nuevo puerto (mismo nombre o `list_queue`, a fijar al codificar). Adaptador
     `SqlAlchemyApprovalRepository` (`app/infra/db/repositories/approval.py`, nuevo).
   - Router `approvals.py`: `GET /approvals` (capacidad `approval.decide`, paginado + `status` + `sort`
     default `sla_due,confidence`) · `POST /approvals/{id}/approve|edit|reject` (delegan en
     `approval_service.decide()`, ya cerrado en `domain-services` — **sin cambios de lógica**, solo
     wiring HTTP + mapeo de errores `Conflict`→409/`Validation`→422 vía el envelope ya existente).
   - *Criterio de éxito*: `edit` sin `final_body` → 422; doble decisión sobre la misma tarea → 409 (ya
     garantizado por `approval_service.decide()`, aquí solo se verifica end-to-end vía HTTP); cola
     aislada por tenant (RLS + filtro app-level).

2. **Notificaciones in-app completas por HTTP**.
   - `NotificationRepository` **ampliado**: `list_for_user` gana paginación + filtro `unread: bool | None`
     (`PageResult[Notification]`, orden `-created_at` ya fijado). Adaptador
     `SqlAlchemyNotificationRepository` (`app/infra/db/repositories/notification.py`, nuevo).
   - Router `notifications.py`: `GET /notifications` (paginado, filtro `unread`, sin capacidad dedicada —
     alcance implícito al `user_id` del subject, mismo criterio que "una notificación solo la ve su
     destinatario" de CU-BE-10) · `PATCH /notifications/{id}/read`.
   - *Criterio de éxito*: `unread=true` no devuelve leídas; marcar una ya leída es no-op (ya garantizado
     por `notification_service.mark_read`, verificado aquí end-to-end); notificación de otro usuario →
     404 (no revela).

3. **`GET /analytics/summary`**.
   - Puerto + adaptador nuevos `AnalyticsRepository` (`app/domain/ports/analytics.py` +
     `app/infra/db/repositories/analytics.py`): agregados vía SQL (no en Python) — tickets por `status`
     (`COUNT ... GROUP BY`), aprobaciones pendientes (`COUNT WHERE status=pending`), confianza media
     (`AVG(confidence) WHERE confidence IS NOT NULL`), breaches de SLA (`COUNT WHERE sla_due < now() AND
     status NOT IN (resolved, closed)`). **Sin clase de servicio** (`grilling` P3): `app/domain/services/
     analytics.py` expone una **función suelta** `async def summary(analytics_repo: AnalyticsRepository,
     tenant_id: uuid.UUID | None) -> AnalyticsSummary` — mismo criterio que `classification.classify()`
     (sin estado que inyectar por constructor, una clase de un solo método sería ceremonia sin beneficio).
   - Router `analytics.py`: `GET /analytics/summary` (capacidad `analytics.read`; agregados acotados al
     tenant del subject salvo ámbito `global`, vía `get_tenant_context` — mismo patrón que el resto).
   - **`spec.md` gana 1-2 FR nuevas** documentando el contrato de agregados (decisión del owner: sin CU
     dedicado).
   - *Criterio de éxito*: un tenant nunca ve agregados de otro (ámbito `tenant`); Soporte (`global`) ve
     cross-tenant; sin tickets/runs → todos los contadores en 0 y `confianza media = null` (no `NaN`/error
     de división por cero).

4. **Cierra el hueco de FR-038 dejado por `routers-core`**: tras un `ticket.assign` con éxito, emitir
   `Notification(type=ticket_assigned)` al `assignee_id`; tras un `ticket.reply` (mensaje `public` nuevo),
   emitir `Notification(type=ticket_reply)` a **`{requester_id, assignee_id} - {autor del mensaje}`**, sin
   notificar a `None` (`grilling` P4 — regla determinista sin `if` ad-hoc por caso: cubre agente asignado
   responde → notifica al cliente; cliente responde → notifica al agente asignado si existe; un tercer
   agente no asignado responde → notifica a ambos). Se cablea en los routers ya existentes
   (`tickets.py`/`messages.py`, de
   `routers-core`, cerrados) llamando a `notification_service.emit(...)` tras la operación exitosa —
   **orquestación de router**, no lógica nueva en `ticket_service`/`MessageRepository` (mismo criterio que
   "la notificación es best-effort, no atómica con lo que la dispara").
   - *Criterio de éxito*: asignar un ticket genera 1 notificación al nuevo `assignee_id` (ninguna si
     `assignee_id=None`, desasignación); responder con `public` genera 1 notificación a la otra parte
     (ninguna en mensajes `internal`).
   - **Fuera de alcance nombrado**: `approval_requested` (lo crea el grafo vía `interrupt()`, 15/16) y
     `sla_warning`/`sla_breach` (scheduler, tarea 18) — ningún evento de esos dos tipos se dispara desde
     este plan.

## Alcance y fuera de alcance

### Dentro del alcance
- `app/domain/ports/agent_runner.py`: método nuevo `trigger()`.
- `app/domain/ports/repositories.py`: `AgentRunRepository.get_active_for_ticket` (nuevo);
  `ApprovalRepository.list_pending` **reemplazado** por `list(...)` paginado/filtrable;
  `NotificationRepository.list_for_user` con paginación + `unread`.
- `app/domain/ports/analytics.py` (nuevo, recortado a `summary()`).
- `app/domain/ports/rate_limiter.py` (nuevo, `RateLimiter.check_and_increment(key) -> bool`).
- `app/domain/errors.py`: nuevo `RateLimited` (taxonomía HTTP-derivable, →429 en `app.api.errors`).
- **Migración Alembic nueva**: índice único parcial en `agent_run(ticket_id)` `WHERE status IN
  ('queued','running')` (`design-review` #1, CAS real contra runs duplicados).
- `app/core/config.py` (`Settings`): `ai_draft_rate_limit_per_minute` (default `10`, nuevo); **se
  elimina** `ai_draft_max_per_ticket` (nunca implementado, redundante — `design-review` #2) y su test en
  `tests/test_config.py`.
- `app/infra/rate_limit/in_memory.py` (nuevo, `InMemoryRateLimiter`, ventana fija por proceso).
- `app/core/deps.py`: helper de capacidad **compuesta** (`agent.trigger` OR `ticket.read`) para
  `GET /agent-runs/{id}` (`design-review` #4).
- `app/domain/services/agent_service.py` (nuevo).
- `app/domain/services/analytics.py` (nuevo, función suelta `summary()`, sin clase).
- `tests/test_approval_service.py`: actualizar `test_list_pending_isolates_by_tenant` (fake + expectativa)
  tras el reemplazo de `list_pending` por `list(...)` (`design-review` #3).
- `app/domain/services/approval_service.py` / `notification_service.py`: ampliación de firma donde el
  punto anterior lo exige (sin tocar la lógica de `decide()`/`emit()`/`mark_read()` ya cerrada).
- `app/infra/agent_runner/stub.py` (nuevo, `StubAgentRunner`).
- `app/infra/db/repositories/{approval,agent_run,notification,analytics}.py` (nuevos adaptadores
  SQLAlchemy, mismo patrón que `ticket.py`/`message.py`).
- `app/api/v1/routers/{agent,approvals,notifications,analytics}.py` (código real, sustituye el GUIÓN).
- `app/api/v1/schemas/{agent,approvals,notifications,analytics}.py` (nuevos, espejo del contrato).
- `app/core/deps.py`: `get_agent_service`/`get_approval_service`/`get_notification_service`/
  `get_analytics_repository` (mismo patrón `get_*_service` ya existente).
- `app/main.py`: registra los 4 routers nuevos (`include_router`, prefijo `/api/v1`).
- Wiring de `notification_service.emit()` en `tickets.py` (`assign`) y `messages.py` (reply público) —
  ambos de `routers-core`, ya cerrados.
- `.claude/specs/backend/spec.md`: 1-2 FR nuevas para `analytics.summary` (Objetivo 3).
- Tests de **integración** (Postgres real, Docker) para adaptadores/routers — mismo nivel que
  `routers-core`.

### Fuera de alcance
- **El grafo LangGraph real** (`app/agents/{state,graph,tools,nodes}.py`) y el **checkpointer/HITL real**
  (`app/agents/{checkpointer,hitl,runner}.py`) → planes **15**/**16**. `StubAgentRunner.trigger()` no
  ejecuta `classify→retrieve→grade→generate→decide` (FR-022): crea el `AgentRun` y se detiene ahí.
- **Interrupción real / creación de `ApprovalTask(pending)` desde el grafo** (`interrupt()`, FR-026) → 16.
  Sin grafo real, ningún `ApprovalTask` se crea automáticamente en este plan; la cola de `/approvals`
  queda funcionalmente vacía hasta 16 (mismo criterio que `kb.search` con el `VectorStore` stub en
  `routers-core`: el router es real, el generador de datos no).
- **Rate-limiting distribuido de `POST /tickets/{id}/ai-draft`** (Redis/almacén compartido entre
  procesos/instancias): este plan implementa un límite **mínimo in-memory por proceso** (Objetivo 0,
  `grilling` P7/P7b) — la limitación multi-proceso (`N × nº de procesos`) queda documentada y sin
  resolver, mismo criterio que el rate-limiting de `/auth/login`/`/auth/refresh` dejado abierto por
  `routers-core`.
- **Streaming SSE** del draft (`agent-graph.md §9`, seam para fase posterior) — Fase 1 es solo
  request/polling.
- **`approval_requested`/`sla_warning`/`sla_breach`** como eventos que disparan `notification_service.emit`
  → 15/16 (creación de `ApprovalTask`) y 18 (scheduler SLA), respectivamente. Este plan solo cablea
  `ticket_assigned`/`ticket_reply` (Objetivo 4).
- **`notification_service.count_unread()` expuesto por HTTP**: el contrato actual (`GET /notifications`)
  no tiene un campo/endpoint de conteo separado — sigue sin consumidor HTTP (hueco ya nombrado en
  `domain-services`, no se resuelve aquí porque no hay endpoint que lo pida).
- **CU-BE dedicado para analytics**: decisión del owner (ver Contexto, punto 5) — solo FR en `spec.md`.
- **Gate OpenAPI "generado ⊇ contrato" automatizado en CI** → tarea 19 (igual que `routers-core`); en este
  plan sigue siendo gate manual por tarea.
- **CAS/optimistic-concurrency en el nuevo método de cola de `ApprovalRepository`**: no se introduce
  ninguno nuevo — el único punto con CAS real sigue siendo `decide_if_pending` (ya cerrado); el método de
  listado es de solo lectura.

## Recursos externos

- `.claude/specs/general/api-contract.yaml`: paths `/tickets/{id}/ai-draft`, `/agent-runs/{id}`,
  `/approvals`, `/approvals/{id}/{approve,edit,reject}`, `/notifications`, `/notifications/{id}/read`,
  `/analytics/summary`; schemas `AgentRun`, `ApprovalTask`, `ApprovalStatus`, `Notification`,
  `AnalyticsSummary`, `Page`, `Problem`.
- `.claude/specs/backend/agent-graph.md`: contrato del grafo (§2-§9) — fija qué le toca a 15/16 y qué NO
  hace este plan; `thread_id=ticket_{id}_run_{n}` (§6.1).
- `.claude/specs/backend/spec.md`: FR-022..031 (flujo-IA), FR-038 (notificaciones); FR nuevas de este plan
  para analytics (Objetivo 3).
- CUs: `CU-BE-06-draft-ia-y-aprobacion-hitl.md` (HITL, ya con Gherkin — este plan NO añade escenarios
  nuevos al CU, solo lo conecta por HTTP hasta donde el dominio llega), `CU-BE-10-notificaciones-in-app.md`.
- `.claude/specs/backend/rbac.md`: capacidades ya en catálogo (`agent.trigger`, `approval.decide`,
  `analytics.read`) — ninguna capacidad nueva se añade en este plan.
- `app/domain/services/{approval_service,notification_service}.py`, `app/domain/ports/{agent_runner,
  repositories}.py` (plan `domain-services`, se amplían aquí).
- `app/core/deps.py`, `app/api/errors.py`, `app/api/v1/schemas/common.py`, `app/infra/db/repositories/
  {ticket,message}.py` (plan `routers-core`, patrones a reutilizar).
- `tests/conftest.py` (fixtures Postgres real: `migrated_database`/`app_engine`/`superuser_engine`).
- `backend/IMPLEMENTATION-GUIDE.md §2/§5` (orden de build, gate manual OpenAPI⊇contrato).

## Estimación global

- **Tareas**: 5 (agent trigger+stub+router · approvals cola+router · notifications cola+router ·
  wiring FR-038 · analytics).
- **Esfuerzo**: nivel integración (Postgres real, como `routers-core`), pero sin rediseño de identidad ni
  migraciones nuevas — más pequeño y acotado que `routers-core`; ~2 sesiones asistidas (la tarea 01 crece
  algo tras `grilling` al incorporar el rate-limiter).
- **Recursos**: requiere `docker compose up -d db`.

## Criterios de calidad y verificación

- TDD, nivel **integración** para adaptadores/routers (Postgres real, Docker); el `StubAgentRunner` es
  declarativo (sin ramas condicionales) → mutation N/A documentado, mismo criterio M4 de planes anteriores.
- Gates por tarea: `ruff`(+`S`) · `ruff format` · `mypy --strict` · `cosmic-ray` (`break:80`) donde aplique
  · `/sdd-lint` · `fact-checker`.
- Hexagonal: adaptadores en `app/infra/*`; routers no importan SQLAlchemy directamente ni contienen lógica
  de negocio (delegan en `agent_service`/`approval_service`/`notification_service`/el adaptador de
  analytics).
- OpenAPI generado se compara manualmente contra el contrato al cerrar cada router (gate automatizado
  sigue siendo tarea 19).
- La FR nueva de analytics se añade a `spec.md` en la propia tarea que construye el router (Objetivo 3),
  no como efecto colateral silencioso.

## Tasks

- [x] `backend-routers-flujo-ia-01` (P1) — Migración (índice único parcial `agent_run`) +
  `AgentRunner.trigger()` (puerto) + `StubAgentRunner` + `AgentRunRepository.get_active_for_ticket` +
  adaptador `SqlAlchemyAgentRunRepository` (CAS vía `IntegrityError`→`Conflict`) + puerto `RateLimiter` +
  `InMemoryRateLimiter` + error `RateLimited`→429 + elimina `ai_draft_max_per_ticket` + `agent_service`
  (rate-limit → 409 si hay run en curso → trigger; get con scope por tenant) + capacidad compuesta
  `agent.trigger` OR `ticket.read` en `deps.py` + router `agent.py` completo · depends_on: —
- [ ] `backend-routers-flujo-ia-02` (P1) — `ApprovalRepository` ampliado (cola paginada/filtrable,
  reemplaza `list_pending`) + actualiza `tests/test_approval_service.py` + adaptador
  `SqlAlchemyApprovalRepository` + `approval_service` (ampliación de cola) + router `approvals.py`
  completo · depends_on: —
- [ ] `backend-routers-flujo-ia-03` (P2) — `NotificationRepository` ampliado (paginación + `unread`) +
  adaptador `SqlAlchemyNotificationRepository` + `notification_service` (ampliación de listado) + router
  `notifications.py` completo · depends_on: —
- [ ] `backend-routers-flujo-ia-04` (P2) — Cierra FR-038: cablea `notification_service.emit()` en
  `tickets.py` (`assign`→`ticket_assigned`) y `messages.py` (reply público→`ticket_reply`) · depends_on: 03
- [ ] `backend-routers-flujo-ia-05` (P3) — Puerto+adaptador `AnalyticsRepository` (agregados SQL) + FR
  nueva en `spec.md` + router `analytics.py` completo · depends_on: 01, 02

## Registro de cambios del plan

- 2026-08-19: creado (draft para grilling). Decisiones tomadas con el owner antes de redactar: (1)
  `GET /agent-runs/{id}` se protege con `agent.trigger` (misma capacidad que dispara el draft, no
  `ticket.read`); (2) el hueco de SDD de `analytics.summary` (sin FR ni CU) se cierra solo con FR nueva
  en `spec.md`, sin CU dedicado (lectura agregada de un solo paso, sin flujos alternativos que
  justifiquen un Cockburn completo).
- 2026-08-20: refinado con `grilling` (8 preguntas, 8 decisiones). (P1) Regla 409 de `agent_service.
  trigger` se mantiene tal cual, con una limitación **aceptada y documentada**: sin grafo real (15/16),
  un `AgentRun` creado por este plan queda `queued` para siempre, así que un ticket solo puede disparar
  un `ai-draft` una vez hasta que 15/16 exista. (P2) `ApprovalRepository.list_pending` (sin consumidor
  real, verificado) se **reemplaza** por `list(tenant_id, status=None, sort, page, page_size)` en vez de
  convivir con un método nuevo — sin `status` preserva el comportamiento actual (solo `pending`). (P3)
  `analytics.summary` es una **función suelta** (`app/domain/services/analytics.py`), no una clase de
  servicio — mismo criterio que `classification.classify()` (sin estado, una clase sería ceremonia). (P4)
  Destinatarios de la notificación `ticket_reply`: `{requester_id, assignee_id} - {autor del mensaje}`,
  sin `None` — regla determinista que cubre los 3 casos reales sin `if` ad-hoc. (P5) `GET
  /agent-runs/{id}` de otro tenant → 404 vía `tenant_scope`/`global_scope` (mismo patrón que `tickets`),
  nunca 403 (no revela existencia). (P6) Se mantienen las 5 tareas del draft, ninguna se parte/fusiona.
  (P7/P7b) **Amplía el alcance original**: en vez de dejar el rate-limiting de `ai-draft` como hueco sin
  dueño, este plan implementa un límite **mínimo in-memory por tenant** (puerto `RateLimiter` +
  `InMemoryRateLimiter`, ventana fija, umbral configurable `ai_draft_rate_limit_per_minute` default 10,
  nuevo error de dominio `RateLimited`→429) — la limitación multi-proceso (`N × nº de procesos`, sin
  estado compartido) queda documentada y sin resolver (Redis/almacén distribuido, fuera de este plan).
  (P8) El rate-limiter entra en la tarea 01 (mismo cambio coherente que `agent_service.trigger()`, no una
  tarea 06 dedicada — no tiene sentido probarlo aislado de lo que protege).
- 2026-08-20: `design-review` (subagente fresco, sin routing válido en `models.design-review` — el valor
  configurado `claude-opus-4-8` no es un id de modelo vigente, mismo problema ya detectado en
  `routers-core`; se avisó y se lanzó heredando el modelo de sesión). **4 hallazgos, 3 bloqueantes/con
  decisión del owner, ninguno "me parece bien" sin evidencia**: (1, bloqueante) `agent_service.trigger()`
  era check-then-act sin CAS —mismo footgun que `decide_if_pending`/`rotate_if_active` ya evitan—, dos
  requests concurrentes podían crear 2 `AgentRun` para el mismo ticket; resuelto con **índice único
  parcial** en `agent_run(ticket_id)` `WHERE status IN (queued,running)` + `IntegrityError`→`Conflict` en
  el adaptador (tarea 01 ampliada). (2, bloqueante) `app/core/config.py` ya tenía
  `ai_draft_max_per_ticket` (B.1, nunca implementado) que el plan ignoraba al añadir
  `ai_draft_rate_limit_per_minute`; resuelto **eliminando el campo viejo** (y su test), un único concepto
  de límite (tarea 01 ampliada). (3, bloqueante de alcance) la afirmación "`list_pending` sin consumidor
  real, verificado" era incompleta — `test_approval_service.py::test_list_pending_isolates_by_tenant` lo
  ejercita y se rompía sin estar declarado; **añadido explícitamente a la tarea 02**. (4) `GET
  /agent-runs/{id}` con solo `agent.trigger` dejaba ciegos a `support_viewer`/`client_viewer` (sin esa
  capacidad) frente al estado de un draft que sí pueden leer; resuelto con capacidad **compuesta**
  `agent.trigger` OR `ticket.read` (tarea 01 ampliada, primer caso de este tipo en el backend). Ejes
  confirmados sin objeción: `analytics.summary()` como función suelta (mismo patrón que
  `classification.classify()`), `TenantMixin`/RLS en las 3 entidades nuevas, ausencia real de FR/CU de
  analytics, viabilidad del wiring de notificaciones sin tocar `ticket_service`/`MessageRepository`.
- 2026-08-20: `scenario-coverage` (subagente QA fresco, `sonnet` — modelo válido en `models.
  scenario-coverage`) sobre las 5 tareas ya materializadas + este plan como dato. **Hallazgos (A, dentro
  del alcance) incorporados a las tareas**: (tarea 01) faltaba comprobar que el ticket existe/pertenece
  al tenant antes de crear el `AgentRun` (un ticket inexistente habría dado 409 en vez de 404 al chocar
  con la FK); reordenados los chequeos de `agent_service.trigger()` de más barato a más caro (ticket →
  run activo, ahora sí con un uso real de `get_active_for_ticket` como pre-check — antes huérfano — →
  rate-limit → creación), para no gastar cuota ni tocar la constraint en un disparo que iba a fallar
  gratis; añadidos escenarios de frontera del rate-limit (N-ésimo aceptado, expiración de ventana,
  aislamiento entre tenants), 403, y el escenario explícito de la limitación ya aceptada "reabrir con un
  run anterior no terminal sigue bloqueando"; fijada la precedencia de ámbito de la capacidad compuesta
  `agent.trigger` OR `ticket.read` (gana `global` si cualquiera de las dos lo concede). (tarea 02) **bug
  real**: `approval.decide` es una capacidad exclusivamente `global` pero `ApprovalRepository.list`
  tenía `tenant_id` obligatorio — Soporte nunca habría visto ninguna aprobación (las `ApprovalTask` son
  de tenants cliente, nunca del tenant "syntax"); corregido a `tenant_id: uuid.UUID | None` (mismo patrón
  que la tarea 05); añadidos 404 en decisión sobre id inexistente, 403, escenario de ámbito global, y
  fijada la whitelist de `sort` al literal exacto `"sla_due,confidence"` (decisión del owner, sin
  flexibilidad no pedida). (tarea 03) `mark_read` no podía distinguir "no es mía/no existe" (404) de "es
  mía, ya leída" (200 idempotente) — añadido `NotificationRepository.get()` y `notification_service.get()`
  para que el router decida el código correcto antes de llamar a `mark_read`; fijada la semántica
  simétrica de `unread=false` (solo leídas, decisión del owner); añadidos escenarios de lista vacía y de
  las dos causas de 404. (tarea 04) fallo de `notification_service.emit()` tras la operación principal ya
  confirmada **no debe** propagar un error HTTP (envuelto en `try/except`, solo logueado) — único
  criterio coherente con "notificación best-effort" que el propio plan ya declaraba; excluido también el
  actor en la notificación de `ticket_assigned` (decisión del owner: autoasignarse no notifica, simétrico
  con `ticket_reply`); añadidos escenarios de reasignación y de fallo de asignación. (tarea 05) corregido
  el nombre de campo `pending_approvals`→**`approvals_pending`** (verificado contra `api-contract.yaml`
  línea 1299, discrepancia real detectada); fijado que `tickets_by_status` siempre trae las 6 claves de
  `TicketStatus` con `0` por defecto (decisión del owner); añadidos escenarios de frontera del SLA
  (exactamente `now()`, `sla_due=NULL`, ticket resuelto con SLA vencido) y 403. **(B) Fuera de alcance
  confirmado sin sorpresas**: los 10 huecos que el QA encontró fuera del alcance declarado (grafo real,
  interrupción real, rate-limiting multi-proceso, streaming SSE, cola vacía sin grafo, `count_unread` sin
  HTTP, tipos de notificación no cableados, retry/compensación de `emit()`, ausencia de CU de analytics,
  caché de analytics, gate OpenAPI automatizado) ya estaban todos nombrados explícitamente en el plan o en
  su tarea correspondiente — ninguno requirió ampliar el plan ni generó una decisión nueva del owner.
