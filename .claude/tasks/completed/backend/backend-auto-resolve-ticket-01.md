---
id: backend-auto-resolve-ticket-01
package: backend
plan: auto-resolve-ticket
status: done
priority: 1
depends_on: []
estimate: 3h
actual: 3h
issue:
created: 2026-08-31
updated: 2026-08-31
---

# Extraer `TicketService.advance_to()` y migrar `approval_service.decide()`

## Description

Hoy `approval_service.decide()` (`app/domain/services/approval_service.py:120-129`) recorre a mano
`_NEEDS_OPEN_BEFORE_PENDING` para encadenar `new/reopened→open→pending` antes de reanudar el grafo.
La tarea `02` de este plan necesita el mismo tipo de recorrido, pero hasta `resolved` — sin este
refactor, la lógica de "cómo llegar hasta un destino válido" quedaría duplicada en dos sitios que
alguien tendría que sincronizar a mano si cambia `_VALID_TRANSITIONS` (hallazgo de `design-review`,
plan `.claude/plans/pending/backend/auto-resolve-ticket.md`, Registro de cambios 2026-08-31, punto 4).

Extrae un método único en `TicketService` que recorra `_VALID_TRANSITIONS` desde el estado actual del
ticket hasta un destino dado, y migra `approval_service.decide()` a usarlo. El comportamiento
observable de `approval_service.decide()` **no cambia** — es un refactor puro; sus tests existentes
deben seguir en verde sin modificar sus expectativas.

## Spec

- Nuevo método en `TicketService` (`app/domain/services/ticket_service.py`), p.ej.
  `advance_to(ticket_id: uuid.UUID, target: TicketStatus, actor_id: uuid.UUID | None = None) -> Ticket`:
  recorre `_VALID_TRANSITIONS` desde `ticket.status` hasta `target`, llamando a `self.transition()`
  en cada salto (reutiliza su audit log existente, sin marca especial). **Semánticas fijadas en
  `scenario-coverage` (2026-08-31, decisión del owner)**:
  - **Origen == destino → no-op**: si `ticket.status` ya es `target`, no transiciona nada y
    devuelve el ticket tal cual (NO propaga `InvalidTransition`). Necesario para que
    `approval_service.decide()` no cambie de comportamiento si una segunda decisión llega con el
    ticket ya en `pending`.
  - **Recorrido con visitados**: el algoritmo que busca el camino hasta `target` marca estados
    visitados y nunca re-entra en uno ya visitado — `_VALID_TRANSITIONS` tiene ciclos reales
    (`open→pending→resolved→reopened→open`; `resolved→closed→reopened→open→pending→resolved`); sin
    marcar visitados, una búsqueda hacia un destino inalcanzable (p.ej. `new`, sin aristas de
    entrada) puede no terminar. Si no hay camino, propaga `InvalidTransition` en tiempo acotado.
  - **Fallo a mitad de camino → sin rollback**: si un salto intermedio falla, el ticket queda en el
    **último estado alcanzado con éxito** (no revierte al origen, no llega a `target`) — mismo
    criterio de "sin unit-of-work cross-repo" ya aceptado y documentado en `approval_service.py`.
  - **`actor_id` opcional** (nuevo parámetro, default `None`): se pasa a cada `self.transition()`
    encadenado. Ver el punto siguiente — es la pieza que hace implementable el requisito de
    `design-review` de poblar `actor_id` en el código nuevo (tareas `02`/`03`).
- **`actor_id` en el audit log (hallazgo bloqueante de `scenario-coverage`, 2026-08-31)**:
  `TicketService._audit()` no acepta `actor_id` hoy (siempre `None` implícito) y ni `transition()`
  ni `reopen()` lo reciben como parámetro — sin este cambio de firma, es imposible que el `Subject`
  real llegue al audit log en la tarea `03`, y "actor_id=None explícito" en la tarea `02` es
  indistinguible de "no hacer nada". Esta tarea añade `actor_id: uuid.UUID | None = None` a
  `_audit()`, `transition()`, `reopen()` y `advance_to()` (todos opcionales, default `None` —
  **no** rompe ningún llamante existente, incl. los routers que hoy no lo pasan). `AuditLogEntry`
  ya tiene el campo (`business.py:141`), solo falta que los métodos de servicio lo acepten y lo
  propaguen.
- `approval_service.decide()` sustituye su bloque `if ticket.status in _NEEDS_OPEN_BEFORE_PENDING: ...`
  + `await self._ticket_service.transition(updated.ticket_id, TicketStatus.pending)` por una sola
  llamada a `advance_to(updated.ticket_id, TicketStatus.pending)`.
- No se cambia la firma pública de `ApprovalService.decide()` ni ningún contrato HTTP.

## Fuera de alcance

- El camino auto de `respond.py` (tarea `02`).
- La nueva capacidad `ticket.reopen` (tarea `03`) — pero **esta tarea sí prepara la firma** que la
  `03` necesita (`actor_id` en `reopen()`); `03` pasa a depender de esta tarea (ver frontmatter).
