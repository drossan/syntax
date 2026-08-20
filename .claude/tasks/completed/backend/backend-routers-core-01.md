---
id: backend-routers-core-01
package: backend
plan: routers-core
status: done
priority: 1
depends_on: []
estimate: 3h
actual: fusionada con backend-routers-core-02 en una sesión conjunta (ver session log); sin desglose de tiempo por separado
issue:
created: 2026-08-19
updated: 2026-08-19
---

# Migración identidad multi-tenant (user global + user_tenant + refresh_session.tenant_id + tenant.auto_approve)

## Description

Rediseña el modelo de identidad para soportar que **un mismo usuario pertenezca a varios tenants con una
sola contraseña** (decisión de `grilling`, confirmada tras `design-review`: el owner quiere identidad
global, no cuentas separadas por tenant). Migración Alembic nueva **sobre** el esquema ya migrado de
`database-foundation` (sin backfill: no hay datos de producción). Base para todo lo demás del plan
(`auth_service`, `deps`, adaptadores). Spec: `data-model.md` (a actualizar en la tarea 02, no aquí — esta
tarea es solo el cambio de esquema + entidades de dominio).

## Spec

- **Migración Alembic nueva** (`alembic/versions/000X_...`), revisión sobre `0001_initial_schema`:
  - `user`: DROP columna `tenant_id` (y su FK), DROP columna `status`; DROP `UniqueConstraint(tenant_id,
    email)`; ADD `UniqueConstraint(email)` (único global).
  - `user_tenant` (tabla nueva): `id` (PK uuid) o PK compuesta `(user_id, tenant_id)` — elegir PK compuesta
    (no hace falta un id sintético, la relación es la propia clave); `user_id` (FK `user.id`, CASCADE);
    `tenant_id` (FK `tenant.id`, RESTRICT); `status` (mismo enum `user_status`: invited/active/disabled);
    `created_at` (`TimestampMixin`-like, server_default now()). Índice por `user_id` (listar membresías de
    un usuario) y por `tenant_id` (listar usuarios de un tenant, lo usa `admin_users`).
  - `refresh_session`: ADD columna `tenant_id` (FK `tenant.id`, RESTRICT, NOT NULL) — una sesión de
    refresh es de un tenant concreto (el elegido en `select_tenant`).
  - `tenant`: ADD columna `auto_approve` (`bool`, `NOT NULL DEFAULT false`).
  - `downgrade()` revierte exactamente lo anterior (recompone `user.tenant_id`/`status`/unique compuesto,
    dropea `user_tenant`, dropea columnas nuevas). Sin backfill de datos en ningún sentido (DB de test/dev
    vacía o con fixtures reproducibles, no producción).
- **`app/infra/db/models/identity.py`**: `User` pierde `tenant_id`/`status`; unique solo en `email`. Nueva
  clase ORM `UserTenant` (tabla `user_tenant`). `RefreshSession` gana `tenant_id: Mapped[uuid.UUID]`.
  `Tenant` gana `auto_approve: Mapped[bool]`.
- **`app/domain/entities/identity.py`**: `User` (Pydantic) pierde `tenant_id`/`status`. Nueva entidad
  `UserTenantMembership{user_id, tenant_id, status: UserStatus, created_at}`. `RefreshSession` gana
  `tenant_id: uuid.UUID`. `Tenant` gana `auto_approve: bool = False`.
- **Gate de drift** (mismo patrón que `database-foundation` 06): `compare_metadata(Base.metadata,
  syntax_test)` vacío tras la migración nueva.
- Ningún puerto/servicio se toca aquí (eso es la tarea 02) — esta tarea es **solo** esquema + entidades.

## Fuera de alcance

- `auth_service`, `deps`, contrato, `rbac.md`, CU-BE-01, capacidad `tenant.settings.manage` → tarea 02.
- Adaptadores SQLAlchemy de los puertos (`UserRepository`, `UserTenantMembershipRepository`, etc.) → 04.
- Backfill de datos reales — no aplica (repo pre-lanzamiento, sin datos de producción).
- Roles/capacidades por membership más allá de `user_role.tenant_id` (ya existente, sin cambios aquí).

## Scenarios (Gherkin)

<!-- SDD: migración/entidades → Gherkin LOCAL, "sin cambios de spec/CU" (el CU se actualiza en la tarea
     02). Integración contra Postgres real (mismo patrón que database-foundation 06). -->

