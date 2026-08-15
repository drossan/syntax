---
id: backend-database-foundation-04
package: backend
plan: database-foundation
status: pending
priority: 1
depends_on: [backend-database-foundation-03]
estimate: 2.5h
actual:
created: 2026-08-15
updated: 2026-08-15
---

# Modelos ORM — negocio (7 tablas con TenantMixin, marcadas para RLS)

## Description

Los modelos del grupo **negocio**, que llevan `tenant_id` (`TenantMixin`) y serán las **únicas** con RLS
(`data-model.md` §2/§6): `ticket`, `message`, `attachment`, `approval_task`, `agent_run`, `audit_log`,
`notification`. Con sus enums nativos, FKs/cascadas (`data-model.md` §7: SET NULL en requester/assignee/
author/actor; CASCADE en el agregado del ticket) e índices compuestos por tenant. Spec: `data-model.md`,
FR-013 (toda tabla de negocio filtra por tenant), NFR-003.

## Spec

- 7 modelos heredando `TenantMixin` (+ `TimestampMixin` donde aplique); columnas de `data-model.md` §5.
- Enums nativos: `ticket_status`, `message_visibility` (**sin `developer` en Fase 1**), `agent_run_status`
  (incl. `failed`), `notification_type`, y los que apliquen.
- FKs/cascadas de §7 (SET NULL vs CASCADE según la relación); índices compuestos (p.ej. `(tenant_id, updated_at)`
  para el orden por defecto del contrato).
- `agent_run.sources` como JSONB (forma laxa; su detalle fino es del plan del agente).
- Todas registradas en `Base.metadata`.

## Fuera de alcance

- KB (05). La migración/políticas RLS reales (06). La lógica de negocio que las usa (planes 10+).
- El enum `developer` de `message_visibility` (Fase 2).

## Scenarios (Gherkin)

<!-- SDD: modelos de infra → Gherkin LOCAL, "sin cambios de spec/CU". Verificación a nivel de metadata (unit). -->

```gherkin
Feature: modelos de negocio con tenant

  Scenario: las 7 tablas de negocio están registradas
    Given la metadata de los modelos
    When se listan las tablas del grupo negocio
    Then están las 7 (ticket, message, attachment, approval_task, agent_run, audit_log, notification)

  Scenario: toda tabla de negocio lleva tenant_id NOT NULL
    Given los modelos de negocio
    When se inspecciona cada uno
    Then todos tienen tenant_id UUID NOT NULL con FK a tenant (marca de RLS)

  Scenario: message_visibility no incluye developer en Fase 1
    Given el enum message_visibility
    When se inspeccionan sus valores
    Then no contiene "developer"

  Scenario: agent_run_status incluye failed
    Given el enum agent_run_status
    When se inspeccionan sus valores
    Then contiene "failed"

  Scenario Outline: las cascadas de FK siguen data-model §7
    Given la FK <fk>
    When se inspecciona su on_delete
    Then es <accion>

    Examples:
      | fk                        | accion   |
      | ticket.requester_id       | SET NULL |
      | ticket.assignee_id        | SET NULL |
      | message.ticket_id         | CASCADE  |
      | message.author_id         | SET NULL |
      | attachment.message_id     | CASCADE  |
      | approval_task.decided_by  | SET NULL |
      | agent_run.ticket_id       | CASCADE  |
      | audit_log.actor_id        | SET NULL |
      | notification.user_id      | CASCADE  |

  # ── Endurecido por scenario-coverage ──

  Scenario Outline: los enums de negocio tienen exactamente su conjunto de valores
    Given el enum <enum>
    When se inspecciona el conjunto de sus valores
    Then es exactamente <valores> (ni más ni menos)

    Examples:
      | enum              | valores                                              |
      | ticket_status     | new, open, pending, on_hold, resolved, closed        |
      | ticket_priority   | low, normal, high, urgent                            |
      | approval_status   | pending, approved, edited, rejected                  |
      | notification_type | assigned, mentioned, sla_warning, sla_breach, decided |
      | message_visibility | public, internal                                    |
      | agent_run_status  | pending, running, succeeded, failed                  |

  Scenario Outline: los índices compuestos de §9 existen en los modelos
    Given el modelo <modelo>
    When se inspeccionan sus índices
    Then existe un índice sobre <columnas>

    Examples:
      | modelo        | columnas               |
      | ticket        | (tenant_id, status)    |
      | ticket        | (tenant_id, sla_due)   |
      | message       | (ticket_id, created_at) |
      | approval_task | (tenant_id, status)    |
      | notification  | (user_id, read_at)     |
```

> Nota: los valores exactos de los enums de arriba se confirman contra `data-model.md` §3 al implementar (el
> QA marcó que el conteo/valores deben cuadrar 1:1 con la spec). Los CHECK de rango (`csat`, `confidence`) viven
> en la migración (tarea 06).

## Provides

Los 7 modelos ORM de negocio (con `tenant_id`) en `app.infra.db.models`, base para la RLS de la migración
(06), los tests de aislamiento (07) y el `BaseRepository` (08).

## Definition of Done

- [ ] Tests escritos ANTES de la implementación (Red → Green → Refactor).
- [ ] Cada escenario Gherkin tiene al menos un test (7 tablas, tenant_id NOT NULL, message_visibility sin developer, agent_run_status failed, cascadas).
- [ ] Todos los tests en verde (`make test`).
- [ ] `Provides` disponible; el dominio no importa `app.infra`.
- [ ] `ruff check` (+`S`) + `ruff format --check` + `mypy` strict OK.
- [ ] Gate de mutation: modelos **declarativos** → mutation N/A documentado (M4 del plan).
- [ ] Gate `/sdd-lint` sin ERROR (SDD: sin cambios de spec/CU — modelos de infra).
- [ ] Gate de `fact-checker`.
- [ ] Documentación: docstrings de los modelos/enums; session log.
