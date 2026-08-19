# Session log — backend-routers-core-01

Tarea: migración Alembic `0002` (identidad multi-tenant: `user` global + `user_tenant` +
`refresh_session.tenant_id` + `tenant.auto_approve`) + entidades de dominio. Nivel: integración
(Postgres real). Fusionada en la misma sesión con `backend-routers-core-02` (ver más abajo, "Decisión:
fusión con la tarea 02").

## Entradas

- 2026-08-19 — Arranque. Tarea 01 `active`. Antes de tocar código: commit del scaffolding del plan
  (frontmatter movidos a `active/`/`pending/`, sin commitear todavía).

## Resumen

`app/infra/db/models/identity.py` + `app/domain/entities/identity.py`: `User` pasa a ser identidad
**global** (sin `tenant_id`/`status` propios; `email` único global); nueva entidad/modelo
`UserTenantMembership`/`UserTenant` (`user_id`, `tenant_id`, `status`, `created_at`, PK compuesta);
`RefreshSession` gana `tenant_id`; `Tenant` gana `auto_approve: bool`. Migración
`alembic/versions/0002_identity_multi_tenant.py` (`down_revision="0001"`) aplica los ALTER/CREATE
correspondientes, con `downgrade()` simétrico.

## Decisiones técnicas + porqué

- **Fusión con la tarea 02 (decisión del owner, antes de empezar).** Cambiar `User`/`RefreshSession` en
  el dominio rompe `auth_service.py`/`test_auth_service.py` (usan `User.tenant_id`/`User.status` en ~8
  sitios), que la tarea 01 declara explícitamente fuera de alcance — y el fix real necesita el puerto
  `UserTenantMembershipRepository`, que es de la tarea 04. Con la DoD de 01 exigiendo "todos los tests en
  verde", cerrar 01 sola habría dejado el repo roto hasta cerrar 02. Se preguntó al owner: eligió fusionar
  01+02 en una sola sesión de trabajo (ambas P1, misma rama) en vez de aceptar la rotura transitoria o
  enmascararla con `xfail`.
- **Bug de arquitectura descubierto: la migración `0001` (plan cerrado `database-foundation`) NO estaba
  congelada.** Su `upgrade()`/`downgrade()` llamaban a `Base.metadata.create_all()`/`drop_all()` — es
  decir, leían los modelos ORM **en vivo**. Al editar `identity.py` para esta tarea, `0001` habría
  generado directamente el esquema NUEVO en cualquier `upgrade head` desde cero, dejando a `0002` sin
  nada real que alterar (verificado: `drop_constraint("fk_user_tenant_id_tenant", ...)` fallaba porque
  esa constraint nunca llegaba a crearse). Presentadas 3 opciones al owner (congelar 0001 / guards de
  idempotencia en 0002 / squash 0001+0002), eligió **congelar 0001**: se reescribió para definir su
  propio `sa.MetaData()` con las 18 tablas explícitas (mismo `NAMING_CONVENTION`, mismos enums vía
  `app.infra.db.models.enums` — módulo de solo-valores-contrato, no de estructura), reproduciendo el
  shape histórico exacto (con `user.tenant_id`/`status`, sin `user_tenant`) sin importar
  `app.infra.db.models`/`Base`. `0002` pasa a ser un ALTER real y con sentido para siempre.
- **Enums reusados en la migración congelada vía `app.infra.db.models.enums`, no reimplementados a
  mano.** Es un módulo de VALORES (contrato de `data-model.md §3`, no de estructura de tablas): no está
  sujeto al mismo riesgo de acoplamiento que las clases de tabla, y evita transcribir a mano los 17
  valores de `kb_domain` (fuente de errores tipográficos).
- **`user_tenant.status` en `0002` referencia el enum `user_status` ya existente con
  `postgresql.ENUM(..., create_type=False)`** — evita que Alembic intente re-`CREATE TYPE` un tipo que
  `0001` ya creó.
- **Nombres de constraints explícitos** (`fk_user_tenant_id_tenant`, `uq_user_tenant_id`,
  `pk_user_tenant`, etc.) siguiendo el `NAMING_CONVENTION` del repo — necesario porque los `op.*` de
  Alembic no aplican la convención de `Base.metadata` automáticamente; sin nombres explícitos, Postgres
  autogenera nombres distintos y el `drop_constraint` de la tarea 02/futuras migraciones no los
  encontraría.

## Tests corridos + resultado

- `tests/test_migration_identity_multi_tenant.py` (nuevo, 11 escenarios 1:1 con el Gherkin de la tarea):
  **11 tests**, verdes.
- `tests/test_migration.py` (de `database-foundation`, no debía romperse): **verde** tras congelar 0001
  (se limpió/recreó `syntax_test` una vez para eliminar un estado intermedio corrupto de cuando 0001
  todavía no estaba congelada).
- `tests/test_models_identity.py`: actualizado (unique de `User` a solo `email`; `UserTenant` añadida a
  las tablas/modelos de identidad; tests de FK/cascada/enum re-apuntados a `UserTenant`/
  `RefreshSession.tenant_id`/`Tenant.auto_approve`).
- Suite completa del backend: **verde** (ver detalle de conteo y gates de mutation/ruff/mypy en el
  session log de la tarea 02, que cierra la sesión conjunta).
- Gate de mutation: **N/A documentado** para esta tarea (migración + entidades declarativas, mismo
  criterio M4 de `database-foundation`) — el gate de mutation real de la sesión fusionada corrió sobre
  `auth_service.py`/`security.py` (tarea 02).
- `/sdd-lint`: N/A para esta tarea (sin cambios de spec/CU aquí — los tocó la tarea 02).

## Docs actualizadas

- Docstrings de `Tenant`/`User`/`UserTenant`/`RefreshSession` (ORM y dominio) explicando el porqué del
  rediseño (identidad global, una sola contraseña compartida).
- Docstring de cabecera de `0001_initial_schema.py` explicando la congelación (footgun descubierto, por
  qué y cómo se resolvió) y de `0002_identity_multi_tenant.py`.
- Este session log.

## Ficheros / commits

- `backend/app/infra/db/models/identity.py`, `backend/app/infra/db/models/__init__.py`,
  `backend/app/domain/entities/identity.py`.
- `backend/alembic/versions/0001_initial_schema.py` (reescrito, congelado).
- `backend/alembic/versions/0002_identity_multi_tenant.py` (nuevo).
- `backend/tests/test_models_identity.py` (actualizado).
- `backend/tests/test_migration_identity_multi_tenant.py` (nuevo).
- Commit conjunto con la tarea 02 (ver su session log) — ambas cierran en el mismo commit lógico de la
  rama `plan/backend/routers-core` por la fusión decidida al arrancar.

## Tiempo real

- `estimate: 3h` → real: parte de una sesión conjunta con la tarea 02 (`estimate: 4h`); no se llevó
  tiempo por separado. Ver retro en el cierre del plan.

## Follow-ups

- Ninguno propio de esta tarea; los huecos nombrados (backfill N/A, roles por membership, etc.) ya
  estaban declarados en el plan.
