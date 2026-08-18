# Session log — backend-database-foundation-06

Tarea: Alembic async + migración inicial (extensión, 18 tablas, GRANTs, RLS) + init script del
rol `syntax_app` + fixture de test-DB + gate de drift + smoke RLS + **ADR-0016**.
Nivel: **integración** (Postgres real). Mutation: N/A (DDL/migración) salvo el helper de URL.

## Resumen

- **Init script** `docker/initdb/01-create-app-role.sh`: crea `syntax_app` (NOSUPERUSER NOBYPASSRLS
  LOGIN) idempotente; password out-of-band desde `SYNTAX_APP_PASSWORD`. Montado en compose (`db`).
- **Alembic**: `alembic.ini` (URL fuera del ini) + `alembic/env.py` (online async, `run_sync`, lee
  `MIGRATION_DATABASE_URL` vía `app/infra/db/alembic_url.py` con fallo claro) + `script.py.mako`.
- **`app/infra/db/alembic_url.py`**: `get_migration_database_url()` (lanza RuntimeError accionable si falta).
- **Migración `0001_initial_schema`**: `CREATE EXTENSION vector` → `Base.metadata.create_all` (18 tablas,
  enums, índices, FKs desde los modelos) → 3 CHECK (csat 1..5, confidence 0..1, role system) → GRANTs DML a
  `syntax_app` → RLS + `CREATE POLICY tenant_isolation` en las 7 de negocio (predicado H2 con bypass GUC +
  `current_setting(...,true)`). `downgrade` revierte RLS + `drop_all` (no toca el rol).
- **Fixtures** (`conftest.py`): `migrated_database` (session; asegura rol + crea/reutiliza `syntax_test` +
  `upgrade head`; falla claro si `db` caída), `superuser_engine`, helpers `app_test_url()`/`test_db_dsn`.
- **ADR-0016** (MADR, accepted) + `adr-index`.

## Decisiones técnicas + porqué

- **`create_all` en la migración inicial** en vez de 18 `op.create_table` a mano: garantiza schema == modelos
  por construcción (drift-test H3 no puede fallar por transcripción). Lo que Alembic no autogenera
  (extensión, GRANTs, RLS, CHECK) va como SQL explícito.
- **asyncpg en los tests, NO psycopg**: `psycopg` (psycopg3) instalado pero sin `libpq` → inutilizable. Uso
  `asyncpg` (driver runtime del proyecto) para el mantenimiento, envuelto en `asyncio.run` en contextos sync.
  **Sin dependencias nuevas**.
- **Drift con `compare_type=True`** (para cazar la dim del vector) + **exclusión de los CHECK**: los CHECK
  viven solo en la migración (decisión owner), no tienen representación en el modelo → no pueden "divergir".
  Se filtran del diff estructural. Meta-test confirma que un `Vector(768)` vs `1536` SÍ se detecta (no falso
  negativo). Alembic **agrupa** los cambios de columna en sublistas → hay que **aplanar** el diff.
- **Nombres de CHECK sin prefijo**: la `naming_convention` añade `ck_<tabla>_`, así que el nombre pasado a
  `op.create_check_constraint` es solo el sufijo (`csat_range` → `ck_ticket_csat_range`).
- **Rol fuera de Alembic** (init script + fixture idempotente): least-privilege; la migración solo GRANTs y
  asume el rol existente. La fixture crea el rol porque el init script solo corre en la 1ª init del volumen.

## Tests corridos + resultado

- TDD (integración, Postgres real): 19 tests en `tests/test_migration.py` — aplica+extensión, 18 tablas, RLS
  solo negocio (7 true / 11 false), policy tenant_isolation, drift vacío, meta-test drift (Vector dim),
  vector(1536), fallo claro si db caída, MIGRATION_DATABASE_URL ausente, upgrade idempotente,
  downgrade→upgrade + rol preservado, rol no-superuser/no-bypass, init idempotente, reutiliza syntax_test,
  GRANTs CRUD en las 18, CHECK csat/confidence (Scenario Outline). Todos verde.
- Suite completa `pytest -q` verde (172 tests). `ruff check` OK (tras `--fix` de orden de imports) ·
  `ruff format --check` OK · `mypy app` strict Success (84 files).
- **Mutation**: DDL/migración/fixtures = N/A (declarativo, M4). El único código de comportamiento,
  `alembic_url.py`, sí: cosmic-ray focalizado → **survival 0.00%** (2 mutantes KILLED).
- `/sdd-lint`: ADR-0016 MADR bien formado (estado accepted, secciones, 0 aclaraciones, enlace del índice OK).
  Sin cambios de spec/CU. PASA.
- `fact-checker` (sonnet): **9/10 VERIFICADO, 0 INCORRECTO**. 1 NO VERIFICABLE reconocido: la cifra 0% del
  mutation (el verificador no re-ejecutó cosmic-ray; la evidencia in-session — 2 mutantes KILLED, 0.00% —
  se mantiene). Verificó en la DB real que `syntax_app` es `f|f` (no superuser, no bypass). Gate limpio.

## Docs actualizadas

- **ADR-0016** (`.claude/specs/adr/0016-...md`) + `adr-index.md`. Docstrings de `env.py`, `alembic_url.py`,
  migración, fixtures. Init script comentado. `docker-compose.yml` (mount initdb + `SYNTAX_APP_PASSWORD`).
- Session log (este fichero).

## Follow-ups

- El helper de contexto RLS de `session.py` y los tests de comportamiento del aislamiento (footgun del pool
  asyncpg + bypass por transacción) → tarea 07 (traza CU-BE-03).
