# Session log — backend-database-foundation-01

Tarea: Settings de DB — `database_url` (rol `syntax_app`, con default) + `embedding_dim`
(`Field(gt=0)`, default 1536) + `.env.example`/`docker-compose.yml` → `syntax_app`.
`MIGRATION_DATABASE_URL` NO va en `Settings` (lo lee `alembic/env.py`, tarea 06).

Rama: `plan/backend/database-foundation`. Nivel: **unit** (sin Docker).

## Entradas

- 2026-08-15 — Arranque. Plan movido a `active/`, tarea 01 `active`. Leídos: HOW-TO-START,
  task-lifecycle, plan, tarea, `config.py` real, `.env.example`, `docker-compose.yml`,
  `test_config.py`, `conftest.py`, `cosmic-ray.toml`, `Makefile`. TDD escenario a escenario.

## Resumen

Añadidos a `Settings` (`app/core/config.py`) dos campos de DB inyectables, ambos con default
para no romper el boot/tests existentes:
- `database_url: str` = `postgresql+asyncpg://syntax_app:syntax_app@localhost:5432/syntax`
  (rol runtime **no-superuser** → RLS aplicará de verdad en tareas 06/07).
- `embedding_dim: int = Field(default=1536, gt=0)` — lo consume `/health/ready` (09).
- `field_validator("database_url", mode="after")` que rechaza `""`/whitespace (el default solo
  cubre la ausencia de la var, no un `""` explícito).

`MIGRATION_DATABASE_URL` **NO** es campo de `Settings` (least-privilege): lo leerá `alembic/env.py`
del entorno (tarea 06).

## Decisiones técnicas + porqué

- **Default en ambos campos**: `test_security.py`/`test_main.py` construyen `Settings(_env_file=None,
  jwt_secret=...)`; sin default, `database_url` sería requerido y rompería esos tests (L2 del plan).
- **`Field(gt=0)` (declarativo)** en vez de un `if` propio: constraint nativa de Pydantic, menos código y
  mensaje de error estándar. Cubre 0/negativo; el mínimo válido pasa a ser 1 (test de frontera lo fija).
- **Validator solo para el vacío**: la constraint de default no distingue "ausente" de `""`; el
  `field_validator` es el único sitio donde rechazar `""` sin perder el default de ausencia.
- **DSN a `syntax_app` en `.env.example`/compose** (H1): si `DATABASE_URL` apuntara al superuser `syntax`,
  `make run`/compose correrían con RLS **apagado**. El superuser queda solo para migraciones (var comentada).

## Tests corridos + resultado

- TDD: 10 tests RED nuevos → GREEN. `tests/test_config.py` (28 tests) verde; suite completa `pytest -q`
  verde (88 tests). [confirmado con `rtk proxy .venv/bin/python -m pytest`]
- `ruff check .` OK · `ruff format --check .` OK (tras aplicar format a un assert) · `mypy app` strict:
  Success, 79 source files.
- Gate mutation `cosmic-ray` sobre `app/core/config.py` (toml acotado a config.py + test_config.py):
  survival **10.00%** ≤ 20% → **pasa**. 2 supervivientes = `RemoveDecorator` (quitar `@classmethod` de
  validadores; Pydantic sigue enlazando → cuasi-equivalentes, no matables por comportamiento).
- `/sdd-lint` (backend): checks mecánicos limpios (0 `[NECESITA ACLARACIÓN`, 15/15 ADRs con estado MADR
  válido). Tarea sin cambios SDD (config infra, sin enlace a CU) → PASA, sin ERROR.
- `fact-checker` (subagente sonnet): **11 VERIFICADO, 0 INCORRECTO** → no bloquea. 1 **NO VERIFICABLE**
  reconocido: la tasa exacta de mutation (10%) — el verificador no re-ejecutó cosmic-ray por coste; la
  evidencia in-session (`cr-rate → 10.00`, exit 0, 2 supervivientes) se mantiene.

## Docs actualizadas

- `app/core/config.py`: docstrings de `database_url` y `embedding_dim` (intención + por qué default/gt).
- `backend/.env.example`: `DATABASE_URL`→`syntax_app`, `SYNTAX_APP_PASSWORD`, `MIGRATION_DATABASE_URL`
  (comentada, superuser). [verificado por grep].
- `backend/docker-compose.yml` (api): default `DATABASE_URL`→`syntax_app`. [verificado por grep].

## Verificación por grep (edits no cubiertos por test unit)

`.env.example:16` `DATABASE_URL=...syntax_app:syntax_app@localhost...`; `:18` `SYNTAX_APP_PASSWORD`;
`:22` `MIGRATION_DATABASE_URL` comentada con superuser `syntax`. `docker-compose.yml:41`
`DATABASE_URL: ${DATABASE_URL:-postgresql+asyncpg://syntax_app:syntax_app@db:5432/syntax}`.
