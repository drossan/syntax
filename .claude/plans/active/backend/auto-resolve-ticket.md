---
id: backend-auto-resolve-ticket
package: backend
status: active
branch: plan/backend/auto-resolve-ticket
issue:
created: 2026-08-31
updated: 2026-08-31
---

# Auto-respuesta IA: publicar → `resolved`

## Contexto y problema

El grafo del agente ya publica la respuesta automáticamente cuando la confianza es suficiente
(`tenant.auto_approve=true` y `confidence >= AGENT_CONFIDENCE_THRESHOLD`):
`app/agents/nodes/respond.py:26-28` llama a `_publish()` directo cuando
`state["requires_approval"]` es `False`. Eso ya funciona, no se construye desde cero.

Lo que falta: `respond.py` publica el `Message` pero **nunca toca `ticket.status`** — el ticket se
queda en el estado que tuviera (típicamente `new`, si `ai_auto_draft` disparó el agente justo al
crearlo). Nada distingue hoy "ya respondido por IA" de "recién creado, sin tocar". El owner decidió
que el estado destino sea **`resolved`** (no un estado nuevo), reutilizando el mecanismo de
`reopen()` que ya existe para que el cliente pueda decir "esta respuesta no vale".

**Hallazgo que fija el diseño**: `_VALID_TRANSITIONS` (`app/domain/services/ticket_service.py:24-34`)
no tiene la arista `(new, resolved)` ni `(open, resolved)` — solo `(pending, resolved)`. Saltar
directo desde `respond.py` reventaría con `InvalidTransition`. Existe ya el precedente exacto:
`approval_service.py:120-129` (documentado en `.claude/specs/backend/casos-de-uso/CU-BE-06-draft-ia-y-aprobacion-hitl.md:40-43`)
encadena `new/reopened → open → pending` antes de reanudar el grafo en el camino HITL aprobado. El
camino auto necesita el mismo encadenado, un salto más: `→ open → pending → resolved` — las tres
aristas ya son válidas, así que **no hace falta tocar `_VALID_TRANSITIONS`**.

Segunda pieza, RBAC: `client_agent` (rol que normalmente abre tickets, `app/infra/db/seed.py:98`)
**no** tiene `ticket.transition` — solo `client_admin` (confirmado en `.claude/specs/backend/rbac.md:62`
y su matriz, línea 71, con ❌ explícito). Sin esta capacidad, un cliente normal no puede llamar a
`reopen()` sobre su propio ticket aunque el mecanismo exista.

