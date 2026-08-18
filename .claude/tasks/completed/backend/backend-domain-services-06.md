---
id: backend-domain-services-06
package: backend
plan: domain-services
status: done
priority: 1
depends_on: [backend-domain-services-02]
estimate: 3h
actual: 1.5h
issue:
created: 2026-08-18
updated: 2026-08-18
---

# auth_service (login, refresh rotación+reuse-detection, reset/invitación) + primitiva de token opaco

## Description

Login, rotación de refresh con reuse-detection, y password reset/invitación (B.3), sobre
`app.core.security` (ya existente: Argon2id + JWT) — tratado como **primitivas puras adyacentes al
dominio**: `auth_service` las consume directamente; `secret`/`ttl` llegan como **parámetros** del llamante
(futuro `deps`), el servicio nunca lee `get_settings()` (decisión de design-review). **Añade una
primitiva nueva** a `app/core/security.py`: hash **determinista** de token opaco — `refresh_session.
token_hash`/`auth_token.token_hash` son `UNIQUE` y se buscan por igualdad; Argon2 (salt aleatorio
embebido) hace esa búsqueda imposible. **No** implementa throttling de login (FR-006 es de la capa de
routers, ya lo declara el guión de `app/api/v1/routers/auth.py`). Guión: `app/domain/services/
auth_service.py`. Spec: FR-001..005/007..009, CU-BE-01, CU-BE-02.

## Spec

- `app/core/security.py` (**añade**, no reemplaza lo existente): `new_opaque_token() -> str` (256 bits,
  `secrets.token_urlsafe`) + `hash_token(token: str) -> str` (SHA-256, determinista — buscable por
  igualdad, a diferencia de `hash_password`/Argon2).
- `login(email, password, tenant_id) -> (access_token, refresh_session)`: verifica `verify_password`
  (Argon2id); si falla, error **genérico** (no revela si el email existe); emite access (`create_access_
  token`, `secret`/`algorithm`/`ttl` como parámetros) + crea `RefreshSession` (nueva `family_id`,
  `token_hash` = `hash_token(new_opaque_token())`).
- `refresh(token) -> (access_token, refresh_session)`: **una sola llamada CAS** —
  `RefreshSessionRepository.rotate_if_active(hash_token(token), hash_token(new_opaque_token()),
  clock.now())` (evita el check-then-act de buscar/comprobar/actualizar en pasos separados,
  `scenario-coverage`): `Rotated(session)` → emite access nuevo; `Reused(family_id)` → **reuse-detection**:
  revoca **toda** la `family_id`, lanza `Conflict` (no emite nada); `NotFound` → refresh inválido/caducado,
  rechaza con el **mismo** error genérico que `Reused` (no distinguir "no existe" de "caducado" en la
  respuesta evita filtrar información) — pero **caducado-no-reusado** (sesión `active` con `expires_at` en
  el pasado) es una rama propia: rechaza exigiendo re-login, **sin** disparar reuse-detection (no revoca
  la familia, porque no hubo reuso — solo expiración natural).
- `logout(token)`: revoca la `RefreshSession` vigente **server-side** (no solo depende de que el cliente
  borre la cookie).
- `forgot_password(email)`: **siempre** responde igual, exista o no el email; si existe, crea
  `AuthToken(kind=password_reset)` (hash determinista, caducidad) y llama a `EmailPort.send` (stub, fuera
  de alcance el adaptador real).
- `reset_password(token, new_password)`: canjea el `AuthToken` (no caducado, `used_at IS NULL`, `kind=
  password_reset`) → `hash_password` + marca `used_at`; token inválido/caducado/usado/de otro `kind` →
  rechaza sin distinguir el motivo en la respuesta (CU-BE-02).
- `invite(user_id)` / `accept_invitation(token, password)`: mismo mecanismo de `AuthToken(kind=
  invitation)`; al aceptar, `user.status` pasa de `invited` a `active`. `invite()` sobre un usuario ya
  `active` → rechaza (`Validation`, reinvitación indebida).
- `login(email, password, tenant_id)` sobre un `user.status` distinto de `active` (`invited`/`disabled`), o
  con un `tenant_id` que no corresponde al tenant real del usuario: mismo error **genérico** que
  credenciales inválidas (no revela cuál de las tres condiciones falló, ni entre tenants).
- Puertos por inyección: `UserRepository`, `RefreshSessionRepository`, `AuthTokenRepository`, `EmailPort`,
  `Clock`.

