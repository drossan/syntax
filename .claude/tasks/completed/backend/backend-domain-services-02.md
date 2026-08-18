---
id: backend-domain-services-02
package: backend
plan: domain-services
status: done
priority: 1
depends_on: [backend-domain-services-01]
estimate: 2.5h
actual: 0.5h
issue:
created: 2026-08-18
updated: 2026-08-18
---

# errors.py (jerarquía + taxonomía HTTP-derivable) + puertos base (repositorios, clock, email)

## Description

Dos piezas transversales que TODOS los servicios de este plan necesitan: (1) la jerarquía de excepciones
de dominio (todos los servicios señalizan error lanzando, **salvo** `rbac_service.authorize`, que devuelve
valor — decisión de grilling); (2) los puertos (`Protocol`) que no son específicos de un solo servicio:
repositorios por agregado y `clock`/`email`. Los puertos de **política** (`SlaPolicy`, `ChatModel`,
`AgentRunner`) **no** van aquí — nacen en la tarea de su consumidor (decisión de design-review: evita una
tarea de puertos gigante sin llamante que luego churnea; `ApprovalPolicy` se descartó de este plan por
completo, ver `backend-domain-services-08`). Guión: `app/domain/errors.py`, `app/domain/ports/
{repositories,clock,email}.py`.

## Spec

- `app/domain/errors.py`: `DomainError` (base) + bases derivables a HTTP: `NotFound` (404), `Conflict`
  (409), `InvalidTransition` (409/422), `Validation` (422). Cada error concreto lleva un `code: str` slug
  estable (p.ej. `"ticket.invalid_transition"`) + `details: dict[str, object]` — el mapeo HTTP futuro
  (11/12) es una tabla de datos, no un árbol de `isinstance`. Incluye `PortError`/`ExternalServiceError`:
  los adaptadores reales (asyncpg/httpx/openai) lanzarán excepciones de infra a través de los puertos; el
  docstring de cada puerto documenta que el adaptador debe envolverlas en `PortError`.