**Ajustado en `design-review` (2026-08-31)**: dar la capacidad `ticket.transition` COMPLETA a
`client_agent` habilita más de lo que pide el objetivo — `pending→resolved` (el cliente se
auto-resuelve, saltándose la revisión del agente) y `resolved→closed` (cierre unilateral, hoy
reservado a soporte/admin). Además, `client_agent` es un rol de sistema **inmutable**
(`.claude/specs/backend/rbac.md §4`: "no se editan/borran; se clonan a un custom si hace falta
variar") — la capacidad, una vez dada, **no** es revocable puntualmente sin clonar el rol y
reasignar usuarios; el owner, informado de esto, decidió una capacidad nueva y estrecha en su
lugar: **`ticket.reopen`**, acotada por el servicio a solo `{resolved,closed}→reopened`.

Como hoy no existe un endpoint dedicado a `reopen()` (`TicketService.reopen()` ya existe en
dominio, pero `POST /{id}/transition` es genérico y acepta cualquier destino válido de
`_VALID_TRANSITIONS`), esta capacidad necesita su propio endpoint —p.ej. `POST /{id}/reopen`—
gateado por `ticket.reopen`, que llame a `TicketService.reopen()` directamente (mismo patrón que
`POST /{id}/assign`, endpoint dedicado con su propia capacidad).

## Objetivos

1. **La auto-respuesta deja el ticket en `resolved`**, encadenando transiciones válidas existentes.
   - *Criterio de éxito*: un ticket `new` con `auto_approve=true` y confianza alta, tras disparar el
     agente, queda en `status=resolved` con el mensaje publicado — verificado con test de
     integración real (Postgres) y con una verificación manual contra el backend real.
2. **`client_agent` puede reabrir un ticket `resolved`/`closed`** (objetar la auto-respuesta) — y
   **solo eso**: sin `pending→resolved` ni `resolved→closed` para ese rol.
   - *Criterio de éxito*: un sujeto `client_agent` sobre un ticket de su propio tenant `resolved`
     → `reopened` vía el endpoint dedicado, sin 403; el mismo sujeto contra cualquier otro destino
     (p.ej. `pending→resolved`) sigue dando 403 (sin `ticket.transition`).

## Alcance y fuera de alcance

- Inyectar `TicketService` en `make_respond_node()` (`app/agents/nodes/respond.py`) y threadearlo
  por `app/agents/graph.py::build_graph()` → `app/agents/runner.py::LangGraphAgentRunner.__init__()`
  hasta el punto de ensamblado real (`app/core/deps.py` — confirmar el wiring exacto al arrancar la
  tarea, no asumido aquí).
- **Extraer el encadenado a un método único compartido** (ajuste de `design-review`, 2026-08-31):
  `TicketService.advance_to(ticket_id, target)` (nombre orientativo) que recorra `_VALID_TRANSITIONS`
  desde el estado actual hasta `target`, generalizando el `_NEEDS_OPEN_BEFORE_PENDING` de
  `approval_service.py` en vez de duplicar la lógica de "cómo llegar hasta ahí" en dos sitios.
  `approval_service.decide()` pasa a usarlo (destino `pending`, mismo comportamiento observable,
  sin tests de esa parte rotos) y el nuevo código de `respond.py` lo usa con destino `resolved`.
- En el camino auto (`not requires_approval`), encadenar la transición **antes** de publicar el
  `Message` (mismo orden que `approval_service.decide()`: transiciona, luego dispara el efecto
  público) — si un salto intermedio falla, no se publica ningún mensaje sobre un ticket en estado a
  medias. Cada salto genera su entrada normal de audit log (`ticket.transitioned`), sin marca
  especial — mismo criterio que el precedente, decisión de `grilling` (2026-08-31).
- **`actor_id` en el audit log** (ajuste de `design-review`, 2026-08-31): `TicketService._audit()`
  nunca popula `actor_id` hoy (campo existente, `business.py`, default `None`) — inocuo mientras
  solo roles de confianza transicionan tickets, pero deja de serlo en cuanto `client_agent` (rol más
  numeroso) y el camino auto pueden transicionar también: sin `actor_id`, cliente/soporte/IA quedan
  indistinguibles en el único registro de auditoría. Poblar `actor_id` en las transiciones del
  camino auto explícitamente como "sistema" (valor a definir en la tarea — p.ej. un sentinel o
  `None` documentado como "sin actor humano", distinto de un `Subject` real) y exigir lo mismo en el
  nuevo endpoint de `reopen()` (pasar el `Subject` real del `client_agent`/`client_admin` que decide).
- **Asimetría documentada, no resuelta** (ajuste de `design-review`, 2026-08-31): el camino HITL
  (revisado por un humano) se detiene en `pending` (`approval_service.decide()`); este plan hace que
  el camino auto (nadie lo revisó) llegue un salto más allá, a `resolved` — la respuesta MENOS
  escrutada queda MÁS "cerrada" que la más escrutada. Es una consecuencia de la decisión ya cerrada
  con el owner (estado destino = `resolved`), no se reabre aquí; se deja nombrada para que quien
  audite el diseño más adelante no la lea como un descuido.
- **Caso borde confirmado en `grilling` (2026-08-31)**: si el ticket YA está en `resolved`/`closed`
  cuando el camino auto publica (p.ej. un `agent.trigger` manual posterior), **no se toca el
  estado** — se publica el mensaje igual, sin intentar ninguna transición.
- Nueva capacidad **`ticket.reopen`** (ajuste de `design-review`, 2026-08-31 — sustituye la capacidad
  completa `ticket.transition` que se había fijado en `grilling`): capacidad nueva en el catálogo
  (`app/infra/db/seed.py` `CAPABILITIES`), acotada por el servicio a `{resolved,closed}→reopened`
  únicamente, expuesta vía un endpoint dedicado (`POST /{id}/reopen`, mismo patrón que
  `POST /{id}/assign`) que llama a `TicketService.reopen()` directo — no vía el genérico
  `POST /{id}/transition`. Añadida a `client_agent` en `seed.py:98` y documentada en
  `.claude/specs/backend/rbac.md` (prosa + matriz).
- Actualizar el docstring de `app/agents/nodes/__init__.py` (ajuste de `design-review`, 2026-08-31):
  documentar `respond` como la excepción a "los nodos solo reciben puertos" — recibe `TicketService`
  (un servicio de dominio) porque el orden transición-antes-de-publicar (decisión de `grilling`)
  exige que la mutación ocurra en el mismo nodo que `_publish()`.
- Threading de `TicketService` confirmado sin ambigüedad (no era una decisión, un hecho a verificar):
  `app/core/deps.py::_get_agent_runner()` ya construye `LangGraphAgentRunner` con la misma `session`
  que `get_ticket_service(session)` usa en `get_approval_service()` — basta con pasar
  `ticket_service=get_ticket_service(session)` ahí. Único otro constructor de `LangGraphAgentRunner`:
  `tests/test_runner.py` (a actualizar, mecánico).
- Tests de integración reales (Postgres/RLS — footgun conocido `SET app.tenant_id` en pool async)
  sobre el camino auto completo, sobre `advance_to()` (incl. que `approval_service.py` sigue
  funcionando igual), y sobre el RBAC de `ticket.reopen` (incluye el caso negativo: `client_agent`
  sin `ticket.transition` sigue en 403 contra cualquier otro destino).

### Fuera de alcance
- Cualquier estado nuevo distinto de `resolved` (decisión ya cerrada con el owner).
- Dar `ticket.transition` (la capacidad completa) a `client_agent` — sustituida por `ticket.reopen`,
  acotada.
- Cambiar el comportamiento observable de `approval_service.decide()` — se refactoriza a usar
  `advance_to()`, pero el resultado (encadena hasta `pending`) es idéntico; sus tests existentes no
  deben cambiar de expectativa.
- Poblar `actor_id` retroactivamente en transiciones ya existentes fuera de esta tarea (solo se
  popula en el código nuevo/tocado).
- El refresco en vivo del hilo de mensajes en frontend — va en el plan
  `frontend/ticket-thread-live-refresh` (paralelo, sin dependencia dura entre ambos).

## Recursos externos

- `.claude/specs/backend/agent-graph.md` — spec del grafo (no cubre hoy el punto "auto-respuesta →
  resolved"; esta tarea es la que lo documenta).
- `.claude/specs/backend/casos-de-uso/CU-BE-06-draft-ia-y-aprobacion-hitl.md` — precedente del
  encadenado de transiciones (líneas 40-43) y contrato del camino auto/HITL.
- `.claude/specs/backend/rbac.md` — fuente de verdad de capacidades por rol.
- `app/domain/services/approval_service.py:120-129` — código real del patrón a replicar.

## Estimación global

- **Tareas totales**: 3 (ver lista al final; creció de 2 a 3 en `design-review` al extraer
  `advance_to()` como pieza propia).
- **Esfuerzo estimado**: 2-3 sesiones.
- **Recursos**: sin accesos nuevos; backend real ya corre local (Postgres+pgvector vía
  `docker compose`, verificado en esta sesión — el `HOW-TO-START-A-TASK.md` del package describe una
  precondición de "backend no ejecuta" que está **desactualizada**, confirmado corriéndolo en vivo).

## Criterios de calidad y verificación

- TDD en todas las capas (dominio con fakes; integración real contra Postgres para RLS/estado).
- `make lint` (ruff) y `make typecheck` (mypy strict) en verde tras cada tarea.
- Gate de mutation testing (`cosmic-ray`, `break: 80`, `make mutation`) por tarea.
- Verificación manual contra el backend real: crear ticket con `auto_approve=true`, confirmar que
  queda `resolved` solo, y que `client_agent` puede reabrirlo.

## Tasks

- [x] `backend-auto-resolve-ticket-01` (P1) — Extraer `TicketService.advance_to()` y migrar `approval_service.decide()`  · depends_on: —
- [ ] `backend-auto-resolve-ticket-02` (P2) — Encadenar el camino auto a `resolved` en `respond.py` (usa `advance_to()`)  · depends_on: backend-auto-resolve-ticket-01
- [ ] `backend-auto-resolve-ticket-03` (P2) — RBAC: nueva capacidad `ticket.reopen` + endpoint dedicado  · depends_on: —

## Registro de cambios del plan

- 2026-08-31: creado, a partir de un plan combinado (harness plan mode) aprobado por el owner tras
  fijar dos decisiones de diseño: estado destino `resolved` (reutilizando `reopen()`) y RBAC de
  `client_agent`. Hallazgo de la sesión de planificación: `_VALID_TRANSITIONS` no necesita cambios,
  el patrón de encadenado ya existe en `approval_service.py` — evita una tercera decisión de diseño
  (estado nuevo) que el owner ya había descartado.
- 2026-08-31: refinado con `grilling` (4 preguntas, 4 decisiones): (1) ticket ya `resolved`/`closed`
  al auto-responder → publicar sin tocar estado; (2) orden transición-luego-publicación; (3) audit
  log sin marca especial (3 entradas normales); (4) `ticket.transition` para `client_agent` — **esta
  decisión se corrigió después en `design-review`, ver abajo**.
- 2026-08-31: revisado con `design-review` (subagente adversario, 5 hallazgos, model routing caído a
  inherit — `models.design-review: claude-opus-4-8` no es un alias válido para la tool de agentes).
  Cambios aplicados, decididos con el owner:
  1. **RBAC corregido** (revierte la decisión de `grilling`): `ticket.transition` completo para
     `client_agent` no era revocable (rol de sistema inmutable, `rbac.md §4`) y abría más superficie
     de la pedida (auto-resolver, cerrar unilateral). Sustituido por `ticket.reopen`, capacidad
     nueva y estrecha, acotada por el servicio a `{resolved,closed}→reopened`, con endpoint
     dedicado.
  2. `actor_id` se puebla en las transiciones nuevas (antes nunca se poblaba) — sin esto, cliente/
     soporte/IA quedarían indistinguibles en el audit log en cuanto ambos caminos nuevos pueden
     transicionar tickets.
  3. Asimetría auto-vs-HITL (`resolved` vs `pending`) documentada explícitamente, no resuelta —
     consecuencia nombrada de una decisión ya cerrada.
  4. Encadenado extraído a `TicketService.advance_to()` compartido con `approval_service.py`, en vez
     de duplicar la lógica de recorrido de `_VALID_TRANSITIONS` en dos sitios — nueva tarea `01`.
  5. Docstring de `nodes/__init__.py` se actualiza para documentar `respond` como la excepción a
     "los nodos solo reciben puertos".
- 2026-08-31: revisado con `scenario-coverage` (subagente QA, 11 hallazgos en alcance + 4 fuera de
  alcance contrastados). Decisiones aplicadas, con el owner:
  1. Semánticas de `advance_to()` fijadas (antes ambiguas): origen==destino → no-op (no
     `InvalidTransition`, necesario para no romper `approval_service.decide()` ante una segunda
     decisión); recorrido con visitados (evita colgarse en los ciclos reales de
     `_VALID_TRANSITIONS`); fallo a mitad → sin rollback, el ticket queda en el último estado
     alcanzado con éxito.
  2. **`actor_id` sin mecanismo — bloqueante, corregido**: `_audit()`/`transition()`/`reopen()` no
     aceptaban `actor_id` como parámetro; sin cambiar esas firmas, el requisito 2 de la pasada
     anterior de `design-review` no era implementable. La tarea `01` añade el parámetro (opcional,
     default `None`, sin romper llamantes existentes) a las cuatro firmas; la tarea `03` pasa a
     depender de la `01` (antes `depends_on: []`) para evitar que ambas tocaran la misma firma por
     separado.
  3. 4 escenarios nuevos de `reopen()` en la tarea `03`: origen `closed` (no solo `resolved`), 409
     (capacidad presente, estado inválido — distinto del 403 ya cubierto), aislamiento cross-tenant
     (404) y `ticket_id` inexistente (404).
  4. 3 riesgos nombrados (mensaje duplicado si crashea entre transicionar y publicar; sin notificar
     a soporte al reabrir; carrera sin lock entre el camino auto y un `reopen()` simultáneo) — **se
     dejan documentados y sin mitigar en esta pasada**, mismo criterio que el riesgo ya aceptado sin
     unit-of-work cross-repo en `approval_service.py`.
  5. Confirmado sin hallazgo nuevo: la asimetría auto-vs-HITL y el hueco de FR-030 (run nuevo al
     reabrir) ya estaban completamente documentados; ningún cambio adicional.
