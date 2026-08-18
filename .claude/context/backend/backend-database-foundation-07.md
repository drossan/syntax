# Session log — backend-database-foundation-07

Tarea: `app/infra/db/session.py` — engine/sessionmaker async (rol `syntax_app`) + helper de
contexto RLS (`tenant_scope`/`global_scope`) + tests de aislamiento (footgun). Nivel:
**integración obligatoria** (Postgres real como `syntax_app`). Mutation: código de comportamiento.

## Traza SDD

Infra de aislamiento → traza a **CU-BE-03** (autorización y aislamiento tenant) +
**FR-013/FR-014/FR-015** (aislamiento multi-tenant, escritura acotada) + **NFR-002**. No es 1:1: el CU
completo necesita endpoints/RBAC (plan 10). ADR-0016 (rol dedicado + GUC de bypass) es el porqué.

## Resumen

`session.py` deja de ser doc-only:
- `get_engine()`/`get_sessionmaker()` perezosos (sin efectos en import); `async_sessionmaker(
  expire_on_commit=False)`; `get_session()` cede `AsyncSession` (dependency de 09).
- `_coerce_tenant_uuid()`: valida UUID → **ValueError** controlado (no error crudo de PG).
- `tenant_scope(session, tenant_id)`: abre transacción + `SELECT set_config('app.tenant_id', :tid, true)`
  (bind-safe; `SET LOCAL` no admite params). Alcance transaccional → se descarta al commit/rollback.
- `global_scope(session)`: `set_config('app.bypass_rls', 'on', true)` (ámbito global de Soporte).

## Decisiones técnicas + porqué

- **`set_config(..., true)` (transaccional)** en vez de `SET` de sesión: el pool asyncpg reutiliza
  conexiones; un `SET` de sesión arrastraría el tenant a la siguiente request (footgun) → fuga
  cross-tenant. El alcance transaccional se descarta al cerrar la transacción → sin fuga.
- **Fix de correctness en el predicado RLS (migración 0001)**: tras un `set_config(...,true)` previo, una
  conexión del pool reutilizada devuelve el GUC como **`''` (cadena vacía)**, NO NULL → `''::uuid` LANZA
  (rompía el fail-closed tras reúso). Corregido a `NULLIF(current_setting('app.tenant_id', true), '')::uuid`
  → `''`→NULL→0 filas (fail-closed correcto). Refina el predicado H2 de la tarea 06.
- **Validación de UUID en Python** antes de tocar la DB: `tenant_id` malformado → ValueError, no una
  excepción cruda de Postgres (scenario-coverage).
- **`app_engine` con `pool_size=1`** en los tests: fuerza el reúso de la MISMA conexión → hace el footgun
  observable; con filas **commiteadas** + `TRUNCATE` (H5), no rollback envolvente (que lo haría vacuo).

## Tests corridos + resultado

- TDD (integración, `syntax_app`): 15 tests en `tests/test_session.py` — aislamiento lectura, footgun de
  pool (sin fuga tras contexto A), bypass global ve ambos, bypass no se arrastra, fail-closed sin GUC,
  KB no filtrada, escritura acotada (WITH CHECK ok), escritura cross-tenant rechazada (DBAPIError),
  UUID malformado (ValueError), contexto descartado en ROLLBACK, Scenario Outline (solo `'on'` bypassa),
  sessionmaker expire_on_commit=False, get_engine lazy singleton.
- Suite completa `pytest -q` verde (187 tests). `ruff check` OK · `ruff format --check` OK · `mypy app`
  strict Success (84 files).
- **Mutation** `cosmic-ray` sobre `session.py` (break 80): **survival 3.03%** (33 mutantes, 1 superviviente
  = `pool_pre_ping=True→False`, flag de pool invisible al comportamiento; la lógica RLS queda 100% muerta).
- `/sdd-lint`: sin cambios de artefactos SDD; traza a CU-BE-03 (existe) documentada aquí. Corpus mecánico
  limpio → PASA.
- `fact-checker` (sonnet): **9/9 VERIFICADO, 0 INCORRECTO**. 1 NO VERIFICABLE reconocido: la cifra 3.03% del
  mutation (no re-ejecutó cosmic-ray; la evidencia in-session — 33 mutantes, 1 superviviente `pool_pre_ping`
  — se mantiene). Confirmó el `NULLIF` del predicado y el test del footgun (pool_size=1, sin fuga). Gate limpio.

## Docs actualizadas

- Docstrings de `session.py` (intención, footgun, params, `raises ValueError`). Comentario del predicado
  RLS en la migración `0001` explicando el `NULLIF`. Session log (este fichero).

## Follow-ups

- `deps.get_db_session` + `/health/ready` → tarea 09. `BaseRepository` (filtro app-level) → tarea 08.
- Autorización de quién puede usar `global_scope` (RBAC) → plan 10.
