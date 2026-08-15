---
id: backend-database-foundation-07
package: backend
plan: database-foundation
status: done
priority: 1
depends_on: [backend-database-foundation-06]
estimate: 3.5h
actual: 1.2h
created: 2026-08-15
updated: 2026-08-15
---

# session.py: engine/sessionmaker async + helper de contexto RLS + tests de aislamiento (footgun)

## Description

La sesión async y el mecanismo que hace **efectiva** la RLS: `create_async_engine` (rol runtime
**`syntax_app`**, sujeto a RLS) + `async_sessionmaker(expire_on_commit=False)` + `get_session()`, y un
**helper de contexto de tenant** que fija `SET LOCAL app.tenant_id` (alcance transaccional) — y, para el
ámbito global, `SET LOCAL app.bypass_rls='on'`— y se resetea, de modo que una conexión reutilizada del pool
**no** filtra entre tenants (**footgun**). Es el corazón de NFR-002 / ADR-0006. Sin efectos en import.
Guión: `app/infra/db/session.py`. **Traza** a **CU-BE-03** (aislamiento) + FR-013/014/015; no 1:1 (el CU
necesita endpoints/RBAC → plan 10).

## Spec

- `create_async_engine(settings.database_url, ...)` (pool asyncpg) + `async_sessionmaker(engine,
  expire_on_commit=False)`; `get_session()` cede `AsyncSession`. Sin efectos en import (lazy).
- Helper de contexto RLS (p.ej. `async with tenant_scope(session, tenant_id): ...`): abre/usa transacción y
  fija el GUC con **`SELECT set_config('app.tenant_id', $1, true)`** (bind-safe; `SET LOCAL` **no** admite bind
  params — corrección del QA) tras **validar que `tenant_id` es UUID**; variante `global` fija
  `set_config('app.bypass_rls', 'on', true)`. El tercer arg `true` = alcance transaccional → se descarta al
  cerrar la transacción (commit **o** rollback). Reset explícito de **ambos** GUC (tenant_id **y** bypass).
- **Determinismo**: sin depender de reloj real; tiempo vía puerto `clock` donde aplique.
- Tests de aislamiento (**integración obligatoria**, conexión `syntax_app`, filas **commiteadas**, limpieza
  `TRUNCATE` — no rollback envolvente, ver H5): aislamiento por tenant, reúso de conexión del pool sin fuga,
  bypass global, KB/identidad sin filtro, GUC ausente = fail-closed (0 filas, sin excepción).

## Fuera de alcance

- `get_tenant_context`/`get_current_subject`/RBAC (quién obtiene `global`) → plan 10.
- `BaseRepository` (08) y `/health/ready` (09).

## Scenarios (Gherkin)

<!-- SDD: primitiva de infra → Gherkin LOCAL, "sin cambios de spec/CU", con TRAZA a CU-BE-03 (aislamiento
     tenant) + FR-013/014/015 + NFR-002. Integración obligatoria contra Postgres real como `syntax_app`. -->

```gherkin
Feature: aislamiento multi-tenant por RLS a nivel de sesión

  Scenario: con el contexto en un tenant solo se ven sus filas
    Given filas de negocio de los tenants A y B
    When se consulta con el contexto fijado al tenant A (como syntax_app)
    Then solo se devuelven las filas del tenant A

  Scenario: una escritura respeta el tenant del contexto
    Given el contexto fijado al tenant A
    When se inserta una fila de negocio sin tenant de otro
    Then la fila queda asociada al tenant A (WITH CHECK)

  Scenario: reúso de conexión del pool no filtra entre tenants (footgun)
    Given una transacción con contexto en tenant A que termina
    When otra transacción reutiliza la misma conexión del pool con contexto en tenant B
    Then la segunda no ve ninguna fila del tenant A (el SET LOCAL no persiste)

  Scenario: el ámbito global ve cross-tenant
    Given filas de los tenants A y B
    When se consulta activando el bypass por transacción (app.bypass_rls='on')
    Then se devuelven filas de ambos tenants

  Scenario: sin contexto de tenant no se ve nada (fail-closed)
    Given ninguna GUC app.tenant_id fijada
    When se consulta una tabla de negocio como syntax_app
    Then se devuelven 0 filas (sin excepción; current_setting missing_ok)

  Scenario: las tablas KB e identidad no filtran por tenant
    Given filas KB (globales) y contexto fijado a un tenant
    When se consultan las tablas KB/identidad
    Then se ven todas (no llevan RLS)

  # ── Endurecido por scenario-coverage ──

  Scenario: el bypass global no se arrastra a la siguiente transacción (footgun del GUC de bypass)
    Given una transacción con bypass global que termina, sobre una conexión del pool
    When otra transacción reutiliza esa conexión con el contexto fijado a un tenant
    Then la segunda solo ve filas de ese tenant (el bypass no persiste)

  Scenario: escritura con tenant_id de otro tenant se rechaza (WITH CHECK)
    Given el contexto fijado al tenant A
    When se inserta/actualiza una fila con tenant_id explícito del tenant B
    Then la operación se rechaza (WITH CHECK), no se acepta ni se reescribe silenciosamente

  Scenario: tenant_id malformado produce un error controlado
    Given un tenant_id que no es un UUID válido
    When se intenta abrir el contexto de tenant
    Then falla de forma controlada (validación previa), no con una excepción cruda de Postgres

  Scenario: el contexto se descarta también al hacer ROLLBACK
    Given una transacción con contexto en tenant A que lanza una excepción
    When la transacción hace rollback y la conexión vuelve al pool
    Then un uso posterior de esa conexión no ve el contexto de A

  Scenario Outline: solo el literal 'on' activa el bypass global
    Given app.bypass_rls fijado a <valor>
    When se consulta una tabla de negocio con filas de varios tenants
    Then el resultado es <efecto>

    Examples:
      | valor | efecto                          |
      | on    | ve todos los tenants (bypass)   |
      | true  | NO bypass (filtra por tenant)   |
      | 1     | NO bypass (filtra por tenant)   |
```

## Provides

`get_session()`, el `async_sessionmaker`/engine (rol `syntax_app`) y el helper de contexto RLS
(`tenant_scope` + bypass global) — consumidos por `/health/ready` (09), `BaseRepository` (08) y, más
adelante, `deps.get_tenant_context` (plan 10).

## Definition of Done

- [ ] Tests escritos ANTES de la implementación (Red → Green → Refactor) — integración obligatoria (Postgres real).
- [ ] Cada escenario Gherkin tiene al menos un test (aislamiento lectura/escritura, footgun de pool, bypass global, fail-closed sin GUC, KB/identidad sin filtro).
- [ ] Todos los tests en verde (`make test` con `docker compose up -d db`).
- [ ] `Provides` disponible; sin efectos en import; determinismo (sin reloj real).
- [ ] `ruff check` (+`S`) + `ruff format --check` + `mypy` strict OK.
- [ ] Gate de mutation `cosmic-ray` (`break: 80`) sobre `app/infra/db/session.py` (**código de comportamiento**: helper de contexto RLS).
- [ ] Gate `/sdd-lint` sin ERROR (SDD: sin cambios de spec/CU; **traza a CU-BE-03 + FR-013/014/015 + NFR-002** en el session log).
- [ ] Gate de `fact-checker`.
- [ ] Documentación: docstrings (intención, footgun, params); session log con la traza a CU-BE-03.
