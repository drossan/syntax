---
id: backend-routers-core-06
package: backend
plan: routers-core
status: pending
priority: 2
depends_on: [backend-routers-core-05]
estimate: 4h
actual:
issue:
created: 2026-08-19
updated: 2026-08-19
---

# Routers admin_tenants (+/admin/settings) · admin_users · admin_roles (+capabilities)

## Description

Los 3 routers de administración, sobre los adaptadores de identidad (04) y `deps`/RBAC (05). `admin_users`
ahora crea/invita contra el modelo multi-tenant (un email ya existente solo gana una membership nueva).
`/admin/settings` (`auto_approve`) se protege con la capacidad **nueva** `tenant.settings.manage` (ámbito
`tenant`, añadida al catálogo en la tarea 02) — el propio tenant puede gestionar su ajuste, no solo
Soporte global (coherente con ADR-0009, hallazgo de `design-review`). Spec: CU-BE-09, `rbac.md`.

## Spec

- **`admin_tenants.py`**:
  - `GET /admin/tenants` (`tenant.manage`, global) → paginado, vía `TenantRepository.list()`.
  - `POST /admin/tenants` (`tenant.manage`, global) → crea `Tenant`.
  - `GET /admin/settings` (`tenant.settings.manage`) → `TenantSettings{auto_approve}`. Gana un **query
    param `tenant_id` opcional**: si el subject accede en ámbito `tenant`, se ignora (usa `subject.
    tenant_id`); si accede en ámbito `global` (Soporte, sin tenant propio), `tenant_id` es **obligatorio**
    (422 si falta) — resuelve la ambigüedad de "a qué tenant se refiere" cuando Soporte no tiene uno
    propio (hallazgo de `scenario-coverage`).
  - `PATCH /admin/settings` (`tenant.settings.manage`, mismo `tenant_id` opcional/obligatorio) → actualiza
    `auto_approve`.
  - Toda mutación (`POST /admin/tenants`, `PATCH /admin/settings`) audita vía `AuditLogRepository.add`
    (mismo patrón que `ticket_service`, hallazgo de `scenario-coverage`).
- **`admin_users.py`**:
  - `GET /admin/users` (`user.manage`, tenant) → lista las `UserTenantMembership` del tenant del subject
    (join a `User` para email), paginado.
  - `POST /admin/users` (`user.manage`) → `UserInvite{email, roles[]}`: delega en `auth_service.invite`
    (tarea 02 — email existente → solo membership nueva; email ya `active` en ese mismo tenant → 409;
    email nuevo → `User` + membership). Asigna `roles[]` vía `UserRole` (con `tenant_id` = el tenant que
    invita). Audita `user.invited`.
  - `PATCH /admin/users/{id}` (`user.manage`) — **`{id}` es el `User.id` global** (no hay id sintético de
    membership, `user_tenant` tiene PK compuesta): el router busca la `UserTenantMembership(id,
    subject.tenant_id)`; si no existe (el `User` existe pero no tiene membership en ESTE tenant) → 404
    (mismo patrón que el aislamiento cross-tenant de tickets, nunca revela que el `User` existe en otro
    tenant). Actualiza `status` de esa membership (soft-delete = `disabled`) y/o `roles[]`; nunca toca el
    `User` global ni membresías de otros tenants. Audita `user.updated`.
- **`admin_roles.py`**:
  - `GET /admin/capabilities` (`role.manage`) → catálogo completo.
  - `GET /admin/roles` (`role.manage`) → semilla `system` + custom del tenant (vía `RoleRepository.list`).
  - `POST /admin/roles` (`role.manage`) → `rbac_service.validate_role_composition` (invariantes:
    ámbito `global` prohibido, no escalar por encima del propio composer) → `RoleRepository.add`. Audita
    `role.created`.
  - `PATCH`/`DELETE /admin/roles/{id}` (`role.manage`) → roles `system` inmutables → 403/409. Audita
    `role.updated`/`role.deleted`.

## Fuera de alcance

- `tickets`/`messages`/`kb` → tareas 07-09.
- Roles/capacidades por membership más allá de `user_role.tenant_id` existente.
- Notificar al usuario tras la invitación (más allá del email-stub que `auth_service.invite` ya hace).
- Race de `invite()` creando un `User` global nuevo (TOCTOU): aceptado que una colisión concurrente puede
  hacer que uno de los dos admins reciba `PortError` (violación de unicidad de email); sin CAS dedicado
  (ver plan, hallazgo de `scenario-coverage`, frecuencia muy baja).

## Scenarios (Gherkin)

Criterios de aceptación (Gherkin) en el caso de uso:
- [CU-BE-09 — Administración de tenants/usuarios/roles](../../../specs/backend/casos-de-uso/CU-BE-09-administracion-tenants-usuarios-roles.md)

