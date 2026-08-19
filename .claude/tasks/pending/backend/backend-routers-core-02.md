---
id: backend-routers-core-02
package: backend
plan: routers-core
status: pending
priority: 1
depends_on: [backend-routers-core-01]
estimate: 4h
actual:
issue:
created: 2026-08-19
updated: 2026-08-19
---

# auth_service reescrito (login 2 pasos + select_tenant + change_password) + security.py + contrato/specs

## Description

Reescribe `auth_service` sobre las entidades nuevas de la tarea 01: `login()` ya no exige `tenant_id`
(no lo tiene el contrato); si el email tiene 2+ membresías `active`, emite un `identity_token` corto en
vez de tokens reales, y un `select_tenant()` nuevo cambia ese token por el `TokenResponse` de siempre.
`invite()`/`accept_invitation()` pasan a operar sobre `UserTenantMembership.status` (ya no existe
`User.status`). Añade `change_password()` (endpoint nuevo del contrato, sin implementar hasta ahora).
Sincroniza lo que el rediseño rompe fuera del código: contrato compartido con el frontend y 3 documentos
de spec — para que ningún artefacto quede desincronizado sin dueño (hallazgo de `design-review`). Spec:
FR-001..009 (ampliadas), CU-BE-01/02 (a actualizar aquí).

## Spec

- **`app/core/security.py`**: `create_access_token`/`decode_access_token` ganan un claim `purpose: str`
  (p.ej. `"access"` | `"tenant_selection"`) y `tenant_id` pasa a ser **opcional** en la firma (un
  `identity_token` no lleva tenant todavía). `decode_access_token` sigue exigiendo `sub`/`exp`; solo exige
  `tenant_id` cuando `purpose == "access"`.
