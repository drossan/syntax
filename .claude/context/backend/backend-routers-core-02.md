# Session log — backend-routers-core-02

Tarea: `auth_service` reescrito (login en 2 pasos, `select_tenant`, `switch_tenant`, `invite`/
`accept_invitation` sobre membership, `change_password`) + `security.py` (`purpose`/`tenant_id`
opcional) + sincroniza `api-contract.yaml`/`data-model.md`/`rbac.md`/CU-BE-01/CU-BE-02. Nivel: unit
(fakes de puertos). Fusionada en la misma sesión con `backend-routers-core-01` (ver su session log,
"Decisión: fusión con la tarea 02" — el owner eligió esta opción cuando el rediseño de entidades de la
01 rompía `auth_service`/`test_auth_service.py` sin forma de arreglarlo dentro del alcance declarado
de la 01).

## Entradas

- 2026-08-19 — Continuación de la sesión de la tarea 01 (misma rama, mismo tramo de trabajo).

## Resumen

`AuthService` reescrito sobre las entidades nuevas (`User` global, `UserTenantMembership`,
`RefreshSession.tenant_id`): `login(email, password)` ya no recibe `tenant_id`; cuenta membresías
`active` en tenants no-`disabled` (0 → error genérico, 1 → `AuthResult` con tokens reales, 2+ →
`IdentitySelection` con `identity_token` corto + `TenantChoice[]`, sin refresh-cookie). `select_tenant`/
`switch_tenant` canjean, respectivamente, un `identity_token` (`purpose=tenant_selection`) o un access
token válido por el `TokenResponse` real, re-validando membership+tenant en el momento del canje
(defensa en profundidad, no solo lo válido en el login). `invite(tenant_id, email)`/
`accept_invitation` operan sobre `UserTenantMembership.status`. `change_password` nuevo. Puerto nuevo
`UserTenantMembershipRepository` en `app.domain.ports.repositories`; `UserRepository.get_by_email`
pierde el parámetro `tenant_id` (búsqueda global). `security.py`: `create_access_token`/
`decode_access_token` ganan `purpose` (default `"access"`) y `tenant_id` opcional — solo se exige
cuando `purpose == "access"`.

## Decisiones técnicas + porqué

- **`_eligible_memberships` centraliza el filtro `active` + tenant no-`disabled`** (usado por `login` y
  reflejado en `_issue_tokens_for_selected_tenant` para `select_tenant`/`switch_tenant`) — evita
  duplicar la lógica de elegibilidad en 3 sitios distintos.
- **`select_tenant`/`switch_tenant` RE-validan membership+tenant en el momento del canje**, no confían
  en que seguían siendo válidas cuando se emitió el `identity_token`/access token — cubre el caso real
  de que un tenant se deshabilite ENTRE el login y la selección (test dedicado:
  `test_select_tenant_rejects_a_membership_whose_tenant_became_disabled_after_login`).
- **`accept_invitation` activa TODAS las membresías `invited` del usuario, no solo la del token**
  (limitación conocida, documentada en `data-model.md §4.1`): `auth_token` no lleva `tenant_id` (fuera
  del alcance de esta tarea tocar ese esquema) — con invitaciones simultáneas a 2+ tenants para el mismo
  usuario, aceptar una activa todas. Riesgo de seguridad nulo (mismo destinatario en ambos casos);
  mismo criterio que otros riesgos conocidos documentados del plan (CAS de `ticket_service`, `Deny
  out_of_scope` de `rbac_service`).
- **`jwt.InvalidTokenError` capturado dentro de `auth_service._decode_subject`**, no en `security.py` —
  el dominio decide que CUALQUIER fallo de decodificación (expirado, firma inválida, `purpose`
  incorrecto) colapsa al mismo error genérico de credenciales; `security.py` se mantiene como primitiva
  pura que solo valida forma/expiración, no semántica de negocio.
