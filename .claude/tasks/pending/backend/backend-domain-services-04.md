---
id: backend-domain-services-04
package: backend
plan: domain-services
status: pending
priority: 1
depends_on: [backend-domain-services-02]
estimate: 3h
actual:
issue:
created: 2026-08-18
updated: 2026-08-18
---

# ticket_service (máquina de estados, asignación, CSAT, auditoría) + puerto SlaPolicy

## Description

Ciclo de vida del ticket: alta, máquina de estados, asignación, CSAT, auditoría de cada mutación. Nace
aquí el puerto **`SlaPolicy`** (design-review: los puertos de política nacen con su primer consumidor
real, no en una tarea de puertos centralizada) — diseñado ya pensando en que la tarea 18 (scheduler)
necesitará la misma política para el escalado, aunque los valores reales (horas/días por prioridad) no se
fijan aquí (`data-model.md §11` los deja explícitamente indefinidos). Guión: `app/domain/services/
ticket_service.py`, `app/domain/ports/sla_policy.py` (nuevo). Spec: FR-016/017/018/020/021, CU-BE-04.

## Spec

- `SlaPolicy.due_at(priority: TicketPriority, from_: datetime, tenant_id: UUID) -> datetime | None`
  (Protocol, nuevo módulo `ports/sla_policy.py`). El fake de test devuelve una fecha fija/determinista
  (puerto `Clock` inyectado, sin reloj real).
- `create(tenant_id, requester, subject, body) -> Ticket`: estado inicial `new`; el primer mensaje del
  solicitante es `Message(visibility=public)`; `sla_due = sla_policy.due_at(priority_default, clock.now(),
  tenant_id)`. Auditar la creación.
- **Máquina de estados** (`ticket_status`: `new→open→pending→resolved→closed→reopened`, RN-1 de CU-BE-04):
  `transition(ticket, new_status)` valida la transición contra la tabla de aristas exacta: `new→open`,
  `open→pending`, `pending→resolved`, `resolved→closed`, `resolved→reopened`, `closed→reopened`,
  `reopened→open`. Inválida (incl. **transicionar al mismo estado**, p.ej. `open→open` — no es una arista
  de la tabla, se trata como cualquier otra transición no listada) → `InvalidTransition` (nunca muta,
  nunca una excepción cruda). `reopen()`: `resolved`/`closed` → deja el ticket en **`reopened`** (estado
  de reposo real, Gherkin literal de CU-BE-04 — **no** auto-encadena a `open`) y **recalcula `sla_due`**
  vía `SlaPolicy` (coherente con "al crear/reabrir"); una transición posterior y separada `reopened →
  open` (vía `transition()`, no un método especial) lo retoma sin recalcular `sla_due` de nuevo.
- `assign(ticket, assignee_id | None)`: set/clear, auditado. Si `assignee_id` no pertenece al mismo
  `tenant_id` del ticket → rechaza (`Validation`) — la comparación usa el `tenant_id` que ya trae el
  `Ticket`/el `assignee_id` resuelto por el llamante (no consulta `UserRepository` desde aquí).
- `set_csat(ticket, value: int)`: `1..5` — fuera de rango (`0`, `6`, negativos) → `Validation`; auditado.
  (El CHECK de la migración, 06/`database-foundation`, es la defensa en profundidad en DB; esta validación
  de dominio es la primera línea.)
- Toda mutación (creación, transición, asignación, CSAT) escribe un `AuditLogEntry` vía
  `AuditLogRepository`.
- Operar sobre un `ticket_id` que el repo no encuentra → `NotFound` (nunca una excepción cruda del repo).
- **Fuera de alcance nombrado** (FR-030): quién lanza el `agent_run` nuevo al reabrir y qué pasa con el
  `agent_run`/`approval_task` huérfanos del run anterior — no se le añade lógica a este servicio sin spec
  que lo respalde; lo decide el plan que construya esa orquestación (12/15/16).
- Sin efectos en import; puertos por inyección (`TicketRepository`, `MessageRepository`,
  `AuditLogRepository`, `SlaPolicy`, `Clock`).

## Fuera de alcance

