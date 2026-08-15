---
id: backend-database-foundation-06
package: backend
plan: database-foundation
status: pending
priority: 1
depends_on: [backend-database-foundation-05]
estimate: 4h
actual:
created: 2026-08-15
updated: 2026-08-15
---

# Alembic + migración inicial (extensión, schema, RLS) + rol app + fixture test-DB + ADR-0016

## Description

Materializa el esquema real y el aislamiento a nivel DB. Configura Alembic async (`alembic.ini`,
`alembic/env.py` que lee `MIGRATION_DATABASE_URL` del entorno, `script.py.mako`) y escribe la migración
`0001_initial_schema` **a mano** (autogenerate no emite extensión ni RLS). Aparte de Alembic, un **init
script** crea el rol `syntax_app` (fuera de la migración, ver M1/M2 y ADR-0016). Monta la **infra de test**
(DB `syntax_test` + fixture) con el **gate de drift** y el **smoke de RLS**. Corre como **superuser**. Spec:
`data-model.md` §6/§8/§9, ADR-0006, ADR-0010. Nueva **ADR-0016** (RLS vía rol dedicado + GUC de bypass).

## Spec

- **Init script** (`docker-entrypoint-initdb.d/*.sql` local + doc ops prod): `CREATE ROLE syntax_app
  NOSUPERUSER NOBYPASSRLS LOGIN`; password out-of-band (`ALTER ROLE ... PASSWORD`, desde env). Idempotente.
- `alembic.ini` + `alembic/env.py` (online async, `async_engine_from_config` + `run_sync`, `target_metadata =
  Base.metadata`, URL de `MIGRATION_DATABASE_URL`) + `script.py.mako`.
- `0001_initial_schema` (revision `0001`, down `None`): `CREATE EXTENSION IF NOT EXISTS vector`; las **18
  tablas** + enums + FKs/cascadas + índices (unicidad/compuestos, **sin ANN**); `embedding.vector` literal
  **`vector(1536)`** (M3); **GRANTs** DML a `syntax_app` (schema + tablas + secuencias + tipos enum); y, en las
  **7 tablas de negocio**: `ENABLE ROW LEVEL SECURITY` + `CREATE POLICY tenant_isolation` con **`USING
  (current_setting('app.bypass_rls', true) = 'on' OR tenant_id = current_setting('app.tenant_id', true)::uuid)`**
  y el **mismo `WITH CHECK`** (H2). `downgrade()` revierte el schema (no toca el rol).
- **CHECK constraints** (decisión owner): `ticket.csat` en `1..5`, `agent_run.confidence` en `0..1`, y
  `role.tenant_id` NULL **sii** `role_kind='system'` (coherencia system/tenant).
- **Infra de test**: fixture session-scoped que crea/migra `syntax_test` (superuser, conexión autocommit a DB
  de mantenimiento para `CREATE DATABASE`); si `db` no alcanzable → error claro.
- **Gate de drift** (H3): `compare_metadata(Base.metadata, syntax_test)` → diff vacío.
- **Smoke RLS** (H4/M5): `relrowsecurity = true` en las 7 de negocio y `false` en KB+identidad; policy
  `tenant_isolation` existe en las 7.
- **ADR-0016** (MADR): rol dedicado no-superuser + GUC de bypass por transacción (refina ADR-0006).

## Fuera de alcance

- El helper de contexto RLS de `session.py` y los tests de aislamiento de comportamiento (footgun/global) → 07.
- El índice ANN → plan RAG. La lógica de negocio → planes 10+.

## Scenarios (Gherkin)

<!-- SDD: infra/migración → Gherkin LOCAL, "sin cambios de spec/CU" (crea ADR-0016). Integración contra
     Postgres real (fixture test-DB). Endurecido después por scenario-coverage. -->

