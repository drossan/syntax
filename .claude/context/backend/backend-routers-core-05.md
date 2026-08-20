# Session log — backend-routers-core-05

Tarea: `app.core.deps` (`get_current_subject`/`get_tenant_context`/`require_capability`) + router
`auth` completo (login 2 pasos, select/switch-tenant, refresh, logout, me, password
forgot/reset/change). Nivel: integración (Postgres real vía `httpx.ASGITransport` + `superuser_engine`,
primera vez que se ejercita el ciclo de vida completo de una request HTTP real sobre el dominio de
identidad). Depends_on: 02, 04 (ambas `done`).

## Entradas

- 2026-08-19 — Arranque. La tarea seguía en `.claude/tasks/pending/backend/` (debió moverse a `active/`
  al empezar) — corregido en el cierre: movida a `active/` y `status: pending`→`status: active` en el
  frontmatter, antes de continuar.

## Resumen

`app/core/deps.py` (nuevo): `get_db_session` (delega en `app.infra.db.session.get_session`),
`get_auth_service` (ensambla `AuthService` con los 6 adaptadores de la tarea 04 + `SystemClock` +
`StubEmailPort`), `get_current_subject` (JWT `purpose=access` → `Subject` con capacidades resueltas
server-side vía `RoleRepository.effective_capabilities`, nunca desde el propio token), `get_tenant_context`
(decide `global_scope`/`tenant_scope` por el ámbito CONCEDIDO de la capacidad requerida, precedencia
`global`>`tenant`), `require_capability` (factory que cede `(subject, session-ya-en-scope)` a los
routers 06-09). `app/api/v1/routers/auth.py` (nuevo): router completo con los 9 endpoints del contrato.
`app/api/v1/schemas/auth.py` (nuevo): DTOs (`LoginRequest`, `TokenResponse`, `TenantChoice`,
`LoginTenantSelection`, `SelectTenantRequest`, `SwitchTenantRequest`, `ForgotPasswordRequest`,
`ResetPasswordRequest`, `ChangePasswordRequest`, `CapabilityGrant`, `MeUser`, `Me`). `app/infra/clock.py`
(nuevo, `SystemClock`) y `app/infra/email.py` (nuevo, `StubEmailPort`, loguea vía structlog en vez de
enviar) — primeros adaptadores reales de los puertos `Clock`/`EmailPort` de `domain-services`.
`app/core/security.py` gana `JWT_ALGORITHM` (constante de módulo). `app/api/errors.py` gana la entrada
401 y un caso especial (`auth.invalid_credentials`→401 en vez del 422 genérico de `Validation`).
`pyproject.toml`: `extend-immutable-calls` para `Depends`/`Query`/`Path`/`Body` (Ruff/bugbear `B008`
marcaba como falso positivo el patrón idiomático de FastAPI `= Depends(...)` en los defaults).

## Decisiones técnicas + porqué

- **3 bugs REALES encontrados al conectar el router de punta a punta por primera vez** (ninguno se
  manifestaba en los tests unitarios/con fakes de `domain-services`, porque ninguno ejercitaba el ciclo
  de vida completo de una `AsyncSession` de request):
  1. **`RoleRepository.effective_capabilities` leía `CapabilityModel.scope`** (el ámbito MÁXIMO del
     catálogo) **en vez de derivar el ámbito de la asignación** (`UserRoleModel.tenant_id IS NULL` →
     `"global"`, si no → `"tenant"`). Como `capability.name` es único global, la MISMA capacidad puede
     llegar a un subject por dos vías (un rol `system` global y un rol `tenant`), y `Subject.capabilities`
     necesita distinguirlas para que la precedencia `global`>`tenant` de `get_tenant_context` funcione.
     Leer el catálogo colapsaba ambas vías a un único valor fijo. Fix: la query ahora agrupa por
     `UserRoleModel.tenant_id` y deriva el ámbito ahí. Test de regresión:
     `test_effective_capabilities_scope_comes_from_the_assignment_not_the_catalog`.
  2. **`get_session()` nunca llamaba a `commit()`** — un `flush()` de un adaptador envía el SQL pero no
     cierra la transacción; al cerrar la sesión al final del request sin commit explícito, el cambio se
     perdía. Se detectó porque `POST /auth/password/change` respondía 204 pero el nuevo password nunca
     verificaba en el siguiente login. Fix: commit-on-success / rollback-on-exception envolviendo el
     `yield` de la dependencia.
  3. **`tenant_scope`/`global_scope` llamaban `session.begin()` incondicionalmente** — fallaba con
     `InvalidRequestError: A transaction is already begun` cuando `get_current_subject` ya había
     ejecutado queries en la misma sesión (autobegin de SQLAlchemy) antes de que `require_capability`
     abriera el scope. Fix: comprobar `session.in_transaction()` antes de decidir entre reusar la
     transacción activa (aplicar el `SET LOCAL` sobre ella) o abrir una nueva.
