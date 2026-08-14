# CU-BE-10 — Notificaciones in-app

> **SDD** (Cockburn + Gherkin). CÓMO para FR-038 de [`../spec.md`](../spec.md). Detalle:
> [`../data-model.md`](../data-model.md) (`notification`, `notification_type`). Entrega por **polling** (sin push).

- **Ámbito**: backend (servicio de notificación)
- **Nivel**: subfunción (transversal a eventos de negocio)
- **Actor primario**: sistema (genera); usuario destinatario (consume por polling)
- **Interesados e intereses**:
  - Usuario — enterarse de aprobaciones pedidas, asignaciones, respuestas y SLA.
  - Plataforma — entrega simple (in-app + polling), sin infraestructura de push en Fase 1.

## Precondiciones

- Ocurre un evento notificable con un destinatario dentro de un tenant.

## Garantía mínima

- Una notificación pertenece a su tenant y solo la ve su destinatario.

## Garantía de éxito (postcondición)

- El destinatario tiene una `notification` no leída que puede consultar y marcar leída.

## Disparador

- Un evento: `approval_requested`, `ticket_assigned`, `ticket_reply`, `sla_warning`, `sla_breach`.

## Escenario principal (éxito)

1. Ocurre un evento notificable; el sistema crea una `notification` (`type`, `payload`) para el destinatario.
2. El cliente hace polling de `/notifications` (orden `-created_at`).
3. El destinatario marca la notificación como leída (`read_at`).

## Extensiones (flujos alternativos y de error)

- **1a.** El destinatario pertenece a otro tenant: la notificación no le llega (aislamiento).
- **3a.** Marcar leída una ya leída: no-op (idempotente).

## Reglas de negocio

- **RN-1** — Los tipos válidos son el enum `notification_type`.
- **RN-2** — El contador de no-leído se deriva de `read_at IS NULL` para el `user_id`.

## Criterios de aceptación (Gherkin)

```gherkin
Feature: Notificaciones in-app

  Scenario: Un evento notificable genera una notificación
    Given un ticket que solicita aprobación de un borrador
    When se registra el evento de aprobación pedida
    Then el destinatario tiene una notificación no leída de ese tipo

  Scenario: Consulta ordenada de notificaciones
    Given un usuario con varias notificaciones
    When consulta su lista de notificaciones
    Then las recibe ordenadas de la más reciente a la más antigua

  Scenario: Marcar como leída
    Given una notificación no leída
    When el usuario la marca como leída
    Then deja de contar como no leída

  Scenario: Aislamiento del destinatario
    Given un evento notificable para un usuario de otro tenant
    When se genera la notificación
    Then no aparece en la lista de un usuario ajeno
```