```gherkin
Feature: migración inicial con extensión, schema y RLS

  Scenario: la migración aplica limpia sobre una DB vacía
    Given una DB de test vacía
    When se ejecuta alembic upgrade head
    Then termina sin error And la extensión vector está instalada

  Scenario: se crean las 18 tablas
    Given la DB migrada
    When se listan las tablas del schema
    Then están las 18 entidades de data-model

  Scenario: RLS habilitada solo en las tablas de negocio
    Given la DB migrada
    When se inspecciona relrowsecurity de cada tabla
    Then es true en las 7 de negocio And false en KB e identidad/RBAC

  Scenario: cada tabla de negocio tiene la policy tenant_isolation
    Given la DB migrada
    When se listan las policies de las tablas de negocio
    Then cada una tiene una policy tenant_isolation

  Scenario: los modelos no divergen del schema migrado (drift)
    Given la DB migrada y Base.metadata
    When se ejecuta compare_metadata
    Then el diff está vacío

  Scenario: la columna de embeddings es vector(1536)
    Given la DB migrada
    When se inspecciona embedding.vector
    Then su tipo es vector con dimensión 1536

  Scenario: los tests de integración fallan claro si la DB no está
    Given docker db no alcanzable
    When arranca la fixture de test-DB
    Then falla con un error claro (no se saltan en silencio)

  # ── Endurecido por scenario-coverage ──

  Scenario: upgrade es idempotente (ya en head)
    Given una DB ya migrada a head
    When se ejecuta alembic upgrade head otra vez
    Then es no-op y no falla

  Scenario: downgrade y re-upgrade reproducen el schema
    Given una DB migrada
    When se ejecuta alembic downgrade base y luego upgrade head
    Then el schema resultante es equivalente al inicial (sin error)

  Scenario: el downgrade no borra el rol de aplicación
    Given una DB migrada con el rol syntax_app existente
    When se ejecuta alembic downgrade base
    Then el rol syntax_app sigue existiendo (el rol se gestiona fuera de Alembic)

  Scenario: el init script del rol es idempotente
    Given el rol syntax_app ya existente
    When se re-ejecuta el init script
    Then no falla (CREATE ROLE idempotente)

  Scenario: el rol de aplicación no es superusuario ni bypassa RLS
    Given el rol syntax_app creado
    When se inspecciona pg_roles
    Then rolsuper = false And rolbypassrls = false (premisa de ADR-0016)

  Scenario: syntax_app tiene GRANTs de CRUD en las 18 tablas
    Given la DB migrada
    When se comprueban los privilegios de syntax_app
    Then puede SELECT/INSERT/UPDATE/DELETE en las 18 tablas (negocio, identidad y KB)

  Scenario: MIGRATION_DATABASE_URL ausente da un error claro
    Given MIGRATION_DATABASE_URL no está en el entorno
    When se arranca alembic env.py
    Then falla con un mensaje claro (no un KeyError críptico)

  Scenario: el gate de drift detecta un cambio de dimensión de vector
    Given un modelo de prueba con embedding.vector de dimensión distinta a la migrada
    When se ejecuta compare_metadata
    Then el diff NO está vacío (el gate H3 no da falso negativo con el tipo Vector)

  Scenario: la fixture reutiliza syntax_test si ya existe y está en head
    Given syntax_test existente de una ejecución previa (migrada a head)
    When arranca la fixture de test-DB
    Then la reutiliza sin recrearla ni fallar por DuplicateDatabase

  Scenario Outline: los CHECK de rango rechazan valores fuera de rango
    Given una fila de negocio con <campo> = <valor>
    When se intenta persistir
    Then <resultado>

    Examples:
      | campo             | valor | resultado           |
      | ticket.csat       | 5     | se acepta           |
      | ticket.csat       | 6     | se rechaza (CHECK)  |
      | agent_run.confidence | 1.0 | se acepta          |
      | agent_run.confidence | 1.5 | se rechaza (CHECK) |
```

## Provides

DB migrada (schema + extensión + RLS policies), rol `syntax_app` con GRANTs, la **fixture de test-DB**
(`syntax_test`) reutilizable por 07/08/09, el gate de drift y el smoke de RLS. **ADR-0016**.

## Definition of Done

- [ ] Tests escritos ANTES de la implementación (Red → Green → Refactor) — integración contra Postgres real.
- [ ] Cada escenario Gherkin tiene al menos un test (aplica limpia, 18 tablas, relrowsecurity, policy, drift, vector(1536), fallo-si-db-caída).
- [ ] Todos los tests en verde (`make test` con `docker compose up -d db`).
- [ ] `Provides` disponible: `alembic upgrade head` reproducible; fixture test-DB usable por las tareas dependientes.
- [ ] `ruff check` (+`S`) + `ruff format --check` + `mypy` strict OK.
- [ ] Gate de mutation: DDL/migración **declarativa** → mutation N/A documentado (M4); el código de fixture/g
      helpers de test no es de producción.
- [ ] Gate `/sdd-lint` sin ERROR (SDD: sin cambios de spec/CU; **ADR-0016 MADR** bien formado + `adr-index`).
- [ ] Gate de `fact-checker`.
- [ ] Documentación: **ADR-0016** (doc técnica) + `adr-index`; docstrings de `env.py`/fixture; `Makefile`/README
      (arranque de `db` + `MIGRATION_DATABASE_URL`); session log.