- Quién lanza el `agent_run` nuevo al reabrir (FR-030) y la limpieza del `agent_run`/`approval_task`
  huérfanos → 12/15/16 (hueco nombrado, sin dueño todavía).
- La política real de SLA (horas/días) → tarea 18.
- Notificar tras asignar/responder (`notification_service`) → orquestación del router (11/12), servicio
  desacoplado en este plan.
- Repos concretos → fuera de este plan.

## Scenarios (Gherkin)

Criterios de aceptación (Gherkin) en el caso de uso:
- [CU-BE-04 — Ciclo de vida del ticket](../../../specs/backend/casos-de-uso/CU-BE-04-ciclo-de-vida-del-ticket.md)

> Nota de alcance: el CU cubre alta/respuesta/nota interna/transición inválida/reapertura/auditoría a
> nivel de flujo completo. Esta tarea prueba `ticket_service` con `TicketRepository`/`MessageRepository`/
> `AuditLogRepository`/`SlaPolicy` **mockeados** (unit): "Alta de un ticket", "Transición inválida se
> rechaza", "Reapertura de un ticket cerrado" (`reopened`, no `open` — confirmado tras leer el CU
> completo), "Toda mutación queda auditada". "Respuesta pública" y "Nota interna oculta" son parcialmente
> de este servicio (creación del `Message`) y parcialmente de visibilidad/serialización (fuera de
> alcance, capa de routers). Añade, sobre el CU: asignación (`assign`) y CSAT, que el CU no Gherkin-iza
> explícitamente pero exige FR-016/020. Añadido por `scenario-coverage`:
> ```gherkin
> Scenario Outline: csat fuera de rango se rechaza
>   Given un ticket resuelto
>   When se fija csat a <valor>
>   Then <resultado>
>
>   Examples:
>     | valor | resultado   |
>     | 0     | Validation  |
>     | 1     | aceptado    |
>     | 5     | aceptado    |
>     | 6     | Validation  |
>
> Scenario: reapertura también desde resolved (no solo closed)
>   Given un ticket en estado "resolved"
>   When el cliente lo reabre
>   Then el ticket pasa a "reopened" (misma regla que desde "closed")
>
> Scenario: la transición reopened a open es independiente y posterior
>   Given un ticket en estado "reopened"
>   When se transiciona explícitamente a "open"
>   Then la transición se acepta (arista reopened→open de la máquina)
>
> Scenario: asignar a un usuario de otro tenant se rechaza
>   Given un ticket del tenant A
>   When se asigna a un assignee_id que pertenece al tenant B
>   Then la asignación se rechaza (Validation), el ticket no cambia
> ```

## Provides

`ticket_service` (crear/transicionar/reabrir/asignar/CSAT/auditar) en `app.domain.services.ticket_service`
y el puerto `SlaPolicy` en `app.domain.ports.sla_policy`, consumidos por `approval_service`
(`backend-domain-services-08`, compone la transición a `pending`) y por los routers (11/12).

## Definition of Done

- [ ] Tests escritos ANTES de la implementación (Red → Green → Refactor).
- [ ] Cada escenario Gherkin del CU (alcance de esta tarea) tiene al menos un test + los añadidos
  (asignación cross-tenant rechazada, CSAT Scenario Outline, `reopened` desde `resolved`/`closed`,
  transición separada `reopened→open`, `sla_due` recalculado al reabrir, `NotFound` sobre ticket
  inexistente, auto-transición rechazada).
- [ ] Todos los tests en verde (`make test`).
- [ ] `Provides` disponible; el dominio no importa `app.infra`.
- [ ] `ruff check` (+`S`) + `ruff format --check` + `mypy` strict OK.
- [ ] Gate de mutation `cosmic-ray` (`break: 80`) sobre `ticket_service.py` (`sla_policy.py` es Protocol,
  N/A).
- [ ] Gate `/sdd-lint` sin ERROR (CU-BE-04 Gherkin bien formado, enlace válido).
- [ ] Gate de `fact-checker`.
- [ ] Documentación: docstrings (máquina de estados, por qué `reopened` no auto-encadena, contrato de
  `SlaPolicy`); session log con la traza a CU-BE-04 y el hueco nombrado de FR-030.
