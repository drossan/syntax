---
id: backend-routers-flujo-ia-04
package: backend
plan: routers-flujo-ia
status: done
priority: 2
depends_on: [backend-routers-flujo-ia-03]
estimate: 3h
actual: 3h
issue:
created: 2026-08-20
updated: 2026-08-20
---

# Cierra FR-038: notifica ticket_assigned / ticket_reply desde tickets.py / messages.py

## Description

`routers-core` dejó FR-038 explícitamente sin cablear ("hueco nombrado, plan 12"). Esta tarea cablea
`notification_service.emit()` desde los dos puntos de negocio que ya existen (`tickets.py`/`messages.py`,
cerrados en `routers-core`) — orquestación de router, sin tocar `ticket_service`/`MessageRepository`
(la notificación es best-effort, no atómica con lo que la dispara, mismo criterio que
`notification_service` desacoplado). Depende de la tarea 03 (necesita `get_notification_service` ya
ensamblable).

## Spec

- **`app/api/v1/routers/tickets.py`** (`assign_ticket`): tras `ticket_service.assign()` con éxito, calcula
  destinatarios = `{payload.assignee_id} - {subject.id}` (`scenario-coverage`, decisión del owner: se
  **excluye también al actor** — autoasignarse un ticket no genera notificación, misma regla que
  `ticket_reply`; una desasignación, `assignee_id=None`, no notifica a nadie) y emite
  `notification_service.emit(tenant_id, assignee_id, NotificationType.ticket_assigned, {"ticket_id":
  str(id)})` por cada destinatario resultante (0 o 1).
- **`app/api/v1/routers/messages.py`** (endpoint de creación de mensaje `public`): tras crear el mensaje
  con éxito, calcula destinatarios = `{ticket.requester_id, ticket.assignee_id} - {subject.id}` (autor
  excluido, sin `None`) y emite `Notification(type=ticket_reply)` a cada uno (`grilling` P4 de este plan
  — regla determinista sin `if` ad-hoc por caso). Mensajes `internal` **no** notifican.
- **Fallo de `emit()` no debe tumbar la respuesta principal** (`scenario-coverage`, único criterio
  coherente con "la notificación es best-effort, no atómica con lo que la dispara" que el propio plan ya
  declara): la llamada a `notification_service.emit()` en ambos routers va envuelta en un `try/except
  PortError` que solo **loguea** (`logging.warning`, sin importar `logging` module-level side effects —
  el logger se obtiene por función) y no re-lanza; el `assign`/`reply` ya confirmado devuelve su código de
  éxito normal (200/201) aunque la notificación falle.
- Ambos routers ganan `notification_service: NotificationService = Depends(get_notification_service)`
  como dependencia nueva.
- Sin cambios en `ticket_service`/`MessageRepository`/`notification_service` — solo wiring de router.

## Fuera de alcance

- `approval_requested` (lo crea el grafo vía `interrupt()`, planes 15/16).
- `sla_warning`/`sla_breach` (scheduler, tarea 18).
- Cualquier retry/compensación si `notification_service.emit()` falla tras la operación principal ya
  confirmada — best-effort, sin transacción distribuida (mismo criterio que el resto del backend).

## Scenarios (Gherkin)

Esta tarea no amplía ningún CU (wiring puro entre dos flujos ya especificados en CU-BE-04/CU-BE-10); los
escenarios viven en la propia tarea:

```gherkin
Feature: notificaciones automáticas tras asignar o responder un ticket

  Scenario: asignar un ticket notifica al nuevo agente
    Given un ticket sin asignar
    When se asigna a un agente concreto (distinto de quien asigna)
    Then el agente recibe una notificación ticket_assigned

  Scenario: reasignar un ticket solo notifica al nuevo agente
    Given un ticket ya asignado a un agente X
    When se reasigna a un agente Y
    Then Y recibe una notificación ticket_assigned y X no recibe ninguna

  Scenario: autoasignarse un ticket no genera notificación
    Given un ticket sin asignar
    When un agente se asigna el ticket a sí mismo
    Then no se crea ninguna notificación

  Scenario: desasignar un ticket no notifica a nadie
    Given un ticket asignado
    When se desasigna (assignee_id=null)
    Then no se crea ninguna notificación

  Scenario: si asignar falla, no se crea ninguna notificación
    Given un intento de asignación inválido (p.ej. assignee de otro tenant)
    When la asignación es rechazada por ticket_service
    Then no se crea ninguna notificación

  Scenario: un fallo al emitir la notificación no afecta la respuesta de la asignación
    Given un ticket que se asigna correctamente
    When notification_service.emit() falla (p.ej. PortError)
    Then la respuesta de la asignación sigue siendo exitosa (200)

  Scenario Outline: responder un ticket con mensaje público notifica a la otra parte
    Given un ticket con requester y assignee distintos
    When <autor> escribe un mensaje public
    Then <destinatario> recibe una notificación ticket_reply y <autor> no

    Examples:
      | autor     | destinatario |
      | assignee  | requester    |
      | requester | assignee     |

  Scenario: un tercer agente no asignado responde y notifica a ambas partes
    Given un ticket con requester y assignee, y un tercer agente del mismo tenant
    When el tercer agente escribe un mensaje public
    Then requester y assignee reciben cada uno una notificación ticket_reply

  Scenario: un mensaje interno no notifica
    Given un ticket con requester y assignee
    When se escribe un mensaje internal
    Then no se crea ninguna notificación
```

## Provides

—

## Definition of Done

- [x] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [x] Cada escenario Gherkin tiene al menos un test (camino feliz + bordes/errores)
- [x] Todos los tests en verde
- [x] Spec cumplida; lo declarado en `Provides` queda realmente disponible para las tareas dependientes
- [x] Lint / format / typecheck OK
- [x] Gate de mutation testing superado (`cosmic-ray`, `break:80`)
- [x] Gate `sdd-lint` superado (sin cambios de spec/CU; sincronía verificada contra FR-038)
- [x] Gate `fact-checker` superado (8/8 afirmaciones VERIFICADO tras corregir 2 incidentes de mutation)
- [x] Documentación — TSDoc + doc técnica + session log
- [x] Docs de dev/usuario donde aplique (N/A — sin superficie de usuario final nueva, solo wiring)
