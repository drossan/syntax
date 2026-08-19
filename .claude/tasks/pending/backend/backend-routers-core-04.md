---
id: backend-routers-core-04
package: backend
plan: routers-core
status: pending
priority: 1
depends_on: [backend-routers-core-01, backend-routers-core-03]
estimate: 4h
actual:
issue:
created: 2026-08-19
updated: 2026-08-19
---

# Adaptadores SQLAlchemy de identidad (Tenant, User, UserTenantMembership, Role, RefreshSession, AuthToken)

## Description

Primeros adaptadores REALES de los puertos definidos en `domain-services` (plan 10), contra las entidades
nuevas de la tarea 01. `BaseRepository` (marcado "especulativo" en su propio docstring) **no aplica
directo**: `Tenant`/`User`/`UserTenant`/`Role`/`Capability` no llevan `TenantMixin` (cross-tenant por
diseño, RBAC gobierna su aislamiento, no RLS) — necesitan consultas propias, no el genérico. Nivel de test:
**integración** contra Postgres real (primera vez que se ejercita el CAS de `rotate_if_active` con DB de
verdad, no un fake). Spec: `app/domain/ports/repositories.py` (contratos ya cerrados, se implementan aquí;
`RoleRepository` se **amplía** con `list`/`update`/`delete`, que el plan 10 no necesitaba).

## Spec

- **`app/domain/ports/repositories.py`**: añade `UserTenantMembershipRepository` (Protocol nuevo:
  `get(user_id, tenant_id)`, `add`, `update`, `list_by_user(user_id)`, `list_by_tenant(tenant_id)` con
  paginación); amplía `RoleRepository` con `list(tenant_id) -> list[Role]` (semilla `system` + custom del
  tenant), `update(role) -> Role`, `delete(role_id) -> bool` (roles `system` inmutables — el rechazo es de
  `rbac_service`/`validate_role_composition`, el repo solo persiste); **cambia la firma** de
  `effective_capabilities(user_id) -> effective_capabilities(user_id, tenant_id)` (hallazgo de
  `scenario-coverage`: sin acotar por tenant, un usuario con roles distintos en dos tenants —ya soportado
  por `user_role.tenant_id`— filtraría capacidades de un tenant a la sesión activa en otro; fix de
  seguridad, no ampliación discrecional); amplía `TenantRepository` con `list()` paginado y expone
  `auto_approve`/`status` en `get`/`add`/`update`.
- **`app/infra/db/repositories/tenant.py`**: adaptador de `TenantRepository` — consulta directa
  (`select(Tenant)`), sin filtro de tenant (es la tabla raíz).
- **`app/infra/db/repositories/user.py`**: adaptador de `UserRepository` (`get`, `get_by_email` ahora
  **sin** `tenant_id`, `add`, `update`) — email único global.
- **`app/infra/db/repositories/user_tenant.py`**: adaptador de `UserTenantMembershipRepository`.
- **`app/infra/db/repositories/role.py`**: adaptador de `RoleRepository` (incl. `effective_capabilities`
  vía join `user_role`→`role_capability`→`capability`, ya especificado en el puerto; + `list`/`update`/
  `delete` nuevos).
- **`app/infra/db/repositories/refresh_session.py`**: adaptador de `RefreshSessionRepository` — el CAS
  `rotate_if_active` se implementa como **una sola sentencia** `UPDATE ... WHERE status='active' AND
  token_hash=:hash RETURNING ...` (no `get`+`if`+`update` en pasos separados, exigido por el contrato del
  puerto desde `domain-services`); incluye `tenant_id` en la fila creada.
- **`app/infra/db/repositories/auth_token.py`**: adaptador de `AuthTokenRepository`.
- Todos envuelven excepciones de infra (`IntegrityError`, etc.) en `app.domain.errors.PortError`
  (`raise ... from exc`, nunca dejan pasar la excepción cruda de SQLAlchemy).

## Fuera de alcance

- `TicketRepository`/`MessageRepository` → tarea 07/08 (son de negocio, no de identidad).
- `deps.py`/routers que usan estos adaptadores → tarea 05.
- Migración/entidades → ya cerradas en la 01.

## Scenarios (Gherkin)

<!-- SDD: adaptadores de infra sin comportamiento de negocio propio (implementan un contrato ya
     especificado en domain-services) → Gherkin LOCAL, "sin cambios de spec/CU". El comportamiento que
     SÍ es nuevo (list/update/delete de RoleRepository) se cubre igualmente en Gherkin local: es
     ampliación de un puerto de infra, no un caso de uso nuevo del producto. -->