```gherkin
Feature: migración de identidad a modelo multi-tenant global

  Scenario: la migración aplica limpia sobre la DB ya migrada de database-foundation
    Given una DB de test migrada con el esquema 0001_initial_schema
    When se ejecuta alembic upgrade head
    Then termina sin error

  Scenario: user ya no tiene tenant_id ni status, y el email es único global
    Given la DB migrada con la revisión nueva
    When se inspecciona la tabla user
    Then no existen las columnas tenant_id ni status And existe un UniqueConstraint sobre email

  Scenario: user_tenant existe con status por membership
    Given la DB migrada
    When se inserta una fila user_tenant(user_id, tenant_id, status='active')
    Then se persiste sin error y es consultable por user_id o por tenant_id

  Scenario: un usuario no puede tener dos membresías al mismo tenant
    Given un usuario con una membership activa en el tenant A
    When se intenta insertar una segunda membership del mismo usuario al mismo tenant A
    Then falla por la unicidad (user_id, tenant_id)

  Scenario: el email es único a nivel global, no por tenant
    Given un User ya existente con un email concreto
    When se intenta insertar otro User con ese mismo email
    Then falla por el UniqueConstraint(email) global (antes habría sido válido en otro tenant)

  Scenario: borrar un usuario elimina en cascada sus membresías
    Given un usuario con una o más filas user_tenant
    When se borra ese User
    Then sus filas user_tenant desaparecen (ON DELETE CASCADE)

  Scenario: un tenant con membresías o sesiones no puede borrarse
    Given un tenant con al menos una fila user_tenant o refresh_session
    When se intenta borrar ese tenant
    Then falla (ON DELETE RESTRICT)

  Scenario: refresh_session exige tenant_id
    Given la DB migrada
    When se inserta una refresh_session sin tenant_id
    Then falla (NOT NULL)

  Scenario: tenant.auto_approve por defecto es false
    Given un tenant insertado sin especificar auto_approve
    When se lee la fila
    Then auto_approve es false

  Scenario: downgrade revierte la migración limpiamente
    Given la DB migrada con la revisión nueva
    When se ejecuta alembic downgrade -1
    Then user recupera tenant_id/status/unique compuesto, y user_tenant/refresh_session.tenant_id/
      tenant.auto_approve desaparecen

  Scenario: los modelos no divergen del schema migrado (drift)
    Given la DB migrada con la revisión nueva y Base.metadata actualizado
    When se ejecuta compare_metadata
    Then el diff está vacío
```

## Provides

`app/infra/db/models/identity.py` (esquema `user`/`user_tenant`/`refresh_session`/`tenant` actualizado) +
`app/domain/entities/identity.py` (`User` sin tenant/status, `UserTenantMembership` nueva,
`RefreshSession.tenant_id`, `Tenant.auto_approve`) + la migración aplicada en `syntax_test`. Consumido por
la tarea 02 (`auth_service`) y la 04 (adaptadores).

## Definition of Done

- [x] Tests escritos ANTES de la implementación (Red → Green → Refactor).
- [x] Cada escenario tiene al menos un test de integración (Postgres real).
- [x] Todos los tests en verde (`make test`) — 392 tests, suite completa del backend.
- [x] `Provides` disponible; `compare_metadata` da diff vacío; `downgrade` probado.
- [x] `ruff check` (+`S`) + `ruff format --check` + `mypy` strict OK.
- [x] Gate de mutation: **N/A documentado** (migración + entidades declarativas, mismo criterio M4 de
  `database-foundation`).
- [x] Gate `/sdd-lint`: N/A para esta tarea (sin cambios de spec/CU aquí — los tocó la 02, con su propio
  gate).
- [x] Gate de `fact-checker`: 11/12 afirmaciones VERIFICADAS, 1 NO VERIFICABLE reconocida (mutation
  session.sqlite gitignored, borrada tras el cierre).
- [x] Documentación: docstrings de las entidades nuevas/modificadas; session log con la traza a esta
  migración y su relación con `database-foundation` (revisión sobre la que aplica) — incl. el hallazgo
  de que `0001` no estaba congelada (bug de arquitectura de `database-foundation`, corregido aquí con
  aprobación del owner).

> **Nota de cierre**: fusionada con `backend-routers-core-02` en una sola sesión de trabajo (decisión
> del owner) porque el cambio de entidades de esta tarea rompía `auth_service`/`test_auth_service.py`
> de forma irreparable dentro del alcance declarado de esta tarea sola. Ver el Registro de cambios del
> plan y los session logs de ambas tareas.
