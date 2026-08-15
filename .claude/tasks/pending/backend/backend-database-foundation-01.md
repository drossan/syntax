---
id: backend-database-foundation-01
package: backend
plan: database-foundation
status: pending
priority: 1
depends_on: []
estimate: 1.5h
actual:
created: 2026-08-15
updated: 2026-08-15
---

# Settings de DB: database_url (syntax_app) + embedding_dim + DSN de app en .env/compose

## Description

La capa DB necesita config. Hoy `Settings` no tiene DSN de base de datos (el `.env` los define pero
`extra="ignore"` los descarta). Se añaden `database_url` (rol runtime **`syntax_app`**, no superuser) y
`embedding_dim`, **ambos con default** para no romper el boot/tests existentes. La URL de migraciones
(**superuser**) NO va en `Settings` (least-privilege): la lee `alembic/env.py` del entorno. Además el
`DATABASE_URL` de `.env.example` y del servicio `api` de `docker-compose.yml` debe apuntar a `syntax_app`
(si apunta al superuser, RLS quedaría apagado en `make run`/compose). Spec: NFR-001 (secretos por entorno),
FR-013 (aislamiento). Guión: `app/core/config.py`.

## Spec

- `Settings.database_url: str` — DSN asyncpg del rol `syntax_app`; **default** de desarrollo
  (`postgresql+asyncpg://syntax_app:...@localhost:5432/syntax`) para que `Settings()` sea construible sin `.env`.
- `Settings.embedding_dim: int = 1536` — dimensión de embeddings, **`Field(gt=0)`** (rechaza 0/negativo).
  Consumido solo por `/health/ready` (09) para asertar la dimensión viva (el modelo usa `Vector(1536)` literal).
- `database_url`: rechaza cadena vacía (default aplica solo si la var está ausente, no si es `""`).
- **`MIGRATION_DATABASE_URL` NO es campo de `Settings`** — se lee del entorno en `alembic/env.py` (tarea 06).
- `.env.example`: `DATABASE_URL` → `syntax_app`; añadir la var de migración (superuser) comentada + la
  password de `syntax_app`. `docker-compose.yml` (`api`): `DATABASE_URL` default → `syntax_app`.
- Sin efectos en import (heredado de config.py): `get_settings()` sigue cacheado.

## Fuera de alcance

- El rol `syntax_app` en la DB (init script) y su uso real → tareas 06/07.
- `get_tenant_context`/RBAC → plan 10.

## Scenarios (Gherkin)

<!-- SDD: infra pura de config → Gherkin LOCAL, "sin cambios de spec/CU". Ancla NFR-001/FR-013.
     Los edits de .env.example/docker-compose.yml se verifican por inspección (grep), no por test unit;
     se declaran en el session log. -->

```gherkin
Feature: configuración de base de datos inyectable

  Scenario: database_url se lee del entorno
    Given la variable DATABASE_URL en el entorno
    When se cargan los settings
    Then database_url es ese valor

  Scenario: database_url tiene default sin entorno ni .env
    Given ni DATABASE_URL en el entorno ni en .env
    When se construyen los settings aislados
    Then database_url toma el DSN de desarrollo por defecto (rol syntax_app)

  Scenario: embedding_dim se expone como entero con default 1536
    Given ninguna EMBEDDING_DIM en el entorno
    When se cargan los settings
    Then embedding_dim es 1536 (int)

  Scenario: embedding_dim inválido aborta la carga
    Given EMBEDDING_DIM = "no-numérico"
    When se cargan los settings
    Then se produce un error de validación

  Scenario: la URL de migración no es un campo de Settings
    Given los settings cargados
    When se inspecciona la instancia de Settings
    Then no existe un atributo para la URL de migración (superuser)

  # ── Endurecido por scenario-coverage ──

  Scenario Outline: embedding_dim rechaza valores no físicos
    Given EMBEDDING_DIM = <valor>
    When se cargan los settings
    Then el resultado es <resultado>

    Examples:
      | valor | resultado                |
      | 1536  | válido                   |
      | 0     | error de validación (gt=0) |
      | -1    | error de validación (gt=0) |

  Scenario: database_url vacío se rechaza
    Given DATABASE_URL = "" (presente pero vacío)
    When se cargan los settings
    Then se produce un error de validación (no se usa el default con vacío)
```

## Provides

`settings.database_url` y `settings.embedding_dim` disponibles para `session.py` (07), `alembic/env.py` (06),
los modelos (05) y `/health/ready` (09). El `DATABASE_URL` de `.env.example`/compose ya apunta al rol restringido.

## Definition of Done

- [ ] Tests escritos ANTES de la implementación (Red → Green → Refactor).
- [ ] Cada escenario Gherkin tiene al menos un test (lectura/env, default, int/default, inválido, ausencia de campo migración).
- [ ] Todos los tests en verde (`make test`).
- [ ] `Provides` disponible; sin efectos en import; defaults no rompen los tests existentes.
- [ ] `ruff check` (+`S`) + `ruff format --check` + `mypy` strict OK.
- [ ] Gate de mutation `cosmic-ray` (`break: 80`) sobre `app/core/config.py` (los campos/validadores nuevos).
- [ ] Gate `/sdd-lint` sin ERROR (SDD: sin cambios de spec/CU — infra de config).
- [ ] Gate de `fact-checker`.
- [ ] Documentación: docstrings de los campos nuevos; `.env.example` actualizado (dev doc); session log con la verificación por grep de `.env.example`/`docker-compose.yml`.
