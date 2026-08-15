---
id: backend-database-foundation-02
package: backend
plan: database-foundation
status: pending
priority: 1
depends_on: [backend-database-foundation-01]
estimate: 1.5h
actual:
created: 2026-08-15
updated: 2026-08-15
---

# base.py: DeclarativeBase + naming_convention + mixins Timestamp/Tenant

## Description

Fundamento ORM compartido por todos los modelos: `Base(DeclarativeBase)` de SQLAlchemy 2 con una
`naming_convention` explícita en su `metadata` (para que Alembic genere nombres de constraints/índices
**deterministas** y los diffs sean estables) y los mixins reutilizables `TimestampMixin` (`created_at`/
`updated_at` con `server_default`/`onupdate`) y `TenantMixin` (`tenant_id: Mapped[UUID]` NOT NULL con FK a
`tenant`, la marca de "tabla de negocio con RLS"). El dominio NO importa nada de esto (hexagonal, NFR-003).
Guión: `app/infra/db/base.py`. Spec: `data-model.md` §7 (cascadas), NFR-003.

## Spec

- `class Base(DeclarativeBase)` con `metadata = MetaData(naming_convention=<convención estándar>)`
  (`ix`/`uq`/`ck`/`fk`/`pk` con plantillas por columnas/tabla).
- `TimestampMixin`: `created_at` (`server_default=now()`), `updated_at` (`server_default=now()`, `onupdate=now()`),
  ambos timezone-aware.
- `TenantMixin`: `tenant_id: Mapped[uuid.UUID]` NOT NULL, FK a `tenant.id` (la usarán solo las 7 tablas de negocio).
- `Base.metadata` es el `target_metadata` que consumirá `alembic/env.py` (06).
- Sin efectos en import (solo definiciones de clase/metadata).

## Fuera de alcance

- Las entidades concretas → tareas 03/04/05. La sesión/engine → 07. La migración → 06.

## Scenarios (Gherkin)

<!-- SDD: infra ORM → Gherkin LOCAL, "sin cambios de spec/CU". Verificación a nivel de metadata (unit). -->

```gherkin
Feature: fundamento ORM determinista

  Scenario: la metadata usa una convención de nombres explícita
    Given el Base declarativo
    When se inspecciona su metadata
    Then define una naming_convention para ix/uq/ck/fk/pk

  Scenario: TimestampMixin aporta created_at y updated_at
    Given un modelo que hereda TimestampMixin
    When se inspeccionan sus columnas
    Then tiene created_at y updated_at timezone-aware con server_default

  Scenario: TenantMixin aporta tenant_id NOT NULL con FK a tenant
    Given un modelo que hereda TenantMixin
    When se inspecciona la columna tenant_id
    Then es UUID NOT NULL con ForeignKey a tenant.id

  Scenario Outline: cada tipo de constraint sigue su plantilla de nombre
    Given un modelo con una constraint de tipo <tipo>
    When se genera su nombre
    Then sigue la plantilla <tipo> de la naming_convention (determinista)

    Examples:
      | tipo |
      | pk   |
      | fk   |
      | uq   |
      | ix   |
      | ck   |

  Scenario: dos modelos con TenantMixin no colisionan en el nombre de la FK a tenant
    Given dos modelos distintos que heredan TenantMixin
    When se generan los nombres de sus FK a tenant
    Then los nombres son distintos (incluyen la tabla origen)
```

## Provides

`Base` (DeclarativeBase + metadata con naming_convention), `TimestampMixin`, `TenantMixin`, y `Base.metadata`
como `target_metadata` para Alembic (06) y base de todos los modelos (03/04/05).

## Definition of Done

- [ ] Tests escritos ANTES de la implementación (Red → Green → Refactor).
- [ ] Cada escenario Gherkin tiene al menos un test (naming_convention, TimestampMixin, TenantMixin, nombre determinista).
- [ ] Todos los tests en verde (`make test`).
- [ ] `Provides` disponible; sin efectos en import; el dominio no importa `app.infra`.
- [ ] `ruff check` (+`S`) + `ruff format --check` + `mypy` strict OK.
- [ ] Gate de mutation: `base.py` es **declarativo** → mutation N/A documentado (M4 del plan; sin código de comportamiento).
- [ ] Gate `/sdd-lint` sin ERROR (SDD: sin cambios de spec/CU — infra ORM).
- [ ] Gate de `fact-checker`.
- [ ] Documentación: docstrings de Base/mixins; session log.
