# 0016. RLS multi-tenant vía rol dedicado no-superuser + GUC de bypass por transacción

- **Estado**: accepted
- **Fecha**: 2026-08-16
- **Decisores**: Owner.
- **Contexto SDD**: refina [ADR-0006](./0006-aislamiento-multi-tenant-app-level-mas-rls.md) (aislamiento
  multi-tenant app-level + RLS día 1). Materializa FR-013/FR-014/FR-015, NFR-002. Traza CU-BE-03.

## Contexto y planteamiento del problema

ADR-0006 fijó **RLS día 1** en las tablas de negocio con el patrón `SET app.tenant_id` +
`USING (tenant_id = current_setting('app.tenant_id')::uuid)`. Al materializarlo aparecieron dos huecos
que el grilling/design-review del plan `database-foundation` marcaron como **correctness-blocking**:

1. **El rol de la app era superusuario.** `POSTGRES_USER` (`syntax`) es superusuario y **salta RLS** por
   diseño de Postgres (`rolsuper`/`rolbypassrls`). Si la API conecta como `syntax`, **las políticas no
   filtran nada** — el aislamiento sería una falsa sensación de seguridad.
2. **El ámbito `global` de Soporte** (cross-tenant, 02 §5) necesita operar sin el filtro de tenant, pero el
   predicado original no tenía forma de bypass controlado, y `current_setting('app.tenant_id')` de 1 arg
   **lanza** si el GUC no está fijado (en vez de fail-closed).

## Decision drivers

- El aislamiento debe **aplicar de verdad** en runtime (no depender de disciplina de código).
- **Least-privilege**: la API nunca arranca con credenciales superuser.
- El ámbito `global` debe ser **explícito y acotado por transacción** (no una puerta global permanente).
- **Fail-closed**: si falta el contexto de tenant, no se ven filas (no se lanza ni se abre).

## Opciones consideradas

- **Opción 1** — Rol runtime dedicado `syntax_app` **NOSUPERUSER NOBYPASSRLS** + policy con **GUC de bypass
  por transacción** (`app.bypass_rls`) y `current_setting(..., true)` (2 args, `missing_ok`).
- **Opción 2** — Seguir con el superusuario y añadir `FORCE ROW LEVEL SECURITY` en cada tabla.
  `FORCE RLS` hace que RLS aplique **al propietario** de la tabla, pero **no** al superusuario (sigue
  saltándola) — no resuelve el hueco (1).
- **Opción 3** — Aislamiento solo app-level (WHERE tenant_id en cada query), sin RLS. Frágil: un olvido en
  una sola query filtra datos entre tenants; sin defensa en profundidad.

## Resultado de la decisión

Elegida: **Opción 1**.

- **Rol `syntax_app`** (`NOSUPERUSER NOBYPASSRLS LOGIN`) creado **fuera de Alembic** — en un init script
  (`docker-entrypoint-initdb.d`) en local y un runbook de ops en prod; su password se fija **out-of-band**
  (`ALTER ROLE ... PASSWORD` desde env, nunca en el repo). La API conecta con `DATABASE_URL` → `syntax_app`;
  el superusuario queda **solo** para migraciones/bootstrap (`MIGRATION_DATABASE_URL`, no en `Settings`).
- **Migración `0001`**: `ENABLE ROW LEVEL SECURITY` + `CREATE POLICY tenant_isolation` en las **7 tablas de
  negocio** con el predicado exacto (idéntico en `USING` y `WITH CHECK`):

  ```sql
  current_setting('app.bypass_rls', true) = 'on'
  OR tenant_id = current_setting('app.tenant_id', true)::uuid
  ```

  La forma de **2 args** (`missing_ok = true`) devuelve `NULL` si el GUC no está fijado → **fail-closed**
  (ninguna fila) en vez de lanzar. El `WITH CHECK` idéntico impide **escribir** filas de otro tenant.
- **Ámbito `global`** (Soporte): se activa `SET LOCAL app.bypass_rls = 'on'` (o `set_config(..., true)`) **por
  transacción**, de modo que el bypass no sobrevive a la conexión reutilizada del pool. El cableado con RBAC
  (quién puede activarlo) es del plan de dominio (10).
- **Sin `FORCE RLS`**: el rol `syntax_app` **no es propietario** de las tablas (lo es el superusuario que
  migra), así que RLS ya le aplica; `FORCE` es innecesario aquí.

### Confirmación

Migración `backend/alembic/versions/0001_initial_schema.py` + smoke de invariante RLS
(`relrowsecurity` = true en las 7 de negocio, false en KB/identidad; policy `tenant_isolation` presente) y
tests de que `syntax_app` **no** es superusuario ni bypassa RLS — `backend/tests/test_migration.py`
(tarea `backend-database-foundation-06`). Los tests de **comportamiento** del aislamiento (footgun del pool
asyncpg, bypass por transacción) llegan en la tarea 07 (`session.py`), con integración obligatoria.

## Consecuencias

- **Buenas**: el aislamiento aplica en runtime aunque una query olvide el `WHERE tenant_id` (defensa en
  profundidad); least-privilege (la API no tiene credenciales superuser); bypass explícito y acotado por
  transacción; fail-closed ante contexto ausente.
- **Malas / coste**: el rol se gestiona **fuera de Alembic** (un paso de ops extra; la migración solo hace
  GRANTs y asume el rol existente); el footgun `SET app.tenant_id` sobre el pool asyncpg **exige tests de
  integración** (no cazable con mocks) — se materializa en 07; el `SET LOCAL` no admite bind params, así que
  el helper de contexto usará `set_config(..., true)` + validación de UUID (07).
- **Fuera de alcance**: quién puede activar el bypass `global` (autorización RBAC → plan 10); rotación de la
  password del rol (runbook de ops).

## Pros y contras de las opciones

- **Opción 1**: 👍 RLS aplica de verdad, least-privilege, bypass acotado, fail-closed · 👎 rol fuera de
  Alembic (paso de ops), footgun del pool exige integración.
- **Opción 2**: 👍 mínimo cambio · 👎 **no resuelve** el hueco (el superusuario sigue saltando RLS aun con
  `FORCE`).
- **Opción 3**: 👍 sin RLS que gestionar · 👎 sin defensa en profundidad; un solo olvido filtra entre tenants.