```gherkin
Feature: adaptadores SQLAlchemy de identidad respetan el contrato del puerto

  Scenario: UserRepository.get_by_email busca sin filtrar por tenant
    Given un User global con un email conocido
    When se llama a get_by_email(email)
    Then devuelve ese User sin necesidad de indicar ningún tenant

  Scenario: UserTenantMembershipRepository.list_by_user devuelve solo las membresías de ese usuario
    Given dos usuarios con membresías en tenants distintos
    When se listan las membresías de uno de ellos
    Then solo aparecen las suyas, no las del otro usuario

  Scenario: RefreshSessionRepository.rotate_if_active rota atómicamente una sesión activa
    Given una refresh_session con status active
    When se llama a rotate_if_active con su hash
    Then devuelve Rotated con una nueva sesión, y la original queda rotated

  Scenario: RefreshSessionRepository.rotate_if_active detecta reuso
    Given una refresh_session ya rotated
    When se llama a rotate_if_active con su hash (el ya usado)
    Then devuelve Reused(family_id), sin crear una sesión nueva

  Scenario: RefreshSessionRepository.rotate_if_active con un hash que no existe lanza NotFound
    Given ningún refresh_session con un hash concreto
    When se llama a rotate_if_active con ese hash
    Then lanza NotFound

  Scenario: rotate_if_active es atómico bajo concurrencia real
    Given una refresh_session active
    When se lanzan 2 llamadas concurrentes a rotate_if_active con el mismo token_hash
    Then solo una obtiene Rotated y la otra ve Reused o NotFound de forma consistente, nunca las dos Rotated

  Scenario: RoleRepository.list devuelve la semilla system + los custom del tenant
    Given roles system (tenant_id NULL) y un rol custom de un tenant
    When se listan los roles de ese tenant
    Then aparecen ambos grupos

  Scenario: RoleRepository.update persiste los cambios de un rol custom
    Given un rol custom existente
    When se actualiza su descripción o sus capacidades
    Then el cambio es visible en una lectura posterior

  Scenario: RoleRepository.delete sobre un rol custom lo borra
    Given un rol custom sin asignaciones activas
    When se borra
    Then deja de aparecer en list()

  Scenario: TenantRepository.list pagina los tenants
    Given más tenants que un page_size
    When se listan con page/page_size
    Then devuelve la página correspondiente y el total correcto

  Scenario: effective_capabilities se acota al tenant de la sesión
    Given un usuario con un rol en el tenant A y un rol distinto en el tenant B
    When se resuelven sus capacidades para el tenant A
    Then solo aparecen las capacidades del rol asignado en A, nunca las de B

  Scenario: insertar un email duplicado se envuelve en PortError
    Given un User global con un email ya existente
    When se intenta añadir otro User con ese mismo email
    Then la violación de unicidad llega como PortError, no como IntegrityError cruda

  Scenario: un fallo de infra se envuelve en PortError
    Given una operación de un adaptador que dispara una excepción de SQLAlchemy (p.ej. conexión caída)
    When se ejecuta esa operación
    Then la excepción que llega al llamante es PortError, no la excepción cruda
```

## Provides

Adaptadores concretos de `TenantRepository`, `UserRepository`, `UserTenantMembershipRepository` (nuevo),
`RoleRepository` (con `list`/`update`/`delete`), `RefreshSessionRepository`, `AuthTokenRepository` en
`app.infra.db.repositories.*`. Consumido por la tarea 05 (router `auth` + `deps`) y la 06 (admin).

## Definition of Done

- [ ] Tests escritos ANTES de la implementación (Red → Green → Refactor).
- [ ] Cada escenario tiene al menos un test de integración (Postgres real, `docker compose up -d db`).
- [ ] Todos los tests en verde (`make test`).
- [ ] `Provides` disponible; ningún adaptador deja pasar una excepción de infra cruda.
- [ ] `ruff check` (+`S`) + `ruff format --check` + `mypy` strict OK.
- [ ] Gate de mutation `cosmic-ray` (`break: 80`) sobre los adaptadores con lógica condicional real (CAS,
  `effective_capabilities`); los CRUD triviales pueden ser N/A documentado.
- [ ] Gate `/sdd-lint`: N/A (sin cambios de spec/CU, declarado en Scenarios).
- [ ] Gate de `fact-checker`.
- [ ] Documentación: docstrings (por qué `BaseRepository` no aplica aquí, el CAS como sentencia única);
  session log.