- **`AuthService.login(email, password) -> LoginOutcome`** (ya no recibe `tenant_id`):
  1. Normaliza `email` a minúsculas (búsqueda y comparación case-insensitive — más crítico ahora que el
     email es clave de unicidad global, hallazgo de `scenario-coverage`).
  2. Busca el `User` global por email; si no existe o password no verifica → error genérico (igual que
     hoy, no revela existencia).
  3. Lista las `UserTenantMembership` con `status=active` **cuyo `Tenant.status != disabled`** (una
     membership activa en un tenant deshabilitado no cuenta) de ese usuario.
  4. **0 activas** (tras el filtro de tenant no-disabled) → mismo error genérico (no distingue "sin
     membership" de "credenciales inválidas").
  5. **1 activa** → emite `TokenResponse` real (access + refresh-cookie) para ese tenant, como hoy.
  6. **2+ activas** → emite `identity_token` corto (`purpose=tenant_selection`, TTL corto p.ej. 5 min, sin
     `tenant_id`, **sin** refresh-cookie, **reutilizable** dentro de su TTL — no se marca de un solo uso)
     + la lista de `(tenant_id, slug, name)` de esas membresías.
- **`AuthService.select_tenant(identity_token, tenant_id) -> AuthResult`**: decodifica el
  `identity_token` (exige `purpose=tenant_selection` — un token con otro `purpose`, p.ej. un access token
  normal, se rechaza; un token expirado también); valida que exista una `UserTenantMembership(user_id,
  tenant_id)` con `status=active` **y `Tenant.status != disabled`**; si no → error genérico (no revela si
  la membership existe en otro estado). Si válida, emite el `TokenResponse` real igual que el camino de
  1-tenant.
- **`AuthService.switch_tenant(access_token, tenant_id) -> AuthResult`** (nuevo): igual que
  `select_tenant`, pero decodifica un **access token válido** (`purpose=access`) en vez de un
  `identity_token` — permite a una sesión ya autenticada cambiar a otra de sus membresías sin repetir
  credenciales. Mismas validaciones de membership `active` + tenant no-`disabled`.
- **`invite(tenant_id, user_id_or_email)`**: si el email ya existe como `User` global, crea solo la
  `UserTenantMembership(status=invited)` para ese tenant (sin tocar su password); si ya existe una
  membership **`active`** de ese usuario en ESE MISMO tenant → `Conflict` (409, reinvitación indebida,
  mismo criterio que `invite()` sobre un usuario ya activo en `domain-services`). Si el email no existe
  como `User`, crea el `User` (sin password) + la membership `invited`. `accept_invitation(token,
  password)` fija el password del `User` global (afecta a TODAS sus membresías, es una sola contraseña) y
  activa **la membership del token** (`invited` → `active`) — el resto de membresías del usuario no se
  tocan.
- **`change_password(user_id, current_password, new_password)`** (nuevo): verifica `current_password`
  contra el `User` global; si no coincide → `Validation`; si coincide, `hash_password(new_password)`.
- **Contrato** (`.claude/specs/general/api-contract.yaml`): `User` pierde `tenant_id`/`status` como campo
  directo (pasan a `UserTenantMembership`, expuesta donde aplique — p.ej. `/admin/users` devuelve el
  status de la membership del tenant consultado, no un status global). `UserInvite`/`UserUpdate` se
  revisan igual. Login gana una respuesta alternativa (`identity_token` + `tenants[]`) documentada junto a
  `TokenResponse`; nuevos paths `POST /auth/select-tenant` y `POST /auth/switch-tenant`; nuevo path
  `POST /auth/password/change` (ya estaba documentado, solo faltaba el servicio).
- **Specs**: `data-model.md` (§4.1 identidad) y `rbac.md` reflejan el modelo nuevo; `rbac.md` gana la
  capacidad **`tenant.settings.manage`** (ámbito `tenant`, catálogo — la consume la tarea 06).
  `casos-de-uso/CU-BE-01-autenticacion-y-sesiones.md` gana el escenario de login en 2 pasos.

## Fuera de alcance

- `deps.py`/router `auth` (llamar a estos métodos desde HTTP) → tarea 05.
- Adaptadores SQLAlchemy reales de los puertos que `auth_service` usa → tarea 04 (aquí se prueba con
  fakes, nivel unit, como en `domain-services`; la integración real llega cuando el router 05 conecta con
  los adaptadores de 04).
- Rate-limiting de login/select-tenant → hueco nombrado sin dueño (ver plan).
- Roles/capacidades por membership más allá de `user_role.tenant_id` existente.

## Scenarios (Gherkin)

Criterios de aceptación (Gherkin) en el caso de uso (actualizado en esta misma tarea):
- [CU-BE-01 — Autenticación y sesiones](../../../specs/backend/casos-de-uso/CU-BE-01-autenticacion-y-sesiones.md)
- [CU-BE-02 — Recuperación e invitación de contraseña](../../../specs/backend/casos-de-uso/CU-BE-02-recuperacion-e-invitacion-de-contrasena.md)

> Nota de alcance: esta tarea reescribe/amplía CU-BE-01 con los escenarios de login en 2 pasos y
> `select_tenant`; añade a CU-BE-02 el escenario de `change_password`. El resto de escenarios ya
> existentes (rotación de refresh, reuse-detection, reset/invitación de un solo uso) se conservan pero se
> re-verifican contra las entidades nuevas (`UserTenantMembership` en vez de `User.status`).

```gherkin
Feature: login multi-tenant y cambio de contraseña (ampliación de esta tarea)

  Scenario: login con una sola membership activa emite tokens directos
    Given un usuario con credenciales válidas y UNA membership active
    When inicia sesión con email y password
    Then recibe un TokenResponse (access + refresh-cookie) para ese tenant

  Scenario: login con varias membresías activas emite un identity_token, no tokens reales
    Given un usuario con credenciales válidas y DOS membresías active en tenants distintos
    When inicia sesión con email y password
    Then recibe un identity_token corto y la lista de esos tenants, sin refresh-cookie

  Scenario: login sin ninguna membership activa se rechaza con el mismo error genérico
    Given un usuario con credenciales válidas pero sin ninguna membership active
    When inicia sesión con email y password
    Then se rechaza con el mismo error que una contraseña incorrecta

  Scenario: select_tenant con una membership activa del identity_token emite el TokenResponse real
    Given un identity_token válido de un usuario con membresías active en los tenants A y B
    When selecciona el tenant A
    Then recibe un TokenResponse real para el tenant A

  Scenario: select_tenant con un tenant fuera de las membresías del identity_token se rechaza
    Given un identity_token válido de un usuario con membership active solo en el tenant A
    When intenta seleccionar el tenant C (no es una de sus membresías)
    Then se rechaza con el mismo error genérico

  Scenario: select_tenant con una membership invited (no active) se rechaza
    Given un identity_token válido de un usuario con membership invited en el tenant B
    When intenta seleccionar el tenant B
    Then se rechaza (la membership no está active)

  Scenario: select_tenant con un identity_token expirado se rechaza
    Given un identity_token cuyo TTL ya pasó
    When se llama a select_tenant con un tenant_id válido
    Then se rechaza con el mismo error genérico

  Scenario: select_tenant rechaza un token cuyo purpose no es tenant_selection
    Given un access token normal (purpose=access) de un usuario
    When se usa ese token como identity_token en select_tenant
    Then se rechaza (no es un identity_token válido)

  Scenario: login con membresías en estados mixtos solo cuenta las active
    Given un usuario con membership active en el tenant A, invited en el tenant B, y disabled en el tenant C
    When inicia sesión con sus credenciales
    Then se comporta como "una sola membership activa" y emite tokens directos para el tenant A

  Scenario: login ignora membresías active en un tenant deshabilitado
    Given un usuario con una membership active en un tenant cuyo status es disabled
    When inicia sesión con sus credenciales
    Then esa membership no cuenta (si era la única, se rechaza con el error genérico)

  Scenario: switch_tenant con una sesión activa cambia a otra membership sin repetir credenciales
    Given un access token válido de un usuario con membership active en los tenants A y B (sesión actual en A)
    When llama a switch_tenant con el tenant B
    Then recibe un AuthResult nuevo para el tenant B

  Scenario: invitar a un email que ya existe como usuario global solo crea la membership
    Given un email que ya es un User global con password fijado, sin membership en el tenant B
    When se invita ese email al tenant B
    Then se crea una UserTenantMembership(tenant B, invited) sin tocar el password existente

  Scenario: invitar un email ya activo en el mismo tenant se rechaza
    Given un usuario con membership active en el tenant B
    When se le vuelve a invitar al tenant B
    Then se rechaza (Conflict)

  Scenario: aceptar una invitación fija el password global y activa solo esa membership
    Given un usuario con una membership invited en el tenant B y otra active en el tenant A
    When acepta la invitación del tenant B con una contraseña nueva
    Then su password global cambia, la membership de B pasa a active, y la de A sigue active sin cambios

  Scenario: forgot_password funciona sobre el email global, sin tenant_id
    Given un usuario existente con al menos una membership
    When solicita forgot_password solo con su email
    Then se emite el AuthToken de reset (mismo comportamiento uniforme que antes, ahora sin tenant_id)

  Scenario: cambiar la contraseña con la actual correcta la actualiza
    Given un usuario con password conocido
    When solicita change_password con la contraseña actual correcta y una nueva
    Then su password se actualiza

  Scenario: cambiar la contraseña con la actual incorrecta se rechaza
    Given un usuario con password conocido
    When solicita change_password con la contraseña actual incorrecta
    Then se rechaza (Validation), sin modificar el password
```

## Provides

`AuthService` reescrito (`login`/`select_tenant`/`switch_tenant`/`invite`/`accept_invitation`/
`change_password`, más lo ya existente) en `app.domain.services.auth_service`; `security.py` con
`purpose`/`tenant_id` opcional; `api-contract.yaml` sincronizado (login 2 pasos, `/auth/select-tenant`,
`/auth/switch-tenant`, `/auth/password/change`, `User`/`UserInvite`/`UserUpdate`); `rbac.md` con
`tenant.settings.manage`; CU-BE-01/02 actualizados. Consumido por la tarea 05 (router `auth`) y la 06
(`/admin/settings`, `admin_users`).

## Definition of Done

- [ ] Tests escritos ANTES de la implementación (Red → Green → Refactor).
- [ ] Cada escenario tiene al menos un test unit (fakes de puertos, mismo nivel que `domain-services`).
- [ ] Todos los tests en verde (`make test`).
- [ ] `Provides` disponible; el dominio no importa `app.infra`.
- [ ] `ruff check` (+`S`) + `ruff format --check` + `mypy` strict OK.
- [ ] Gate de mutation `cosmic-ray` (`break: 80`) sobre `auth_service.py` + `security.py` (lo tocado).
- [ ] Gate `/sdd-lint` sin ERROR (CU-BE-01/02 Gherkin bien formados tras la actualización).
- [ ] Gate de `fact-checker` (incl. verificar que `api-contract.yaml`/`rbac.md`/`data-model.md` quedaron
  realmente sincronizados, no solo mencionados).
- [ ] Documentación: docstrings (por qué el login en 2 pasos, por qué una sola contraseña global, por qué
  `identity_token` no lleva `tenant_id`); session log con la traza a CU-BE-01/02 y a los 3 documentos de
  spec tocados.
