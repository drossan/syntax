# CU-BE-08 — Scheduler de SLA

> **SDD** (Cockburn + Gherkin). CÓMO para FR-039 de [`../spec.md`](../spec.md) (B.2). Detalle:
> [`../data-model.md`](../data-model.md) (`ticket.sla_due`, `notification_type`). Worker acotado **solo** a SLA.

- **Ámbito**: backend (worker/job periódico de SLA)
- **Nivel**: subfunción (proceso de fondo)
- **Actor primario**: scheduler (sistema)
- **Interesados e intereses**:
  - Soporte — enterarse a tiempo de vencimientos para no incumplir plazos.
  - Plataforma — escalado idempotente, respetando el aislamiento por tenant.

## Precondiciones

- Existen tickets no resueltos con `sla_due` fijado.

## Garantía mínima

- Un mismo vencimiento no genera notificaciones/escalados duplicados aunque el job corra varias veces.

## Garantía de éxito (postcondición)

- Los tickets con SLA vencido/inminente tienen su notificación y, si procede, su escalado registrado.

## Disparador

- El job periódico se ejecuta.

## Escenario principal (éxito)

1. El job selecciona tickets no resueltos con `sla_due` vencido o inminente, por tenant (respetando RLS).
2. Por cada uno, crea `notification` (`sla_warning`/`sla_breach`) y aplica el escalado.
3. Marca el ticket como ya procesado (`sla_breached_at`) y lo audita.

## Extensiones (flujos alternativos y de error)

- **2a.** El ticket ya tenía `sla_breached_at`: el job **no** vuelve a notificar (idempotente).
- **1a.** El ticket pasó a resuelto/cerrado antes del job: se excluye.
- **2b.** Umbral **inminente** vs **vencido**: genera `sla_warning` vs `sla_breach` respectivamente.

## Reglas de negocio

- **RN-1** — La idempotencia se ancla en `sla_breached_at` (una sola vez por vencimiento).
- **RN-2** — El worker está acotado **solo** a SLA (no colas/tareas generales).
- **RN-3** — Opera por tenant respetando el aislamiento (RLS / contexto de tenant).

## Criterios de aceptación (Gherkin)

```gherkin
Feature: Scheduler de SLA

  Scenario: Notificación por SLA vencido
    Given un ticket no resuelto cuyo SLA ha vencido
    When se ejecuta el job de SLA
    Then se crea una notificación de incumplimiento y se aplica el escalado

  Scenario: Aviso por SLA inminente
    Given un ticket no resuelto cuyo SLA está próximo a vencer
    When se ejecuta el job de SLA
    Then se crea una notificación de aviso

  Scenario: El escalado no se duplica
    Given un ticket cuyo vencimiento de SLA ya fue procesado
    When el job de SLA vuelve a ejecutarse
    Then no se genera una notificación de incumplimiento nueva

  Scenario: Un ticket resuelto queda excluido
    Given un ticket cuyo SLA venció pero que ya está resuelto
    When se ejecuta el job de SLA
    Then el ticket no genera notificación de SLA
```