- `app/domain/ports/repositories.py` (Protocols async, tipos de dominio en las firmas, nunca SQLAlchemy):
  `TenantRepository`, `UserRepository`, `RoleRepository` (+ resolución de capacidades efectivas del
  sujeto), `RefreshSessionRepository` — **`rotate_if_active(token_hash, new_token_hash, now) ->
  RotationOutcome`** (compare-and-set, mismo criterio que `ApprovalRepository`: una sola llamada atómica
  que busca por hash y rota **solo si** la sesión seguía activa; `RotationOutcome` distingue `Rotated
  (session)` / `Reused(family_id)` (encontrada pero no activa → dispara reuse-detection) / `NotFound`
  (ningún hash coincide) — cierra la asimetría con `decide_if_pending` que `scenario-coverage` detectó
  (antes era check-then-act: buscar, comprobar estado, rotar en pasos separados), `AuthTokenRepository`,
  `TicketRepository` (get/list con **orden y paginación explícitos** en la firma — no "el fake ordena
  solo"), `MessageRepository` (list_by_ticket orden `created_at`, add), `ApprovalRepository` (get,
  **`list_pending(tenant_id)` con orden `sla_due,confidence`**, y **`decide_if_pending(task_id, decision,
  ...) -> ApprovalTask | None`** — compare-and-set: **lanza `NotFound`** si `task_id` no existe en
  absoluto; devuelve `None` si existe pero ya no estaba `pending` (distinción añadida por
  `scenario-coverage` — antes ambos casos colapsaban en el mismo `None`, sin forma de que el servicio
  distinguiera 404 de 409); NO `get`+`if`+`update` check-then-act), `AgentRunRepository` (get, add,
  update_status, next_run_seq), `NotificationRepository` (list orden `-created_at`, add, mark_read,
  **count_unread**), `AuditLogRepository` (add).
- `app/domain/ports/clock.py`: `Clock.now() -> datetime` (UTC, timezone-aware).
- `app/domain/ports/email.py`: `EmailPort.send(to, template, context) -> None` (async; Fase 1 = stub en
  infra, fuera de este plan).
- Sin efectos en import.

## Fuera de alcance

- Los puertos de política (`SlaPolicy`, `ChatModel`, `AgentRunner`) → nacen en 04/07/08. `ApprovalPolicy`
  (auto_approve) no forma parte de este plan (hueco nombrado para la tarea 16).
- Adaptadores concretos de cualquier puerto → fuera de este plan.
- `ports/storage.py`/`ports/vector.py`: siguen doc-only, ningún servicio de este plan los consume.

## Scenarios (Gherkin)

<!-- SDD: infra de tipos/contratos → Gherkin LOCAL, "sin cambios de spec/CU". Verificación por mypy
     structural (un fake mínimo satisface cada Protocol) + tests de la jerarquía de errores (unit). -->

```gherkin
Feature: jerarquía de errores de dominio y puertos base

  Scenario: cada excepción de dominio deriva de una base HTTP-mapeable
    Given las excepciones concretas de errors.py
    When se inspecciona su MRO
    Then cada una hereda de NotFound, Conflict, InvalidTransition o Validation

  Scenario: una excepción de dominio lleva code y details
    Given una instancia de una excepción de dominio concreta
    When se inspecciona
    Then expone un code (slug estable) y un dict de details

  Scenario: PortError existe para envolver fallos de infra
    Given el módulo errors.py
    When se inspecciona
    Then existe PortError (o ExternalServiceError) como excepción de dominio

  Scenario: una excepción de dominio sin details explícito usa un dict vacío por defecto
    Given una excepción de dominio construida sin pasar details
    When se inspecciona su atributo details
    Then es un dict vacío, nunca None

  Scenario: PortError preserva la excepción original
    Given una excepción de infra capturada (p.ej. un TimeoutError simulado)
    When se envuelve en PortError
    Then PortError.__cause__ es la excepción original

  Scenario Outline: cada puerto tiene un fake mínimo que lo satisface
    Given un fake que implementa <puerto>
    When se comprueba conformidad estructural (mypy / isinstance runtime_checkable)
    Then el fake satisface el Protocol

    Examples:
      | puerto                  |
      | TenantRepository        |
      | UserRepository          |
      | RoleRepository          |
      | RefreshSessionRepository|
      | AuthTokenRepository     |
      | TicketRepository        |
      | MessageRepository       |
      | ApprovalRepository      |
      | AgentRunRepository      |
      | NotificationRepository  |
      | AuditLogRepository      |
      | Clock                  |
      | EmailPort               |

  Scenario: ApprovalRepository.decide_if_pending distingue tarea inexistente de ya-decidida
    Given un fake de ApprovalRepository sin ninguna tarea con ese id
    When se llama a decide_if_pending sobre un task_id inexistente
    Then lanza NotFound (no devuelve None ni muta nada)

  Scenario: ApprovalRepository.decide_if_pending es compare-and-set para una tarea ya decidida
    Given un fake de ApprovalRepository con una tarea existente pero ya no-pending
    When se llama a decide_if_pending sobre esa tarea
    Then devuelve None (no lanza, no muta), señal de que el servicio debe tratarlo como conflicto

  Scenario Outline: RefreshSessionRepository.rotate_if_active distingue los tres resultados
    Given un fake de RefreshSessionRepository con una sesión en estado <estado_previo>
    When se llama a rotate_if_active con su token_hash
    Then el resultado es <resultado>

    Examples:
      | estado_previo      | resultado                         |
      | active             | Rotated(nueva sesión)              |
      | rotated            | Reused(family_id de la sesión)     |
      | inexistente        | NotFound                           |
```

## Provides

`app.domain.errors` (jerarquía) y `app.domain.ports.{repositories,clock,email}` (Protocols + fakes de
referencia) que consumen los 6 servicios (03-08).

## Definition of Done

- [ ] Tests escritos ANTES de la implementación (Red → Green → Refactor).
- [ ] Cada escenario Gherkin tiene al menos un test (jerarquía de errores, code/details con default vacío,
  PortError incl. `__cause__`, fakes por puerto, CAS de ApprovalRepository con NotFound vs None,
  RotationOutcome de RefreshSessionRepository).
- [ ] Todos los tests en verde (`make test`).
- [ ] `Provides` disponible; sin efectos en import.
- [ ] `ruff check` (+`S`) + `ruff format --check` + `mypy` strict OK.
- [ ] Gate de mutation: puertos **declarativos** → N/A (M4); `errors.py` (jerarquía + `code`/`details`) es
  comportamiento mínimo, mutation aplica (`break: 80`) si el gate lo detecta con superficie suficiente.
- [ ] Gate `/sdd-lint` sin ERROR (SDD: sin cambios de spec/CU — infra de contratos).
- [ ] Gate de `fact-checker`.
- [ ] Documentación: docstrings de cada excepción/puerto (intención, cuándo se lanza/qué envuelve); session
  log.