- **Congelación de `alembic/versions/0001_initial_schema.py`** — ver session log de la tarea 01
  (bug de arquitectura descubierto al fusionar ambas tareas, resuelto con aprobación del owner).

## Tests corridos + resultado

- `tests/test_auth_service.py`: reescrito completo sobre las entidades nuevas — **49 tests**, verdes.
  Cubre los 17 escenarios Gherkin de la tarea (login 1/2+/0 membresías, mixtas, tenant disabled,
  select/switch-tenant incl. purpose cruzado y tenant deshabilitado a posteriori, invite/accept sobre
  membership, change_password, más los boundary/regresión heredados de refresh/reset).
- `tests/test_security.py`: **32 tests** (añadidos: `purpose` default, `identity_token` sin
  `tenant_id`, purpose desconocido no exige `tenant_id`, longitud exacta de `new_opaque_token`).
- Suite completa del backend (`pytest -q`): **verde**, 392 tests (verificado por `fact-checker`
  contando símbolos + `--collect-only`). Una colisión transitoria de concurrencia se dio DURANTE el
  cierre (el subagente de `fact-checker` corriendo tests contra la misma `syntax_test` en paralelo con
  una ejecución manual mía) — `tests/test_session.py` falló una vez con "relation ticket does not
  exist"; re-ejecutado en aislamiento, verde. No es una regresión de esta tarea.
- `ruff check .`: OK. `ruff format --check .`: OK en todos los ficheros tocados (1 fichero preexistente,
  `docs/domain-services-explicado.md`, con drift de formato NO relacionado con esta sesión — no se
  tocó).
- `mypy app` (strict): `Success: no issues found in 93 source files`.
- Mutation (`cosmic-ray`):
  - `auth_service.py` (test-command: `test_auth_service.py`+`test_security.py`): primera pasada
    8.56% survival (22 survivors) → tras reforzar tests (ver abajo) → **4.67% survival** (12
    survivors), muy por debajo del `fail-over 20` del Makefile. Los 12 supervivientes restantes están
    documentados como equivalentes o de bajo valor: 8× `is`/`is not` ↔ `==`/`!=` sobre miembros de
    `Enum` (singletons, observacionalmente idénticos); `eligible[0]` vs `eligible[-1]` y
    `len(eligible) == 1` vs `<= 1` (equivalentes: en ese punto `eligible` tiene garantizado exactamente
    o al menos 1 elemento); 3× marcador `*`→`/` (keyword-only → positional-only) en métodos PRIVADOS
    (`_issue_tokens`, `_issue_tokens_for_selected_tenant`, `_decode_subject`) — el contrato keyword-only
    ya se prueba en los métodos PÚBLICOS equivalentes (`login`/`refresh`/`select_tenant`/
    `switch_tenant`).
  - `security.py` (test-command: `test_security.py`+`test_auth_service.py`): primera pasada 3.70%
    survival (3 survivors) → tras añadir 2 tests (longitud exacta del token opaco, purpose que ordena
    antes de "access" alfabéticamente) → **0.00% survival** (100% mutation score).
- `/sdd-lint`: pasada mecánica limpia. Pasada semántica (subagente fresco) encontró **3 ERROR**
  bloqueantes en CU-BE-01/CU-BE-02 (extensiones 2b/3b de CU-BE-01 sin Scenario Gherkin; Precondiciones
  de CU-BE-02 contradiciendo el escenario principal y el Gherkin de "invitar email existente") —
  corregidos (2 escenarios Gherkin nuevos en CU-BE-01, Precondiciones de CU-BE-02 reescritas por
  sub-flujo, extensión 1a añadida). Re-verificado por un SEGUNDO subagente fresco: los 4 puntos
  RESUELTOS. Quedan 2 AVISOS reconocidos (no bloqueantes): `spec.md` (FR-001..009) aún no referencia
  explícitamente `identity_token`/`select_tenant`/`switch_tenant`/`change_password` — declarado en la
  cabecera de ambos CU como ampliación del plan 11, no se amplía `spec.md` en esta tarea (fuera del
  alcance declarado: la tarea toca CU-BE-01/02, no `spec.md`).
