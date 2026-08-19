---
id: backend-routers-core-05
package: backend
plan: routers-core
status: pending
priority: 1
depends_on: [backend-routers-core-02, backend-routers-core-04]
estimate: 3h
actual:
issue:
created: 2026-08-19
updated: 2026-08-19
---

# deps (get_current_subject/get_tenant_context/require_capability) + router auth completo

## Description

Conecta HTTP con `auth_service` (02) y los adaptadores de identidad (04): las 3 dependencias FastAPI que
el resto de routers (06-09) reutilizarán, y el primer router completo del plan. `get_tenant_context`
decide `tenant_scope` vs `global_scope` **por el ámbito concedido de la capacidad requerida** (decisión de
`grilling`), no por un flag fijo del sujeto. Spec: CU-BE-01/02/03, `rbac.md`.

## Spec

- **`app/core/deps.py`**:
  - `get_current_subject(token: str = Depends(oauth2_scheme)) -> Subject`: `decode_access_token`
    (exige `purpose="access"` — un token con otro `purpose`, p.ej. un `identity_token`, se rechaza — y
    `tenant_id`) → **comprueba `Tenant.status != disabled`** (un tenant deshabilitado no opera) →
    `RoleRepository.effective_capabilities(user_id, tenant_id)` (acotado al tenant de la sesión) →
    `Subject(id, tenant_id, capabilities)`. Token inválido/expirado/firma inválida/`purpose` incorrecto →
    401 (vía el envelope de la 03).
  - `require_capability(capability: str) -> Callable`: factory de dependencia. Para el `subject` +
    `capability` dados, determina el **ámbito disponible**: si `(capability, "global") in subject.
    capabilities` → abre `global_scope(session)` (**precedencia**: si el subject tiene la misma
    capacidad en ámbito `tenant` Y `global`, gana `global`); si no, y `(capability, "tenant") in subject.
    capabilities` → `tenant_scope(session, subject.tenant_id)`; si ninguno → `Deny(no_capability)` (403,
    vía envelope). Cede `(subject, session-ya-en-scope)` al router.
  - `get_tenant_context` queda como la función que abre el scope correcto (usada por `require_capability`;
    no se expone como dependencia separada salvo que un router necesite el scope sin gate de capacidad).
- **Router `auth`** (`app/api/v1/routers/auth.py`):
  - `POST /auth/login` (público) → `auth_service.login`; responde `TokenResponse` **o**
    `{identity_token, tenants}` según el caso; Set-Cookie del refresh solo en el camino de tokens reales.
  - `POST /auth/select-tenant` (público, requiere `identity_token` válido) → `auth_service.select_tenant`
    → `TokenResponse` + Set-Cookie.
  - `POST /auth/switch-tenant` (requiere `get_current_subject`, sesión ya autenticada) →
    `auth_service.switch_tenant` → `TokenResponse` + Set-Cookie del tenant elegido.
  - `POST /auth/refresh` (público, lee refresh de la cookie) → `auth_service.refresh`.
  - `POST /auth/logout` → `auth_service.logout`.
  - `GET /auth/me` → `Subject` + capacidades (vía `get_current_subject`); expone `tenant_id` (el de la
    sesión activa — vive en `Subject`, no en `User`, que ya no lo tiene tras el rediseño de la tarea 01).
  - `POST /auth/password/{forgot,reset,change}` → `auth_service.{forgot_password,reset_password,
    change_password}` (`change` requiere `get_current_subject`, los otros dos son públicos).
  - Todos los errores vía el envelope de la tarea 03 (nada de `try/except` local en el router).

## Fuera de alcance

- Routers `admin_*`/`tickets`/`messages`/`kb` → tareas 06-09 (reutilizan estas 3 dependencias, no las
  redefinen).
- Rate-limiting de login/refresh/select-tenant → hueco nombrado sin dueño.
- `POST /tickets/{id}/ai-draft` y cualquier flujo del grafo → plan 12/15/16.

## Scenarios (Gherkin)

Criterios de aceptación (Gherkin) en los casos de uso:
- [CU-BE-01 — Autenticación y sesiones](../../../specs/backend/casos-de-uso/CU-BE-01-autenticacion-y-sesiones.md)
- [CU-BE-03 — Autorización y aislamiento tenant](../../../specs/backend/casos-de-uso/CU-BE-03-autorizacion-y-aislamiento-tenant.md)

> Nota de alcance: de CU-BE-01, esta tarea cubre el router HTTP completo (login 2 pasos, select-tenant,
> refresh, logout, me, password). De CU-BE-03, cubre `get_current_subject`/`require_capability`/decisión
> de ámbito — no la autorización de recursos concretos (eso lo ejercitan las tareas 06-09 sobre sus
> propios endpoints).

