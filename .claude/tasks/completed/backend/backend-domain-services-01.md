---
id: backend-domain-services-01
package: backend
plan: domain-services
status: done
priority: 1
depends_on: []
estimate: 2h
actual: 0.6h
issue:
created: 2026-08-18
updated: 2026-08-18
---

# Entidades de dominio (identidad + negocio) + enums propios + test de drift dominio↔ORM

## Description

El dominio necesita tipos propios: no puede importar `app.infra.db.models` (rompería hexagonal, NFR-003).
Entidades Pydantic v2 (identidad + negocio unificadas en una sola tarea — son igual de declarativas que
las de negocio; partirlas no reduce riesgo, a diferencia de los 18 modelos ORM con constraints reales de
`database-foundation`) + enums propios (mismo conjunto de valores que `app.infra.db.models.enums`, pero
sin importarlos). Incluye `Subject`/`Resource` (los necesita `authorize`, objetivo 4) y `AuditLogEntry`
(la necesita el puerto de auditoría, objetivos 5/9) — ninguno estaba en el guión original de
`app/domain/__init__.py`. Guión: `app/domain/entities/`. Spec: NFR-003, `data-model.md` (entidades),
`rbac.md §1` (`Subject`).

## Spec

- `app/domain/entities/enums.py`: enums Python propios, **mismo conjunto de valores** (no de nombres) que
  `app.infra.db.models.enums`: `TenantStatus`, `UserStatus`, `RoleKind`, `CapabilityScope`,
  `RefreshSessionStatus`, `AuthTokenKind`, `TicketStatus` (incl. `reopened`), `TicketPriority`,
  `MessageVisibility`, `ApprovalStatus`, `AgentRunStatus`, `NotificationType`, `KbDomain` (17).
- `app/domain/entities/identity.py`: `Tenant`, `User`, `Role`, `Capability`, `RefreshSession`, `AuthToken`,
  `Subject` (sujeto autenticado + su conjunto efectivo de `(capability, scope)`, `rbac.md §1`).
- `app/domain/entities/business.py`: `Ticket`, `Message`, `ApprovalTask`, `AgentRun`, `Notification`,
  `Resource` (aporta `tenant_id`/dueño para `authorize`, `rbac.md §7`), `AuditLogEntry`.
- **Ninguna** entidad tiene un campo que el ORM real no tenga (p.ej. `Tenant` **no** lleva `auto_approve`
  — ese hueco queda nombrado para la tarea 16, no se resuelve con un campo aquí).
- `AuditLogEntry` espeja `audit_log` (data-model.md §4.2): `action: str`, `entity_type: str`,
  `entity_id: str`, `payload: dict`, `actor_id: UUID | None`.
- Sin efectos en import (solo `class`/`enum` — Pydantic v2, sin I/O).

## Fuera de alcance

- Los servicios que consumen estas entidades → tareas 02-08.
- Los repositorios/adaptadores concretos → fuera de este plan (09/11/12/16).

## Scenarios (Gherkin)

<!-- SDD: infra de tipos → Gherkin LOCAL, "sin cambios de spec/CU". Verificación a nivel de import
     estático + comparación de valores de enum (unit). -->

```gherkin
Feature: entidades de dominio propias, sin acoplar a infra

  Scenario: el dominio no importa infra
    Given el árbol de módulos de app.domain
    When se inspeccionan sus imports
    Then ninguno importa app.infra ni sqlalchemy

  Scenario Outline: los enums de dominio tienen el mismo conjunto de valores que el ORM
    Given el enum de dominio <enum_dominio> y su equivalente <enum_orm> en app.infra.db.models.enums
    When se comparan sus conjuntos de valores
    Then son exactamente iguales (comparación por valor, no por nombre)

    Examples:
      | enum_dominio          | enum_orm              |
      | TicketStatus          | TicketStatus          |
      | TicketPriority        | TicketPriority        |
      | MessageVisibility     | MessageVisibility     |
      | ApprovalStatus        | ApprovalStatus        |
      | AgentRunStatus        | AgentRunStatus        |
      | KbDomain              | KbDomain              |
      | UserStatus            | UserStatus            |
      | TenantStatus          | TenantStatus          |
      | RoleKind              | RoleKind              |
      | CapabilityScope       | CapabilityScope       |
      | AuthTokenKind         | AuthTokenKind         |
      | NotificationType      | NotificationType      |
      | RefreshSessionStatus  | RefreshSessionStatus  |

  Scenario: Subject expone su conjunto efectivo de capacidades
    Given una instancia de Subject con capacidades resueltas
    When se inspeccionan sus atributos
    Then expone un conjunto de (capability, scope) consultable

  Scenario: Resource expone tenant_id para el ámbito
    Given una instancia de Resource
    When se inspecciona
    Then expone tenant_id (nullable, para recursos globales como la KB)

  Scenario: AuditLogEntry existe con la forma que sus consumidores necesitan
    Given el módulo app.domain.entities.business
    When se inspecciona AuditLogEntry
    Then expone action, entity_type, entity_id, payload y actor_id (nullable)

  Scenario: un valor de enum inválido es rechazado por Pydantic
    Given una entidad con un campo enum (p.ej. Ticket.status)
    When se construye con un valor que no pertenece al enum
    Then Pydantic rechaza la construcción con un error de validación
```

## Provides

Las entidades Pydantic v2 (`app.domain.entities.{identity,business,enums}`) que consumen los 6 servicios
(02-08) y sus puertos; el test de drift que protege contra divergencia silenciosa con el ORM.

## Definition of Done

- [ ] Tests escritos ANTES de la implementación (Red → Green → Refactor).
- [ ] Cada escenario Gherkin tiene al menos un test (import hexagonal, drift por enum incl.
  `RefreshSessionStatus`, forma de Subject/Resource/AuditLogEntry, rechazo Pydantic de enum inválido).
- [ ] Todos los tests en verde (`make test`).
- [ ] `Provides` disponible; el dominio no importa `app.infra`.
- [ ] `ruff check` (+`S`) + `ruff format --check` + `mypy` strict OK.
- [ ] Gate de mutation: entidades **declarativas** → N/A documentado (M4), **salvo** el test de drift, que
  sí ejercita comportamiento real (comparación de conjuntos) y entra en el gate de esta tarea.
- [ ] Gate `/sdd-lint` sin ERROR (SDD: sin cambios de spec/CU — infra de tipos).
- [ ] Gate de `fact-checker`.
- [ ] Documentación: docstrings de entidades/enums; session log.