- Cualquier cambio de comportamiento observable en `approval_service.decide()` — mismos tests, mismo
  resultado (`approval_service.decide()` no pasa `actor_id` explícito; sigue quedando `None`, sin
  cambio observable).
- Poblar `actor_id` en transiciones ya existentes fuera del código tocado por este plan.

## Scenarios (Gherkin)

Criterios de aceptación (Gherkin) en el caso de uso:
- [CU-BE-06 — Draft IA y aprobación HITL](../../../specs/backend/casos-de-uso/CU-BE-06-draft-ia-y-aprobacion-hitl.md)
  (escenario "Aprobación emite la respuesta al cliente" y los demás del camino HITL — deben seguir
  pasando sin cambios tras el refactor; no añade escenarios propios, es un refactor interno sin
  comportamiento nuevo).

Cobertura adicional específica de este refactor (no en el CU, porque `advance_to()` es un detalle de
implementación interno, no comportamiento observable del caso de uso):
- Test unitario de `TicketService.advance_to()` con fakes: desde cada estado de origen posible
  (`new`, `reopened`, `open`, `pending`) hasta cada destino alcanzable, verificando la secuencia de
  saltos y el audit log de cada uno.
- Test unitario: `advance_to()` hacia un destino sin camino válido desde el estado actual propaga
  `InvalidTransition` (verificar tiempo acotado, no solo la excepción — usar un destino que requiera
  recorrer al menos un ciclo antes de descartarse, no un caso trivial de 1 paso).
- Test unitario: `advance_to(ticket_id, target)` con `ticket.status == target` es no-op — no llama a
  `transition()` ninguna vez, no genera audit log, devuelve el ticket sin cambios.
- Test unitario: `advance_to()` con un fallo inyectado en un salto intermedio deja el ticket en el
  último estado alcanzado con éxito (no en el origen, no en `target`), con audit log solo hasta ese
  punto.
- Test unitario: `advance_to(ticket_id, target, actor_id=<uuid>)` propaga ese `actor_id` a cada
  `transition()`/`_audit()` encadenado.

## Provides

- `TicketService.advance_to(ticket_id, target, actor_id=None)` — método de dominio reutilizable por
  cualquier llamante que necesite alcanzar un estado válido encadenando transiciones, sin
  reimplementar el recorrido de `_VALID_TRANSITIONS`. La tarea `02` lo consume con destino
  `resolved`.
- `TicketService.transition()`/`.reopen()`/`._audit()` aceptan `actor_id: uuid.UUID | None = None`
  — la tarea `03` lo consume en `reopen()` para registrar el `Subject` real que decide.

## Definition of Done

- [x] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [x] Cada escenario Gherkin tiene al menos un test (camino feliz + bordes/errores)
- [x] Todos los tests en verde (incl. los existentes de `approval_service.py`, sin modificar sus
      expectativas) — `65 passed` (`test_ticket_service.py` + `test_approval_service.py`)
- [x] Spec cumplida; `advance_to()` queda realmente disponible y usado por `approval_service.decide()`
- [x] Lint / format / typecheck OK — `ruff check`/`ruff format --check`/`mypy` limpios en los 3 ficheros tocados
- [x] Gate de mutation testing superado con `cosmic-ray` — 94.46% kill rate (307/325), por encima de
      `break: 80`. 18 survivors documentados: 12 son mutaciones del operador `|` en anotaciones de tipo
      (aparecen también en métodos no tocados por esta tarea — artefacto del mutador, no hueco real);
      6 en `_shortest_path` son mutantes equivalentes (`is`/`is not` sobre singletons de `Enum`,
      semánticamente idénticos a `==`/`!=`; `continue`→`break` es equivalente para los únicos targets
      reales que usa el código hoy, `pending`/`resolved`, nunca `closed`)
- [x] Gate `sdd-lint` superado — 0 ERROR, 2 AVISO (ambos corregidos): FR-057 dividido en FR-057
      (event-driven) + FR-059 (unwanted-behavior, antes mezclados en un solo FR); el escenario de
      reapertura inválida convertido a `Scenario Outline` con `Examples` (antes 4 estados en prosa)
- [x] Gate de `fact-checker` superado — 10/10 afirmaciones verificadas correctas (una marcada
      "INCORRECTO" porque el fix del `Scenario Outline` se aplicó mientras el subagente corría —
      confirma que el estado final es el correcto, no una afirmación falsa)
- [x] Documentación actualizada:
  - [x] TSDoc/docstrings en `advance_to()`, `_shortest_path()`, y el bloque migrado de
        `approval_service.decide()`
  - [x] Doc técnica: CU-BE-06 y `spec.md` (FR-057/058/059) ya actualizados en la sesión de planificación
        (grilling/design-review/scenario-coverage); 2 AVISOS de `sdd-lint` corregidos en esta tarea
  - [x] Histórico de la tarea — session log en `.claude/context/backend/backend-auto-resolve-ticket-01.md`
- [x] Docs de dev / usuario final + `pnpm changeset` donde aplique (N/A — backend no usa changesets)