```gherkin
Feature: administración de tenants, usuarios y roles

  Scenario: Soporte global lista todos los tenants
    Given un subject con tenant.manage en ámbito global
    When hace GET /admin/tenants
    Then recibe la página con tenants de cualquier cliente

  Scenario: un cliente sin tenant.manage no puede listar tenants
    Given un subject sin la capacidad tenant.manage
    When hace GET /admin/tenants
    Then recibe 403

  Scenario: el admin de un tenant lee su propio auto_approve
    Given un subject con tenant.settings.manage en ámbito tenant
    When hace GET /admin/settings
    Then recibe el auto_approve de SU tenant

  Scenario: el admin de un tenant actualiza su propio auto_approve
    Given un subject con tenant.settings.manage en ámbito tenant
    When hace PATCH /admin/settings con auto_approve=true
    Then el ajuste queda actualizado para su tenant

  Scenario: Soporte global consulta /admin/settings de un tenant concreto con tenant_id
    Given un subject con tenant.settings.manage en ámbito global
    When hace GET /admin/settings?tenant_id=<id> de un tenant concreto
    Then recibe el auto_approve de ESE tenant

  Scenario: Soporte global sin indicar tenant_id en /admin/settings recibe 422
    Given un subject con tenant.settings.manage en ámbito global
    When hace GET /admin/settings sin tenant_id
    Then recibe 422 (obligatorio en ámbito global)

  Scenario: invitar un email que ya existe como usuario global solo añade una membership
    Given un email que ya es User global en otro tenant, sin membership en el tenant B
    When el admin del tenant B hace POST /admin/users con ese email
    Then se crea una membership invited en el tenant B, sin nueva contraseña

  Scenario: invitar un email ya activo en el mismo tenant devuelve 409
    Given un email con membership active en el tenant B
    When el admin de B vuelve a invitarlo
    Then recibe 409

  Scenario: listar usuarios de un tenant no muestra membresías de otros tenants
    Given usuarios con membresías en los tenants A y B
    When el admin de A hace GET /admin/users
    Then solo ve las membresías del tenant A

  Scenario: listar usuarios de un tenant sin ninguno da una página vacía
    Given un tenant sin ninguna UserTenantMembership
    When su admin hace GET /admin/users
    Then recibe 200 con Page{items: [], total: 0}

  Scenario: deshabilitar un usuario es soft-delete de SU membership
    Given un usuario con membership active en el tenant A y otra active en el tenant B
    When el admin de A hace PATCH /admin/users/{id} con status=disabled
    Then la membership de A pasa a disabled y la de B sigue active

  Scenario: PATCH /admin/users/{id} sobre un User real sin membership en ese tenant da 404
    Given un User global que existe pero SIN membership en el tenant del admin
    When ese admin hace PATCH /admin/users/{id} con ese User.id
    Then recibe 404 (no revela que el User existe en otro tenant)

  Scenario: catálogo de capacidades es accesible con role.manage
    Given un subject con role.manage
    When hace GET /admin/capabilities
    Then recibe el catálogo completo de capacidades

  Scenario: crear un rol custom con capabilities vacías es válido
    Given un admin de tenant componiendo un rol
    When envía POST /admin/roles con capabilities=[]
    Then se crea el rol (sin capacidades asignadas todavía)

  Scenario: crear un rol custom con ámbito global se rechaza
    Given un admin de tenant componiendo un rol custom
    When intenta conceder una capacidad en ámbito global
    Then se rechaza (422, invariante de rbac_service)

  Scenario: editar un rol system se rechaza
    Given un rol de kind system
    When se intenta hacer PATCH sobre él
    Then se rechaza (403 o 409, inmutable)

  Scenario: cada mutación admin queda auditada
    Given un admin invitando un usuario, cambiando un rol, o creando un tenant
    When la operación se completa
    Then existe una entrada en AuditLogRepository con la acción y el actor
```

## Provides

Routers `admin_tenants`, `admin_users`, `admin_roles` montados en `/api/v1`, incl. `/admin/settings`.

## Definition of Done

- [ ] Tests escritos ANTES de la implementación (Red → Green → Refactor).
- [ ] Cada escenario tiene al menos un test de integración.
- [ ] Todos los tests en verde (`make test`).
- [ ] `Provides` disponible; sin lógica de negocio en el router (delega en `rbac_service`/adaptadores).
- [ ] `ruff check` (+`S`) + `ruff format --check` + `mypy` strict OK.
- [ ] Gate de mutation `cosmic-ray` (`break: 80`) sobre los 3 routers.
- [ ] Gate `/sdd-lint` sin ERROR (CU-BE-09 Gherkin bien formado, enlace válido).
- [ ] Gate de `fact-checker`.
- [ ] Documentación: docstrings (por qué `tenant.settings.manage` es de ámbito tenant, no global); session
  log con la traza a CU-BE-09.
