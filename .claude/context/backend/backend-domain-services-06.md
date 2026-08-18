# Session log — backend-domain-services-06

Tarea: `auth_service` (login, refresh rotación+reuse-detection, reset/invitación) + primitiva de
token opaco en `app.core.security`. Nivel: unit. Traza: CU-BE-01, CU-BE-02.

## Entradas

- 2026-08-18 — Arranque. Tarea 06 `active`. TDD escenario a escenario (RED primero).

## Resumen

`app/domain/services/auth_service.py`: `AuthService` con `login`/`refresh`/`logout`/`forgot_password`/
`reset_password`/`invite`/`accept_invitation`, sobre `app.core.security` (consumido como primitivas puras:
`secret`/`algorithm`/`ttl` llegan por parámetro, el servicio no lee `get_settings()`). `refresh()` usa
`RefreshSessionRepository.rotate_if_active` (CAS) distinguiendo tres ramas: `NotFound` (ningún hash
coincide), `Reused` (sesión ya no activa → revoca toda la `family_id`, reuse-detection) y sesión rotada
pero con `expires_at <= now` (expiración natural, rama propia, **sin** revocar la familia). Añadidas dos
primitivas nuevas a `app/core/security.py`: `new_opaque_token()` (256 bits, `secrets.token_urlsafe`) y
`hash_token()` (SHA-256, determinista, para columnas `token_hash` buscadas por igualdad — distinto de
`hash_password`, que es Argon2id con salt aleatorio, no apto para lookup).

## Decisiones técnicas + porqué

- **`RefreshSessionRepository.revoke_by_hash` (puerto nuevo, no estaba en el plan original).** Al
  implementar `logout()` no había forma de revocar una sesión conociendo solo su `token_hash` sin pasar
  por `rotate_if_active` (que rota, no solo revoca). Se añadió el método al `Protocol` (idempotente: si el
  hash no corresponde a ninguna sesión, no-op, no revela cuál de los dos casos ocurrió).
- **Reescritura completa de la primera versión de `AuthService`.** El primer borrador tenía un método
  `_issue_session` muerto y un patrón `status=user.status` con reasignación posterior vía una función
  `_active_refresh_status()` con import local — código confuso que no aportaba nada. Se reescribió entero
  con import top-level de `RefreshSessionStatus` y sin el placeholder.
- **UUIDs deterministas (`uuid.UUID(int=N)`) en vez de `uuid.uuid4()`** para `_TENANT`/`_OTHER_TENANT` en
  los tests: con UUIDs aleatorios, una mutación de operador de comparación (`!=`→`<`/`>`) sobre
  `user.tenant_id != tenant_id` sobrevive porque el resultado da igual con valores random no ordenados a
  propósito — mismo patrón que en las tareas 03/04.
- **Doble `_CrossTenantLeakUserRepository` para probar la defensa en profundidad de `login()`.** El fake
  "honesto" (`_FakeUserRepository.get_by_email`) ya filtra por `tenant_id`, así que la comprobación
  `user.tenant_id != tenant_id` dentro de `login()` nunca se ejercita de verdad a través de él — el fake
  bien portado enmascara el propio código que se quería probar. Se añadió un doble que simula un
  adaptador con bug (no filtra por tenant) para confirmar que `login()` no confía ciegamente en que el
  puerto ya filtró.
- **Constantes TTL con valor fijo en el assert, no importado del propio módulo.** Un primer intento de
  test comparaba contra `_REFRESH_SESSION_TTL_DAYS`/`_AUTH_TOKEN_TTL_HOURS` importadas del mismo módulo
  mutado — si `cosmic-ray` cambia el valor de la constante, el test seguía comparando contra ese mismo
  valor mutado (autorreferencia), así que nunca podía fallar. Se cambió a literales fijos (`14`, `24`).
- **Tests de frontera `<=` vs `<`** en `refresh()` (expiración de sesión) y `_redeem_token()` (expiración
  de `AuthToken`): `expires_at == now` debe tratarse como caducado.
- **3 survivors de mutación aceptados como quasi-equivalentes**: `is`/`is not` ↔ `==`/`!=` sobre miembros
  de `Enum` (`UserStatus.active`, `AuthTokenKind`) — los miembros de `Enum` son singletons en Python, así
  que ambas comparaciones son observacionalmente idénticas; ningún test puede distinguirlas sin acoplarse
  a un detalle de implementación irrelevante.

## Tests corridos + resultado

- `tests/test_auth_service.py`: **31 tests**, todos verdes (`pytest -q tests/test_auth_service.py`).
- Suite completa `pytest -q`: **verde** (5 bloques del 21%/42%/64%/85%/100%, sin fallos).
- `ruff check .` OK · `ruff format --check .` OK (117 ficheros) · `mypy app` strict: `Success: no issues
  found in 92 source files`.
- Mutation (`cosmic-ray` sobre `auth_service.py`, 120 jobs): primera pasada **15.83%** (19 survivors) →
  tras endurecer (keyword-only, UUIDs deterministas, doble cross-tenant-leak, TTLs con literal fijo,
  fronteras `<=`) → **2.50%** (3 survivors, los 3 quasi-equivalentes de Enum documentados arriba). Umbral
  del plan: ≤20% — cumplido con margen amplio.
- Bug propio detectado y corregido durante el endurecimiento: el test parametrizado de tokens
  inutilizables (`already-used`/`expired`/`wrong-kind`) construía cada `AuthToken` con
  `token_hash="h"` literal y llamaba a `reset_password("plain-h", ...)` — como `hash_token("plain-h") !=
  "h"`, los 3 casos solo ejercitaban la rama "token no encontrado", nunca las condiciones específicas de
  cada variante. Corregido para usar `hash_token(plaintext)` consistente en ambos lados.
- `/sdd-lint`: mecánico limpio (CU-BE-01/CU-BE-02 enlazados, sin `[NECESITA ACLARACIÓN`, ids `FR-00N` bien
  formados, secciones Cockburn+Gherkin presentes). Semántico (subagente): **solo AVISOS**, ninguno
  bloqueante — gate PASA. Avisos reconocidos (son gaps del propio CU, no del código de esta tarea, y no
  se corrigen aquí para no ampliar el alcance de una tarea de implementación): CU-BE-01 sin escenario
  Gherkin para "refresh caducado" (extensión 3b) ni para FR-005 (capacidades no en el JWT); CU-BE-02 sin
  escenario de emisión del token de invitación (solo se prueba su aceptación) y sin aserción explícita de
  "no revela existencia" en la vía de canje.
- `fact-checker` (sonnet): **9/10 VERIFICADO, 1 INCORRECTO** — mi afirmación de "33 tests" era errónea
  (son 31; error de conteo propio, no del código). Corregido en este log. Resto de afirmaciones (puerto
  `revoke_by_hash` nuevo, primitivas `security.py` nuevas y sin tocar las existentes, gates limpios)
  verificadas de forma independiente por el subagente (incl. re-ejecutando `mypy`/`ruff`).

## Docs actualizadas

- Docstrings de `auth_service.py` (contrato de cada rama de `refresh()`, por qué `secret`/`ttl` no se
  leen de `get_settings()`) y de `app.domain.ports.repositories.RefreshSessionRepository.revoke_by_hash`
  (idempotencia, qué no revela). Session log (este fichero).