## Fuera de alcance

- Throttling de login (FR-006) → capa de routers.
- Alta de usuarios / administración de tenants (CU-BE-09) → `auth_service` solo cubre `AuthToken`
  (emisión/canje/email-stub), no el alta del usuario en sí.
- Adaptador real de email (SMTP) → diferido.
- Política de contraseña (longitud/complejidad mínima) → hueco nombrado, sin dueño asignado.
- Repos concretos → fuera de este plan.

## Scenarios (Gherkin)

Criterios de aceptación (Gherkin) en los casos de uso:
- [CU-BE-01 — Autenticación y sesiones](../../../specs/backend/casos-de-uso/CU-BE-01-autenticacion-y-sesiones.md)
- [CU-BE-02 — Recuperación e invitación de contraseña](../../../specs/backend/casos-de-uso/CU-BE-02-recuperacion-e-invitacion-de-contrasena.md)

> Nota de alcance: de CU-BE-01, esta tarea cubre "Login con credenciales válidas/inválidas", "Rotación del
> refresh", "Reuse-detection de un refresh robado", "Logout revoca la sesión server-side" — **excepto**
> "Throttling tras varios fallos de login" (fuera de alcance, capa de routers). De CU-BE-02, esta tarea
> cubre los 5 escenarios completos (reset/canje/invitación/no-revelar-email/Scenario Outline de tokens
> inutilizables). Añadido por `scenario-coverage` (CU-BE-01 lo narra en su prosa de extensiones pero no
> lo Gherkin-iza):
> ```gherkin
> Scenario: Refresh caducado se rechaza sin activar reuse-detection
>   Given una sesión de refresh activa pero con expires_at en el pasado
>   When se presenta ese refresh para renovar
>   Then la renovación se rechaza exigiendo re-login, sin revocar la family_id
>
> Scenario Outline: login con usuario no-active se rechaza igual que credenciales inválidas
>   Given un usuario en estado <estado>
>   When intenta iniciar sesión con su contraseña correcta
>   Then la autenticación se rechaza con el mismo error genérico
>
>   Examples:
>     | estado   |
>     | invited  |
>     | disabled |
>
> Scenario: login con tenant_id que no corresponde al usuario se rechaza
>   Given un usuario que existe en el tenant A
>   When intenta iniciar sesión indicando el tenant B
>   Then la autenticación se rechaza con el mismo error genérico (no revela en qué tenant existe)
>
> Scenario: invitar a un usuario ya activo se rechaza
>   Given un usuario en estado active
>   When se le vuelve a invitar
>   Then la invitación se rechaza (Validation)
> ```

## Provides

`auth_service` (login/refresh/logout/forgot/reset/invite) en `app.domain.services.auth_service`, y
`new_opaque_token()`/`hash_token()` en `app.core.security`, consumidos por los futuros routers de auth
(11/12).

## Definition of Done

- [x] Tests escritos ANTES de la implementación (Red → Green → Refactor).
- [x] Cada escenario del CU (alcance de esta tarea) tiene al menos un test, incl. la primitiva nueva
  (`hash_token` determinista: mismo input → mismo hash, distinto de `hash_password`), el CAS de
  `rotate_if_active` (Rotated/Reused/NotFound), refresh caducado sin reuse-detection, login con
  invited/disabled/tenant equivocado, invitación a usuario ya activo.
- [x] Todos los tests en verde (`make test`).
- [x] `Provides` disponible; el dominio no importa `app.infra`; `secret`/`ttl` como parámetros (no
  `get_settings()` dentro del servicio).
- [x] `ruff check` (+`S`) + `ruff format --check` + `mypy` strict OK.
- [x] Gate de mutation `cosmic-ray` (`break: 80`) sobre `auth_service.py` + la primitiva nueva de
  `security.py`. Resultado: 2.50% survival (3 quasi-equivalentes de Enum, documentados en el session log).
- [x] Gate `/sdd-lint` sin ERROR (CU-BE-01/CU-BE-02 Gherkin bien formados, enlaces válidos). Solo AVISOS
  semánticos (gaps del propio CU, no de esta tarea), reconocidos en el session log.
- [x] Gate de `fact-checker`. 9/10 VERIFICADO, 1 INCORRECTO (conteo de tests propio, corregido en el log).
- [x] Documentación: docstrings (por qué SHA-256 y no Argon2 para `token_hash`, reuse-detection,
  no-revelar-existencia); session log con la traza a CU-BE-01/CU-BE-02.
