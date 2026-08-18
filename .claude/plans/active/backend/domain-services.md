---
id: backend-domain-services
package: backend
status: active
branch: plan/backend/domain-services
created: 2026-08-18
updated: 2026-08-18
---

# Backend — Servicios de dominio + puertos (rbac · ticket · notification · auth · classification · approval)

## Contexto y problema

El plan `database-foundation` (mergeado a `main`, PR #3) dejó cerrada la capa de datos: 18 modelos ORM,
migración con RLS, `session.py` (aislamiento tenant), `BaseRepository` genérico y `/health/ready`. El
**dominio** (`app/domain/`) sigue siendo esqueleto doc-only: los ficheros de `services/` y `ports/` solo
tienen el "GUIÓN" en docstring. Este es el **plan 10 del roadmap** (`IMPLEMENTATION-GUIDE.md §2`): la
lógica de negocio pura (servicios) + los puertos que la infraestructura implementará, en **arquitectura
hexagonal** — el dominio no importa `app.infra` ni SQLAlchemy.

Scope pedido por el owner: `auth_service`, `rbac_service`, `ticket_service`, `approval_service`,
`notification_service`, `classification`.

**Decisiones tomadas con el owner antes de descomponer en tareas** (ver Registro de cambios: 10 de
`grilling` + 4 de `design-review`, más ~15 correcciones aplicadas directamente por evidencia de spec):
1. Entidades de dominio **completas** (Pydantic v2, con enums propios — el dominio no reusa
   `app.infra.db.models.enums`), con un **test de drift** dominio↔ORM (por valor, no por nombre).
2. `classification` y `approval_service` **entran** en el plan definiendo puertos-stub mínimos
   (`ChatModel.classify`, `AgentRunner.resume`, nuevo); los adaptadores reales llegan en 09/16.
3. `approval_service.decide()` **compone** `ticket_service` (transición a `pending` en approve/edit) y
   `AgentRunner.resume`, pero **NO** emite `Message` ni toca `agent_run.status` — eso lo escribe el nodo
   `respond` del grafo (16); `data-model.md`/`agent-graph.md`/CU-BE-06/`api-contract.yaml` coinciden en
   que la emisión del mensaje es del grafo, no de `approval_service` (contradicción real detectada por
   `design-review`, resuelta a favor de la evidencia cruzada, no del guión original del servicio).
4. Puertos de política (`SlaPolicy`, `ApprovalPolicy`) **nacen con su consumidor** (tarea de
   `ticket_service`/`approval_service`), no en una tarea de puertos centralizada sin llamante.
5. `app.core.security` (ya existente: Argon2id + JWT) se trata como **primitivas puras adyacentes al
   dominio** (no infra real) — `auth_service` las consume directamente; `secret`/`ttl` se pasan como
   parámetros desde el llamante, nunca los lee de `get_settings()` el propio servicio.

## Objetivos

1. **Entidades de dominio propias (Pydantic v2)** — identidad + negocio unificadas en una sola tarea (son
   igual de declarativas; partirlas no reduce riesgo, a diferencia de los 18 modelos ORM con constraints
   reales de `database-foundation`). Incluye `Subject`, `Resource` (necesarios para `authorize`) y
   `AuditLogEntry` (necesaria para el puerto de auditoría) — ninguno de los tres estaba nombrado en el
   draft inicial pese a que los objetivos 4/5/9 los requieren.
   - *Criterio de éxito*: `app.domain` no importa `app.infra`/SQLAlchemy (test de import estático); **test
     de drift**: los enums compartidos con `app.infra.db.models.enums` (`TicketStatus`, `TicketPriority`,
     `MessageVisibility`, `ApprovalStatus`, `AgentRunStatus`, `KbDomain`, `UserStatus`, `TenantStatus`,
     `RoleKind`, `CapabilityScope`, `AuthTokenKind`, `NotificationType`, **`RefreshSessionStatus`** —
     omitido en el draft inicial, corregido por `scenario-coverage`) tienen el **mismo conjunto de
     valores** (comparación por valor — el ORM ya tiene `CapabilityScope.global_ = "global"`, el dominio
     lo repite igual).
2. **`app/domain/errors.py`**: jerarquía de excepciones con **taxonomía estable** — bases derivables a
   HTTP (`NotFound`→404, `Conflict`→409, `InvalidTransition`→422/409, `Validation`→422), cada error
   concreto con un `code`/`type` slug estable + `details: dict` (para que el mapeo HTTP futuro, 11/12, sea
   una tabla de datos, no un árbol de `isinstance`). Incluye `PortError`/`ExternalServiceError` — los
   adaptadores reales (asyncpg/httpx/openai) SÍ lanzarán excepciones de infra a través de los puertos; el
   docstring de cada puerto documenta que el adaptador debe envolverlas.
3. **Puertos base**: `repositories.py` (Protocols reales para los agregados que los servicios llaman:
   Tenant, User, Role+Capability, RefreshSession (con **`rotate_if_active`** compare-and-set — mismo
   criterio que `decide_if_pending`, corregido por `scenario-coverage`: asimetría sin justificar entre
   ambos puertos), AuthToken, Ticket, Message, `ApprovalRepository` con **`decide_if_pending` que
   distingue `NotFound` (tarea inexistente) de `None`/conflicto (tarea existe pero ya no `pending`)** —
   ambigüedad detectada por `scenario-coverage`, AgentRun read/update, Notification, AuditLog), `clock.py`,
   `email.py`. Las firmas de `list`/cola llevan **orden y paginación explícitos** (el criterio "orden
   asertado" solo es real si el test comprueba los argumentos pasados al puerto, no el comportamiento del
   fake). `SlaPolicy`, `ChatModel`, `AgentRunner` **nacen en las tareas de su consumidor** (objetivos
   5/6/9), no aquí. `ApprovalPolicy` (auto_approve) **no nace en este plan** — ver objetivo 9.
   - *Criterio de éxito*: cada puerto tiene un fake mínimo que lo satisface (mypy structural).
4. **`rbac_service.authorize(subject, capability, scope, resource) -> Allow | Deny`** — fiel al contrato
   literal de `rbac.md §7`: **devuelve** (nunca lanza) por capacidad+ámbito, nunca por rol; fail-closed.
   `Deny` lleva un **discriminante** (`DenyReason.no_capability`→403, `DenyReason.out_of_scope`→404) — sin
   él, CU-BE-03/FR-011/FR-014 (403 vs 404, "no revelar existencia") no son representables desde un `Deny`
   opaco.
   - *Criterio de éxito*: FR-010/011/012/037 cubiertos con tests unit (mocks de `RoleRepository`).
5. **`ticket_service`**: máquina de estados + asignación + `sla_due` (vía puerto **`SlaPolicy.due_at
   (priority, from_, tenant_id) -> datetime | None`**, diseñado ya pensando en que la tarea 18 necesitará
   la misma política para el escalado — sin horas/días reales todavía, eso lo fija 18) + CSAT + auditoría.
   `reopen()` deja el ticket en **`reopened`** (estado de reposo real, confirmado por el Gherkin literal
   de CU-BE-04 — no auto-encadena a `open`); una transición posterior y separada `reopened → open` lo
   retoma. **Fuera de alcance nombrado** (FR-030): quién lanza el `agent_run` nuevo al reabrir y qué pasa
   con el `agent_run`/`approval_task` huérfanos del run anterior — no se le añade lógica a `ticket_service`
   sin spec que lo respalde; lo decide el plan que construya esa orquestación (12/15/16). `reopen()`
   **recalcula `sla_due`** vía `SlaPolicy` (coherente con "al crear/reabrir" del guión original).
   - *Criterio de éxito*: FR-016/017/018/020/021 cubiertos; transición inválida → `InvalidTransition`;
     CSAT fuera de `1..5` → `Validation` (Scenario Outline con las fronteras 0/1/5/6, añadido por
     `scenario-coverage`); asignar a un `assignee_id` de otro tenant → rechazado.
6. **`notification_service`**: emitir/listar/marcar-leída/**contar no-leídas** (`count_unread` — capacidad
   exigida por `data-model.md` RN-2, ausente en el draft inicial pese a que CU-BE-10 la consume;
   añadida por `scenario-coverage`), **desacoplado** — ningún otro servicio de este plan lo llama
   (criterio: la notificación es *best-effort*, no un acto atómico con lo que la dispara — a diferencia
   de `approval_service`/`ticket_service`, donde FR-027 trata resume+transición como un solo acto que debe
   abortar junto). `mark_read` valida que la notificación pertenezca al `user_id` (defensa app-level,
   mismo criterio que `BaseRepository`). La orquestación "tras aprobar/asignar, notifica" es del plan de
   routers (11/12).
   - *Criterio de éxito*: FR-038; orden `-created_at` en la firma del puerto, asertado por argumentos.
7. **`auth_service`**: login, refresh con rotación + reuse-detection, password reset/invitación (sobre
   `app.core.security` ya existente, tratado como primitivas puras — `secret`/`ttl` llegan como parámetros
   del llamante, el servicio no lee `get_settings()`). **Añade una primitiva nueva** a `app.core.security`:
   hash **determinista** de token opaco (`new_opaque_token()` + `hash_token()`, SHA-256 — Argon2 no sirve
   para `token_hash` porque su salt aleatorio hace la búsqueda por hash imposible; `refresh_session.
   token_hash`/`auth_token.token_hash` son `UNIQUE` y se buscan por igualdad). **No** implementa
   throttling de login (FR-006 es de la capa de routers). `refresh()` usa el nuevo
   `RefreshSessionRepository.rotate_if_active` (CAS — mismo criterio de `scenario-coverage` que
   `decide_if_pending`, evita el check-then-act del draft inicial).
   - *Criterio de éxito*: FR-001..005/007..009 cubiertos; reuse de un refresh ya rotado revoca toda la
     familia; `forgot` no revela si el email existe; refresh **caducado** (no reusado) se rechaza sin
     activar reuse-detection (escenario añadido por `scenario-coverage` — CU-BE-01 lo narra pero no lo
     Gherkin-iza).
8. **`classification`**: contrato `Classification{categoria, dominio: KbDomain | None, prioridad,
   resoluble}` vía `ChatModel.classify` (puerto recortado a solo `classify` en este plan — `generate`/
   `grade` son prematuros sin caller, quedan documentados en el docstring existente hasta que la tarea 15
   los necesite). **No depende de `ticket_service`**: el servicio solo `classify(ticket_text) ->
   Classification`; quien aplica el resultado a `Ticket.domain/priority` es el futuro llamante (grafo, 15),
   que conoce la secuencia — corrige el `depends_on` incoherente del draft inicial. `dominio=None` **es**
   la señal de "no clasificable con confianza" (sin inventar un campo `confidence` que FR-023 no pide).
   - *Criterio de éxito*: FR-023; `dominio=None` → el llamante recupera sin filtro (FR-024).
9. **`approval_service`**: cola (orden `sla_due,confidence` en la firma del puerto, **aislada por tenant**
   — escenario añadido por `scenario-coverage`). `decide()` **compone**: 1) `ApprovalRepository.
   decide_if_pending` (CAS — atomicidad real en el contrato del puerto, no en el servicio; tarea
   inexistente → `NotFound`; tarea existente pero ya no `pending` → `None` del puerto → el servicio lanza
   `Conflict`, nunca un segundo `resume` — distinción añadida por `scenario-coverage`, antes ambos casos
   colapsaban en el mismo `None`); 2) en `approve`/`edit`: transición del ticket a **`pending`** (vía
   `ticket_service` — B2: fijado ahora, no en "p.ej."; `edit` exige `final_body`, simétrico a que `reject`
   exige `human_note`); 3) `AgentRunner.resume(thread_id, outcome)`. **NO** emite `Message` ni toca
   `agent_run.status` (eso es del nodo `respond` del grafo, 16 — ver decisión 3 arriba). **`auto_approve`
   NO se resuelve en este plan**: `scenario-coverage` detectó que ningún método de `approval_service` en
   este plan **crea** una `ApprovalTask` — quien la crea es el grafo (`interrupt()`, CU-BE-06), así que el
   puerto `ApprovalPolicy` (B4 de design-review) se **retira** de esta tarea; auto_approve es un hueco
   nombrado para la tarea 16 (ver Fuera de alcance). **Fallo tras el CAS** (p.ej. `transition()` lanza
   después de que la `ApprovalTask` ya quedó `approved`): se **documenta como riesgo conocido**, sin
   lógica de compensación — a este nivel (servicio + fakes) no hay una transacción real que abarque dos
   repos distintos; eso es un problema de unit-of-work de infra, fuera de este plan (11/12).
   - *Criterio de éxito*: FR-026/027/028/029; nunca un segundo `resume` sobre el mismo thread.

## Alcance y fuera de alcance

### Dentro del alcance
- `app/domain/entities/{identity,business,enums}.py`: entidades Pydantic v2 (incl. `Subject`, `Resource`,
  `AuditLogEntry`) + enums propios + test de drift de valores contra `app.infra.db.models.enums`.
- `app/domain/errors.py`: jerarquía de excepciones con taxonomía estable + `PortError`.
- `app/domain/ports/`: `repositories.py` (Protocols reales, incl. `AuditLogRepository`, CAS en
  `ApprovalRepository.decide_if_pending` y `RefreshSessionRepository.rotate_if_active`), `clock.py`,
  `email.py`, y los puertos que nacen con su consumidor: `sla_policy.py` (con `ticket_service`), `llm.py`
  recortado a `classify` (con `classification`), `agent_runner.py` (con `approval_service`).
- `app/domain/services/*.py`: los 6 servicios, lógica pura, puertos por inyección de constructor.
- `app/core/security.py`: **añade** `new_opaque_token()` + `hash_token()` (primitiva determinista para
  `token_hash`) — toca un fichero fuera de `app/domain`, pero es un requisito duro de `auth_service`, no
  una ampliación de alcance.
- Tests **unit** (nivel `HOW-TO-START-A-TASK.md`: "Servicio/lógica de dominio → unit con mocks de
  puertos, sin infra") — **sin Docker**.

### Fuera de alcance
- **Adaptadores concretos** de los puertos (repos SQLAlchemy sobre `BaseRepository`, adaptador OpenAI,
  adaptador LangGraph/checkpointer, adaptador email SMTP) → tareas 09 (LLM), 11/12 (routers+adapters de
  repo), 15/16 (grafo/HITL).
- **`deps.get_tenant_context`/`get_current_subject`/`require_capability`** (orquestación FastAPI de
  `rbac_service`) → plan 11/12.
- **Emisión de `Message(public)` y transición de `agent_run.status`** al aprobar/editar/rechazar → nodo
  `respond` del grafo (tarea 16), no `approval_service` (ver decisión 3).
- **Quién lanza el `agent_run` nuevo al reabrir un ticket** (FR-030) y qué pasa con el `agent_run`/
  `approval_task` huérfanos del run anterior → hueco nombrado, sin dueño asignado todavía (12/15/16).
- **`auto_approve` por tenant** (quién consulta `ApprovalPolicy` y decide crear `ApprovalTask(pending)`
  vs. auto-materializar) → hueco nombrado para la tarea 16 (el grafo, que es quien crea la `ApprovalTask`
  vía `interrupt()`, CU-BE-06) — detectado por `scenario-coverage`: ningún método de `approval_service` en
  este plan crea tareas, así que no hay consumidor real de `ApprovalPolicy` aquí.
  Los valores concretos de la política tampoco se fijan (mismo criterio que `SlaPolicy`).
- **Fallo tras el CAS de `approval_service.decide()`** (la `ApprovalTask` ya quedó `approved`/`edited`
  pero un paso posterior — p.ej. `transition()` — falla): riesgo conocido documentado, sin compensación en
  este plan (requeriría una transacción real cross-repo, de infra) → 11/12.
- **Chequeo de `tenant.status=disabled`** en login/autorización/operaciones de ticket → hueco nombrado, sin
  dueño asignado; ninguna de las 8 tareas lo cubre (detectado por `scenario-coverage`).
- **Atribución del actor de auditoría en la transición compuesta** (cuando `approval_service.decide()`
  invoca `ticket_service.transition()`, qué `actor_id` queda en el `AuditLogEntry`) → hueco nombrado, sin
  dueño asignado.
- **Política de contraseña** (longitud/complejidad mínima en `reset_password`/`accept_invitation`) →
  hueco nombrado, sin dueño asignado; puede vivir en `auth_service` o en una capa de validación de
  entrada del router (11/12), a decidir cuando se construya esa tarea.
- **Payload por `NotificationType`** (forma exigida de cada tipo de evento) → `notification_service`
  acepta cualquier `dict`; el schema por tipo, si hace falta, se decide en 11/12.
- **Orquestación cross-servicio no compuesta explícitamente** (p.ej. "tras aprobar, notifica" vía
  `notification_service`) → la hace el router (11/12); `notification_service` es standalone.
- **Throttling de login** (FR-006) → capa de routers (ya lo declara el guión de `auth.py`).
- **Administración de tenants/usuarios/roles** (CU-BE-09: alta de usuarios, gestión de tenants) — **no**
  es uno de los 6 servicios pedidos; `auth_service` solo cubre la parte de `AuthToken`
  (emisión/canje/email-stub) de la invitación, no el alta del usuario en sí.
- **Política real de SLA** (duración por prioridad): `data-model.md §11` la deja explícitamente
  indefinida. `ticket_service` depende de `SlaPolicy.due_at(...)`; los valores reales los fija 18.
- **Scheduler de SLA** (escalado/notificación de vencidos) → tarea 18.
- **Retrieval/RAG** (parte de CU-BE-05 que no es `classify`) → tareas 13/14.
- **`ports/storage.py` y `ports/vector.py`** siguen doc-only: ningún servicio de este plan los consume;
  los materializan las tareas 13/14.

## Recursos externos

- `spec.md`: FR-001..009 (auth), FR-010..015+037 (rbac), FR-016..021 (ticket), FR-023 (classification),
  FR-026..029 (approval), FR-038 (notification); NFR-003 (hexagonal).
- CUs: CU-BE-01 (auth/sesiones), CU-BE-02 (reset/invitación), CU-BE-03 (autorización/aislamiento — 403 vs
  404), CU-BE-04 (ciclo de vida ticket — `reopened` como estado de reposo, RN-1), CU-BE-05 (clasificación,
  parcial), CU-BE-06 (draft IA + HITL — quién emite el `Message`, RN-2 idempotencia), CU-BE-09 (parcial:
  solo invariantes de rol custom).
- `agent-graph.md §6/§7`: contrato del nodo `respond` (emite `Message`) y de `auto_approve` (settings de
  tenant) — confirma la decisión 3; el puerto `ApprovalPolicy` que originalmente justificaba se retiró de
  este plan (`scenario-coverage`: sin consumidor real aquí, ver objetivo 9 y Registro de cambios).
- `api-contract.yaml`: `/approvals/{id}/approve` (200, mensaje emitido — confirma decisión 3), orden por
  defecto de la cola (`sla_due asc, confidence asc`), `TenantSettings.auto_approve`.
- `rbac.md` (catálogo de capacidades, roles semilla, invariantes de rol custom, contrato `authorize`).
- `app/core/security.py` (ya existe: hash/verify Argon2id, JWT create/decode; se añade la primitiva de
  token opaco en la tarea 06 de este plan).
- Guiones ya escritos en `app/domain/{services,ports}/*.py` (docstrings "GUIÓN") — se materializan; los
  números de tarea que citan (de un roadmap anterior) están desactualizados y no vinculan.

## Estimación global

- **Tareas**: 8 (entidades · errors+puertos base · rbac · ticket+SlaPolicy · notification · auth ·
  classification+ChatModel · approval+AgentRunner).
- **Esfuerzo**: nivel unit con mocks (sin Docker) → más rápido por tarea que `database-foundation`;
  ~3-4 sesiones.
- **Recursos**: sin infra externa (no requiere `docker compose up db`).

## Criterios de calidad y verificación

- **TDD**, nivel **unit** con mocks/fakes de puertos (HOW-TO-START-A-TASK.md). Sin integración (no hay DB
  en este plan; la concurrencia real del CAS de `ApprovalRepository` se prueba en integración en 11/12/16).
- Gates por tarea: `ruff`(+S) · `ruff format` · `mypy --strict` · **cosmic-ray** (`break:80`) sobre las
  tareas de servicio (03-08); la de entidades (01) y la de errors+puertos base (02) son declarativas →
  **N/A** documentado (mismo criterio M4 que en `database-foundation`), salvo el test de drift (01), que
  sí es comportamiento real y entra en el gate de esa tarea.
- **Hexagonal**: test de import estático que falla si `app.domain` importa `app.infra`/`sqlalchemy`
  (nota: no cubre `app.core` — tratado aparte como primitivas puras permitidas, decisión explícita).
- **SDD**: servicios trazan a su CU (enlace, no copia de Gherkin); entidades/puertos → Gherkin local "sin
  cambios de spec/CU" (igual que `base.py`/modelos en el plan anterior).
- `/sdd-lint` + `fact-checker` en el cierre de cada tarea (no negociables).

## Tasks

- [x] `backend-domain-services-01` (P1) — Entidades de dominio (identidad + negocio + `Subject`/
  `Resource`/`AuditLogEntry`) + enums propios + test de drift dominio↔ORM · depends_on: —
- [ ] `backend-domain-services-02` (P1) — `errors.py` (jerarquía + taxonomía HTTP-derivable + `PortError`)
  + puertos base: repositorios (incl. `ApprovalRepository.decide_if_pending` CAS, `AuditLogRepository`,
  orden/paginación explícitos) + `clock` + `email` · depends_on: 01
- [ ] `backend-domain-services-03` (P1) — `rbac_service.authorize` (devuelve `Allow|Deny(reason)`,
  capacidad+ámbito, fail-closed, roles custom) · depends_on: 02
- [ ] `backend-domain-services-04` (P1) — `ticket_service` (máquina de estados —`reopen()` deja el ticket
  en `reopened`—, asignación, CSAT, auditoría) + puerto `SlaPolicy` (nace aquí) · depends_on: 02
- [ ] `backend-domain-services-05` (P2) — `notification_service` (emitir/listar/marcar-leída,
  desacoplado) · depends_on: 02
- [ ] `backend-domain-services-06` (P1) — `auth_service` (login, refresh rotación+reuse-detection,
  reset/invitación) + primitiva nueva de token opaco en `app.core.security` · depends_on: 02
- [ ] `backend-domain-services-07` (P2) — `classification` (contrato `dominio: KbDomain | None` +
  `classify()`) + puerto `ChatModel` recortado a `classify` (nace aquí) · depends_on: 02
- [ ] `backend-domain-services-08` (P1) — `approval_service` (cola aislada por tenant, `decide()` compone
  `ApprovalRepository.decide_if_pending` [NotFound/Conflict] + transición a `pending` vía `ticket_service`
  + `AgentRunner.resume`; NO emite Message/toca agent_run; `auto_approve` fuera, es de la tarea 16) +
  puerto `AgentRunner` (nace aquí) · depends_on: 02, 04

## Registro de cambios del plan

- 2026-08-18: creado (draft para grilling). Decisiones tomadas con el owner antes de redactar:
  (D1) entidades de dominio **completas** (Pydantic v2, enums propios, sin reusar `app.infra.db.models.
  enums`) — más trabajo ahora, dominio realmente desacoplado; (D2) `classification`/`approval_service`
  **entran** en el plan pese a depender de piezas no construidas (puerto LLM real=09, grafo/checkpointer=
  15/16): se definen los puertos mínimos y los servicios se prueban con **fakes**. Acotado explícitamente
  fuera: administración de usuarios/tenants (CU-BE-09 salvo invariantes de rol), política real de SLA
  (data-model §11 la deja indefinida), adaptadores concretos de cualquier puerto.
- 2026-08-18: refinado con `grilling` (10 decisiones/avisos): errores por excepción salvo `authorize`
  (devuelve valor, literal `rbac.md §7`); entidades en `entities/{identity,business,enums}.py`; `sla_due`
  vía puerto `SlaPolicy`; `notification_service` desacoplado (criterio: best-effort, no atómico con lo
  que lo dispara); `approval_service.decide()` compone `ticket_service`/`AgentRunner` (FR-027 los trata
  como un solo acto); `classification.dominio: KbDomain | None` (`None` = incierto, sin `confidence`
  inventado); **corrección tras leer CU-BE-04 completo**: `reopen()` deja el ticket en `reopened` (estado
  de reposo real), no auto-encadena a `open`; FR-006 fuera de `auth_service`; doble decisión de
  `approval_service` → `Conflict` (reconcilia `data-model §4.2` "no-op" de estado con FR-028/CU-BE-06
  RN-2 "409" de respuesta).
- 2026-08-18: endurecido con `design-review` (subagente opus). **5 bloqueantes** resueltos: (B1)
  contradicción real entre el guión de `approval_service`, `agent-graph.md §6.3`, CU-BE-06 y
  `api-contract.yaml` sobre quién emite `Message(public)` — resuelto a favor de la evidencia cruzada (lo
  emite el grafo, 16; `approval_service` no lo toca) sobre el guión original del servicio; (B2, decisión
  owner) transición de ticket al aprobar fijada a `pending` (antes "p.ej.", sin fijar); (B3) atomicidad de
  `decide()` movida al contrato del puerto (`decide_if_pending` CAS), no demostrable con fakes a nivel
  servicio; (B4, decisión owner) `auto_approve` vía puerto `ApprovalPolicy` (el ORM `Tenant` no tiene esa
  columna); (B5) añadidas entidades `Subject`/`Resource`/`AuditLogEntry` (exigidas por objetivos 4/5/9 sin
  estar nombradas) y `Deny(reason)` discriminante (403 vs 404, CU-BE-03/FR-011/FR-014). **10 mejoras**
  aplicadas: taxonomía de errores HTTP-derivable + `PortError` (S1); hueco de FR-030 (run nuevo al
  reabrir) declarado sin dueño, sin lógica añadida a `ticket_service` (S2); `ChatModel` recortado a
  `classify` (S3); (S4, decisión owner) `SlaPolicy.due_at(priority, from_, tenant_id)` diseñado con la
  tarea 18 delante; test de drift dominio↔ORM por valor (S5); (S6, decisión owner) `app.core.security`
  tratado como primitivas puras, `secret`/`ttl` como parámetros; primitiva nueva de token opaco
  determinista para `token_hash` (S7 — Argon2 no sirve, su salt aleatorio impide la búsqueda); orden/
  paginación explícitos en las firmas de puerto en vez de "asertado" tautológico con fakes (S8); (S9,
  decisión owner) tareas 01+02 de entidades fusionadas; puertos de política nacen con su consumidor (no
  en una tarea 03 centralizada); `classification` ya no depende de `ticket_service` (solo devuelve
  `Classification`); nota sobre `storage`/`vector` doc-only añadida a Fuera de alcance (S10). Plan
  renumerado de 9 a **8 tareas** tras la fusión 01+02 original.
- 2026-08-18: endurecido con `scenario-coverage` (subagente QA sonnet, 8 dimensiones sobre las 8 tareas +
  el plan como dato). **Autoaplicadas** (sin fork): `RefreshSessionStatus` faltaba en el test de drift
  (bug propio); escenarios de forma de `Subject`/`Resource`/`AuditLogEntry`; rechazo Pydantic ante enum
  inválido; escenario de `details` por defecto y de `PortError` preservando la excepción original; KB
  global sin `tenant_id` en `authorize` (RN-3 de CU-BE-03, sin Gherkin hasta ahora); `Scenario Outline` de
  CSAT (0/1/5/6); reapertura también desde `resolved`; transición separada `reopened→open`; `reopen()`
  recalcula `sla_due`; `count_unread()` en `notification_service` (RN-2 de data-model, capacidad ausente);
  `list_for_user` vacío; `mark_read` valida titularidad y tolera notificación inexistente; refresh
  caducado (no reusado) sin activar reuse-detection; fallo de `ChatModel` envuelto en `PortError` +
  salida malformada propaga validación; `edit()` sin `final_body` → `Validation`; `list_pending` aislada
  por tenant. **4 decisiones del owner**: (1) `decide_if_pending` **distingue** `NotFound` (tarea
  inexistente) de `None`/conflicto (ya decidida) — antes colapsaban; (2) `RefreshSessionRepository.
  rotate_if_active` (CAS) — mismo criterio que `decide_if_pending`, cerraba una asimetría sin justificar
  con `refresh()` (que era check-then-act); (3) fallo tras el CAS de `approval_service.decide()` (p.ej.
  `transition()` falla con la `ApprovalTask` ya `approved`) se **documenta como riesgo conocido**, sin
  compensación (requeriría unit-of-work real de infra, fuera de este plan); (4) **`ApprovalPolicy` se
  retira de la tarea 08**: ningún método de `approval_service` en este plan crea `ApprovalTask`s (lo hace
  el grafo vía `interrupt()`, CU-BE-06) — B4 de design-review identificó el problema (`auto_approve` sin
  columna en `Tenant`) pero no el consumidor real; ahora es un hueco nombrado para la tarea 16. **Huecos
  nombrados sin dueño añadidos** (sin lógica, para que un plan futuro los resuelva): chequeo de
  `tenant.status=disabled`, atribución del actor de auditoría en la transición compuesta, política de
  contraseña, payload por `NotificationType`. Sección (B) del QA (fuera de alcance) confirmó sin sorpresas
  los huecos ya nombrados de FR-030 y CU-BE-09.