- **Código muerto encontrado y eliminado en `switch_tenant`**: `if access_token is None: raise
  HTTPException(status_code=401)` nunca se ejecutaba — `_subject: Subject = Depends(get_current_subject)`
  es una dependencia hermana que usa el MISMO `oauth2_scheme` (cacheado por FastAPI dentro del mismo
  request), y `get_current_subject` ya rechaza `token is None` con 401 antes de que el cuerpo de
  `switch_tenant` llegue a ejecutarse. Se detectó porque el mutation gate no lograba matar ningún
  mutante de ese `401` (todos sobrevivían: 402, 400, cualquier cambio) por más tests que se añadieran —
  no era un hueco de cobertura, era código inalcanzable. Se eliminó el bloque y se sustituyó por
  `cast(str, access_token)` (solo narrowing de tipo para `mypy`, sin superficie de mutación real) +
  se quitó el import ya no usado de `HTTPException`.
- **`_cookie_kwargs` con `secure` derivado de `settings.app_env != "development"`** — decisión de la
  02/03 (permite probar el flujo completo en local sin TLS) que esta tarea conecta por primera vez a
  una respuesta HTTP real; los tests de mutación exigieron fijar el comportamiento exacto para varios
  valores de `app_env` (ver más abajo), no solo para "producción" vs "desarrollo".
- **`GET /auth/me` distingue user-ausente de membership-ausente con `or`, no `and`**: un token válido
  garantiza que el `tenant` existe y no está `disabled` (lo comprueba `get_current_subject`), pero NO
  garantiza que la `UserTenantMembership` siga existiendo — puede haberse borrado entre emitir el token
  y esta request (carrera rara, documentada en el propio código). `user is None or membership is None`
  cubre ambos casos con el mismo 404 controlado.

## Tests corridos + resultado

- `tests/test_router_auth.py` (nuevo): **23 tests** — los 16 escenarios Gherkin de la tarea (login 1/2
  tenants, select/switch-tenant, refresh, logout, `me`, password/change, las 4 decisiones de ámbito de
  `require_capability`) más 7 reforzados durante el endurecimiento de mutación del router:
  - Atributos exactos de la cookie de refresh (`httponly`/`secure`) bajo `app_env="production"`,
    `"development"` y un valor alfabéticamente menor (`"ci"`) — necesarios para matar los mutantes de
    comparación (`!=`→`==`/`<`/`<=`/`>`/`>=`/`is`) sobre `settings.app_env != "development"`.
  - Un caso con un string igual por VALOR a `"development"` pero construido en runtime (no el literal
    interned del módulo, vía `"".join(c for c in "development")`) para distinguir `!=` (comparación por
    valor, correcta) de `is not` (comparación por identidad, mal mutada).
  - `GET /auth/me` con `user` existente pero `membership` ausente (nunca se creó, en vez de borrarla —
    no hay puerto de borrado) — mata el mutante `or`→`and` de la línea 164.
  - `POST /auth/password/forgot` (202 siempre) y `POST /auth/password/reset` (204, seedeando un
    `AuthToken(kind=password_reset)` real vía `SqlAlchemyAuthTokenRepository` para obtener un token en
    claro utilizable) — ninguno de los dos endpoints tenía ningún test antes de este endurecimiento.
- Suite completa del backend (`pytest -q`): **470 tests, verde**, sin regresiones.
- `ruff check .`: OK. `ruff format --check .`: OK en todos los ficheros tocados (el único drift restante,
  `docs/domain-services-explicado.md`, es preexistente y no se tocó). `mypy app` (strict):
  `Success: no issues found in 105 source files`.
- Mutation (`cosmic-ray`, `.venv/bin/cr-rate --fail-over 20`, `test-command`: `test_router_auth.py`),
  corrido por separado sobre cada fichero que pide la DoD:
  - `app/core/deps.py`: primera pasada, **12.82% survival** (≤20% umbral) → **PASA** sin cambios
    adicionales.
  - `app/api/v1/routers/auth.py`: primera pasada, **29.82% survival** (17 survivors: 8 sobre
    `_cookie_kwargs`, 1 sobre `me`, 2 sobre el 401 muerto de `switch_tenant`, 6 sobre
    `password/forgot`+`password/reset` sin tests) → **FALLA**. Tras los refuerzos descritos arriba +
    eliminar el código muerto de `switch_tenant`: segunda pasada, **0.00% survival (100% mutation
    score)** → **PASA**.
