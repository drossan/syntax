---
id: backend-database-foundation-08
package: backend
plan: database-foundation
status: done
priority: 1
depends_on: [backend-database-foundation-07]
estimate: 2.5h
actual: 0.7h
created: 2026-08-15
updated: 2026-08-15
---

# BaseRepository tenant-aware (CRUD con filtro app-level por tenant_id)

## Description

Un repositorio base genérico que aporta la **primera línea de defensa** del aislamiento: el filtro
**app-level** por `tenant_id` en cada operación (sobre la RLS, que es defensa en profundidad — anti-patrón:
confiar solo en RLS, `repositories/__init__.py`). CRUD genérico (`get`/`list`/`add`/`delete`) tipado sobre un
modelo de negocio. **Nota de alcance** (design-review L5): es una primitiva **aceptada como especulativa** —
los repos concretos que implementan los puertos de dominio nacen en el **plan 10** y pueden remodelar esta
base. Spec: FR-013 (filtro app-level + RLS), `rbac.md` §5, NFR-003. Guión: `app/infra/db/repositories/`.

## Spec

- `BaseRepository[T]` genérico (o base tipada) con: `get(id, tenant_id) -> T | None`, `list(tenant_id) ->
  list[T]`, `add(entity) -> T`, `delete(id, tenant_id) -> bool`. Toda lectura/borrado **filtra por
  `tenant_id`** explícitamente (no depende solo de RLS).
- El orden de `list` es **determinista** y **se asserta** (testing.md §5) — p.ej. por la clave del contrato.
- No devuelve entidades ORM crudas al dominio como contrato final (esa frontera la fija el plan 10; aquí se
  prueba contra el modelo ORM real).
- Probado contra la DB de test (integración) con un modelo de negocio real.

## Fuera de alcance

- Repos concretos por entidad + implementación de los puertos de dominio → plan 10.
- `get_tenant_context`/RBAC (de dónde sale el `tenant_id`) → plan 10 (aquí se pasa explícito).

## Scenarios (Gherkin)

<!-- SDD: infra de persistencia → Gherkin LOCAL, "sin cambios de spec/CU". Integración contra Postgres real. -->

```gherkin
Feature: repositorio base con aislamiento app-level

  Scenario: get devuelve una fila del propio tenant
    Given una fila de negocio del tenant A
    When se hace get(id, tenant_id=A)
    Then devuelve la fila

  Scenario: get de otra tenant no la devuelve (filtro app-level)
    Given una fila del tenant B
    When se hace get(id, tenant_id=A)
    Then devuelve None (no revela la fila de B)

  Scenario: list solo devuelve filas del tenant y en orden determinista
    Given filas de los tenants A y B
    When se hace list(tenant_id=A)
    Then devuelve solo las de A And en el orden del contrato (aserción explícita)

  Scenario: add persiste la entidad
    Given una entidad nueva del tenant A
    When se hace add(entity)
    Then queda persistida y recuperable por get

  Scenario: delete solo borra dentro del tenant
    Given una fila del tenant B
    When se hace delete(id, tenant_id=A)
    Then no borra nada y devuelve False

  # ── Endurecido por scenario-coverage ──

  Scenario: list sin filas del tenant devuelve lista vacía
    Given ninguna fila del tenant A
    When se hace list(tenant_id=A)
    Then devuelve [] (lista vacía, no None ni excepción)

  Scenario: get de un id inexistente devuelve None
    Given un id que no existe en ninguna tenant
    When se hace get(id, tenant_id=A)
    Then devuelve None (indistinguible de "existe en otra tenant")

  Scenario: delete del mismo id dos veces es idempotente-seguro
    Given una fila propia del tenant A ya borrada
    When se vuelve a hacer delete(id, tenant_id=A)
    Then devuelve False sin excepción

  Scenario: add que viola una unicidad propaga un error claro
    Given una fila con una clave única ya existente
    When se hace add(entity)
    Then se propaga un IntegrityError (no se traga silenciosamente)
```

## Provides

`BaseRepository` (CRUD tenant-aware) en `app.infra.db.repositories`, base para los repos concretos del plan 10.

## Definition of Done

- [ ] Tests escritos ANTES de la implementación (Red → Green → Refactor) — integración (Postgres real).
- [ ] Cada escenario Gherkin tiene al menos un test (get propio/ajeno, list filtrado+orden, add, delete acotado).
- [ ] Todos los tests en verde (`make test` con `docker compose up -d db`).
- [ ] `Provides` disponible; el dominio no importa `app.infra`; orden determinista aserto.
- [ ] `ruff check` (+`S`) + `ruff format --check` + `mypy` strict OK.
- [ ] Gate de mutation `cosmic-ray` (`break: 80`) sobre `app/infra/db/repositories/` (**código de comportamiento**: el filtro tenant).
- [ ] Gate `/sdd-lint` sin ERROR (SDD: sin cambios de spec/CU — infra de persistencia).
- [ ] Gate de `fact-checker`.
- [ ] Documentación: docstrings; session log (incl. nota "especulativo, puede remodelarse en plan 10").