```gherkin
Feature: dependencias de auth/RBAC y router auth end-to-end

  Scenario: login con credenciales válidas y 1 tenant emite access + refresh-cookie
    Given un usuario activo en un solo tenant
    When hace POST /auth/login con sus credenciales
    Then recibe 200 con TokenResponse y una cookie de refresh httpOnly

  Scenario: login con credenciales válidas y 2 tenants pide selección
    Given un usuario activo en dos tenants
    When hace POST /auth/login con sus credenciales
    Then recibe 200 con identity_token + la lista de tenants, sin cookie de refresh

  Scenario: select-tenant con el identity_token y un tenant válido emite tokens reales
    Given un identity_token de un usuario con 2 tenants
    When hace POST /auth/select-tenant con uno de esos tenant_id
    Then recibe 200 con TokenResponse y cookie de refresh

  Scenario: GET /auth/me sin token se rechaza
    Given ninguna Authorization header
    When hace GET /auth/me
    Then recibe 401 problem+json

  Scenario: GET /auth/me con token válido devuelve el subject y sus capacidades
    Given un access token válido
    When hace GET /auth/me
    Then recibe 200 con el user y sus (capability, scope) resueltos server-side

  Scenario: require_capability con ámbito global abre global_scope
    Given un subject con la capacidad "tenant.manage" en ámbito global
    When accede a un endpoint que exige "tenant.manage"
    Then la consulta subyacente ve datos de cualquier tenant (bypass RLS activo)

  Scenario: require_capability con ámbito tenant abre tenant_scope del propio tenant
    Given un subject con una capacidad solo en ámbito tenant
    When accede a un endpoint que exige esa capacidad
    Then la consulta subyacente queda acotada a su propio tenant_id

  Scenario: require_capability con la misma capacidad en ámbito tenant Y global prioriza global
    Given un subject con (cap,"tenant") y (cap,"global") ambos concedidos
    When accede a un endpoint que exige esa capacidad
    Then se abre global_scope (gana el ámbito más amplio)

  Scenario: require_capability sin la capacidad devuelve 403
    Given un subject sin la capacidad requerida por el endpoint
    When accede a ese endpoint
    Then recibe 403 problem+json

  Scenario: un identity_token usado como access token se rechaza
    Given un identity_token (purpose=tenant_selection) de un login con 2+ tenants
    When se usa como Bearer en un endpoint protegido (p.ej. GET /auth/me)
    Then recibe 401

  Scenario: un JWT con firma inválida se rechaza
    Given un token firmado con un secreto distinto al configurado
    When se usa como Bearer en un endpoint protegido
    Then recibe 401

  Scenario: login/sesión en un tenant deshabilitado se rechaza
    Given un usuario con su única membership active en un tenant cuyo status es disabled
    When hace POST /auth/login con sus credenciales
    Then se rechaza con el mismo error genérico

  Scenario: switch-tenant cambia de tenant sin pedir credenciales de nuevo
    Given una sesión autenticada en el tenant A, con membership active también en el tenant B
    When hace POST /auth/switch-tenant con el tenant B
    Then recibe 200 con TokenResponse para el tenant B, sin haber enviado password

  Scenario: switch-tenant a un tenant sin membership se rechaza
    Given una sesión autenticada sin membership en el tenant C
    When hace POST /auth/switch-tenant con el tenant C
    Then se rechaza

  Scenario: logout revoca la sesión server-side
    Given una sesión de refresh activa
    When hace POST /auth/logout
    Then un refresh posterior con ese token falla

  Scenario: password/change con la contraseña actual correcta la actualiza
    Given un usuario autenticado
    When hace POST /auth/password/change con su contraseña actual correcta y una nueva
    Then recibe 204 y el nuevo password verifica en el siguiente login
```

## Provides

`app.core.deps.{get_current_subject, get_tenant_context, require_capability}` — reutilizados por TODOS
los routers restantes (06-09). Router `auth` completo montado en `/api/v1`.

## Definition of Done

- [ ] Tests escritos ANTES de la implementación (Red → Green → Refactor).
- [ ] Cada escenario tiene al menos un test de integración (cliente HTTP FastAPI + Postgres real).
- [ ] Todos los tests en verde (`make test`).
- [ ] `Provides` disponible; los routers 06-09 pueden importar `deps` sin más cambios.
- [ ] `ruff check` (+`S`) + `ruff format --check` + `mypy` strict OK.
- [ ] Gate de mutation `cosmic-ray` (`break: 80`) sobre `deps.py` y el router `auth`.
- [ ] Gate `/sdd-lint` sin ERROR (CU-BE-01/03 Gherkin bien formados, enlaces válidos).
- [ ] Gate de `fact-checker`.
- [ ] Documentación: docstrings (por qué la decisión de scope es por-capacidad, no por-subject); session
  log con la traza a CU-BE-01/03.