- `fact-checker`: ver informe íntegro en la respuesta al usuario de esta sesión (subagente
  independiente, verificó tests/ruff/mypy/mutation/migración congelada/entidades/contrato ejecutando
  los comandos él mismo).

## Docs actualizadas

- `.claude/specs/general/api-contract.yaml`: `LoginRequest`/`TokenResponse` sin cambio de forma; nuevo
  `LoginTenantSelection`+`TenantChoice`; `/auth/login` con respuesta `oneOf`; nuevos paths
  `/auth/select-tenant`/`/auth/switch-tenant`; `User`/`UserInvite`/`UserUpdate` documentan que
  `tenant_id` desaparece de `User` y `status` es el de la membership del tenant consultado, no un
  atributo global.
- `.claude/specs/backend/data-model.md` §4.1: `tenant.auto_approve`, `user` global, `user_tenant`
  nueva (incl. limitación conocida de `auth_token` sin `tenant_id`), `refresh_session.tenant_id`,
  índices y cascadas actualizados (§9, §7, tabla de grupos §2).
- `.claude/specs/backend/rbac.md`: capacidad nueva `tenant.settings.manage` (ámbito `tenant`) en el
  catálogo §2; §7 (contrato de comprobación) documenta `effective_capabilities(user_id, tenant_id)`
  acotado por sesión y la decisión de ámbito por-capacidad de `get_tenant_context`.
- `.claude/specs/backend/casos-de-uso/CU-BE-01-autenticacion-y-sesiones.md` y
  `CU-BE-02-recuperacion-e-invitacion-de-contrasena.md`: reescritos con el login en 2 pasos,
  `select_tenant`/`switch_tenant`, `invite` sobre membership y `change_password` (9 → 11 escenarios en
  CU-BE-01; CU-BE-02 gana `change_password` + el escenario de invitar un email ya existente).
- Docstrings de `auth_service.py` (por qué el login en 2 pasos, por qué una sola contraseña global, por
  qué el `identity_token` no lleva `tenant_id`, limitación de `accept_invitation`) y de `security.py`
  (`purpose`/`tenant_id` opcional). Este session log.

## Ficheros / commits

- `backend/app/domain/services/auth_service.py` (reescrito), `backend/app/core/security.py`,
  `backend/app/domain/ports/repositories.py` (`UserTenantMembershipRepository` nuevo,
  `UserRepository.get_by_email` sin `tenant_id`).
- `backend/tests/test_auth_service.py` (reescrito), `backend/tests/test_security.py` (ampliado).
- `backend/cosmic-ray.toml` (apunta a `app/core/security.py`, último módulo mutado de la sesión).
- `.claude/specs/general/api-contract.yaml`, `.claude/specs/backend/{data-model.md,rbac.md,
  casos-de-uso/CU-BE-01-*.md,casos-de-uso/CU-BE-02-*.md}`.
- Commit conjunto con la tarea 01 (fusión decidida al arrancar la sesión).

## Tiempo real

- `estimate: 4h` → real: sesión conjunta con la tarea 01 (`estimate: 3h`, total nominal 7h); no se
  desglosó tiempo por tarea al fusionarlas. Ver retro en el cierre del plan.

## Follow-ups

- `spec.md` (FR-001..009) queda sin actualizar para reflejar login en 2 pasos/`change_password` — aviso
  reconocido de `/sdd-lint`, no bloqueante; candidato a limpieza futura (no es deuda de código, es deuda
  de spec).
- La limitación de `accept_invitation` (activa todas las `invited`, no solo la del token) queda
  documentada como riesgo conocido; si en el futuro se necesita precisión por-tenant, requiere añadir
  `tenant_id` a `auth_token` (migración nueva).