- Gate `/sdd-lint`: mecánico limpio (sin `[NECESITA ACLARACIÓN` pendiente, sin IDs `FR`/`SC` mal
  formados ni duplicados en `spec.md`, secciones obligatorias del caso de uso presentes en CU-BE-01 y
  CU-BE-03, los enlaces de la tarea 05 a ambos CU resuelven a ficheros reales). Semántico vía subagente
  fresco: **0 ERROR, 4 AVISO** (gate pasa, avisos reconocidos):
  1. Los 3 escenarios de login por nº de membresías (0/1/2+) de CU-BE-01 podrían modelarse como un
     `Scenario Outline` en vez de 3 Scenarios independientes — no bloqueante, cosmético.
  2. El flujo multi-tenant (`identity_token`/select-tenant/switch-tenant) de CU-BE-01 no tiene FR
     explícito todavía en `spec.md` (el propio CU ya lo reconoce como ampliación pendiente del
     rediseño de identidad, plan 11) — hueco de spec nombrado, no de esta tarea.
  3. La precedencia `global`>`tenant` de `require_capability` (escenario de la tarea, línea 112-115) no
     está respaldada por ninguna regla de negocio explícita de CU-BE-03 — recomendable retro-alimentar
     el CU en un futuro ajuste de specs, no bloqueante.
  4. El escenario de `password/change` en el `## Scenarios` de la tarea pertenece al dominio de CU-BE-02
     (no citado en la lista de trazabilidad de la tarea, que solo nombra CU-BE-01/03) — inconsistencia
     interna menor de la propia tarea, no contradicción con CU-BE-01/03.
- `fact-checker`: pendiente de lanzar tras este session log.

## Docs actualizadas

- Docstrings de `app/core/deps.py` (por qué la decisión de ámbito es por-capacidad concedida, no por un
  flag fijo del subject; el anti-patrón explícito de resolver permisos desde el JWT), de
  `app/infra/db/session.py` (`get_session` commit-on-success/rollback-on-exception, `tenant_scope`/
  `global_scope` reusando una transacción ya activa), de `app/infra/db/repositories/role.py`
  (`effective_capabilities` — el bug real y su fix), del router `auth.py` (el porqué del `cast` en vez
  del `if`/`raise` muerto en `switch_tenant`). Este session log.

## Ficheros / commits

- `backend/app/core/deps.py` (nuevo), `backend/app/api/v1/routers/auth.py` (nuevo),
  `backend/app/api/v1/schemas/auth.py` (nuevo), `backend/app/infra/clock.py` (nuevo),
  `backend/app/infra/email.py` (nuevo).
- `backend/app/core/security.py` (`JWT_ALGORITHM`), `backend/app/api/errors.py` (entrada 401 +
  `auth.invalid_credentials`), `backend/app/main.py` (monta `auth_router`), `backend/pyproject.toml`
  (`extend-immutable-calls`).
- `backend/app/infra/db/repositories/role.py` (fix `effective_capabilities`), `backend/app/infra/db/
  session.py` (fix commit + fix `in_transaction()`).
- `backend/tests/test_router_auth.py` (nuevo), `backend/tests/test_repositories_identity.py`
  (regresión del bug de `role.py`).
- `backend/cosmic-ray.toml` (apunta a `app/api/v1/routers/auth.py`, último módulo mutado).
- `.claude/tasks/active/backend/backend-routers-core-05.md` (movida desde `pending/`, y de ahí a
  `completed/` en este mismo cierre).
- Commit: uno solo, `backend-routers-core-05: feat(backend): deps + router auth completo`.

## Tiempo real

- `estimate: 3h` → real: sesión propia, ampliada por los 3 bugs reales de infra (ninguno hipotético,
  los 3 confirmados con fallos reproducidos antes de arreglarlos) y por dos rondas de mutation gate
  sobre el router (la segunda para llevarlo de 29.82% a 0.00% survival).

## Follow-ups

- Ninguno propio de esta tarea. Los routers 06-09 reutilizan `get_current_subject`/`get_tenant_context`/
  `require_capability` tal cual (`Provides` de esta tarea) sin necesidad de tocarlos.
- Los 4 AVISO de `/sdd-lint` (arriba) quedan como hueco de specs nombrado, no bloquean el cierre.
