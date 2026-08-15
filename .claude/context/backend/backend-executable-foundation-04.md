# Session log — backend-executable-foundation-04

Tarea: **Primitivas de seguridad sin estado** (`app/core/security.py`): hashing Argon2id + JWT access puro.
Plan: `.claude/plans/active/backend/executable-foundation.md`. Rama: `plan/backend/executable-foundation`.
Modo enseñanza (owner Python básico): explicar cada concepto (argon2-cffi, pyjwt, excepciones, `now` inyectable).

Append-only.

---

## 2026-08-15 — Arranque

- depends_on: 02 (done). Tarea movida a `active/` (`git mv`), `status: active` — patrón canónico del
  lifecycle (el session log de la 03 confirma que el repo pasa por `active/` durante el trabajo). Al cierre
  irá a `completed/`, `status: done`. Invariante "una sola active por plan" OK (01-03 done, 05-06 pending).
- Ficheros: `backend/tests/test_security.py` (tests) + `backend/app/core/security.py` (implementación,
  reemplaza el guión doc-only).
- **Surface verificado** en el venv antes de codear (honestidad):
  - argon2-cffi 25.1.0: `PasswordHasher().hash()`→`$argon2id$...`; pw incorrecta→`VerifyMismatchError`;
    hash malformado/vacío→`InvalidHashError` (hereda de `ValueError`, **no** de `VerificationError`) →
    `verify_password` fail-closed captura **ambas**.
  - pyjwt 2.13.0: `encode`→`str`; rechazos (`ExpiredSignatureError`/`InvalidSignatureError`/
    `InvalidAlgorithmError`/`MissingRequiredClaimError`/`DecodeError`) todas subclase de `jwt.InvalidTokenError`.
    `alg=none` y confusión HS384→HS256 → `InvalidAlgorithmError`; secreto erróneo → `InvalidSignatureError`.
    Secreto ≥32 bytes en tests evita `InsecureKeyLengthWarning`.
- Diseño JWT: primitivas puras (secret/algorithm/ttl/now por parámetro). `decode` fija `algorithms=[algorithm]`
  y valida `exp` **manualmente** contra `now` inyectado (pyjwt no acepta `now`), frontera `now >= exp → expirado`.

## 2026-08-15 — TDD de security.py (owner escribe código; asistente guía/explica)

Implementado `app/core/security.py` por TDD, escenario por escenario (22 tests en `tests/test_security.py`).

### Hashing (Argon2id, `argon2-cffi`)
- `hash_password` → `_hasher.hash()` (`PasswordHasher()` a nivel de módulo; solo fija coste, sin efectos en
  import). `verify_password` fail-closed: `try _hasher.verify() except (VerificationError, InvalidHashError)`
  → `False`. Los dos `except` son necesarios: `InvalidHashError` hereda de `ValueError`, no de `VerificationError`.
- Escenarios: oculta/verifica correcta/incorrecta/salt/malformado-fail-closed/vacía-clase-propia.

### JWT access (puro, `pyjwt` HS256)
- `create_access_token(sub, tenant_id, *, secret, algorithm, ttl, now)`: claims `sub`/`tenant_id`/`iat`(=now)/
  `exp`(=now+ttl), sin capacidades (A1.7/FR-005). `now: datetime` aware; `iat/exp` = segundos Unix.
- `decode_access_token(token, *, secret, algorithm, now=None)`: `jwt.decode` con `algorithms=[algorithm]`
  (rechaza alg=none/confusión, verificado que ambas → `InvalidAlgorithmError`) + `options={"require":
  ["exp","sub","tenant_id"], "verify_exp": False}`. Expiración **manual** contra `now` (o reloj real si None):
  `if current >= claims["exp"]: raise ExpiredSignatureError` → frontera `now == exp` = expirado.
- Escenarios: round-trip/exp=now+ttl/firma-inválida/alg=none/confusión/no-JWT(parametrize)/claim-ausente/
  expirado/Outline-frontera(-1 válido, 0/+1 expirado) + 2 extras rama `now=None` (márgenes de siglos,
  deterministas) + 2 de contrato keyword-only.

### Gate de mutation (cosmic-ray)
- Scope acotado en `cosmic-ray.toml` → `module-path=app/core/security.py`, `test-command=…tests/test_security.py`.
- 1er run: 57 mutantes, **2 supervivientes (3.51% ≤ 20, gate verde)**. Los 2 = el `*` keyword-only de las
  firmas (`pos=[35,4]`/`[50,4]`): cosmic-ray lo lee como multiplicación; todas las mutaciones dan sintaxis
  inválida (killed) **salvo** `*`→`/`, que es válida (marcador *positional-only* PEP 570) → survived. Matables
  pinando el contrato keyword-only (el spec fija esas firmas) → añadidos 2 tests de contrato
  (`…_secret_is_keyword_only`, `pytest.raises(TypeError)` al pasar `secret` por posición).
- 2º run: 59 mutantes, **0 supervivientes (0.00%)**.

### Verificación (salida real, esta sesión)
- `make test`/pytest full → **41 passed** · `ruff check` (incl. `S`) + `ruff format --check` → limpios ·
  `mypy app` strict → Success (79 ficheros). `make mutation` → survival 0.00%, gate verde.
- Limpieza de imports: `ruff --fix` (UP017 `timezone.utc`→`from datetime import UTC`; I001 orden; F811 duplicado).

### Traza SDD (DoD — "sin cambios de spec/CU")
- Primitivas puras de infra → **Gherkin local**, sin CU nuevo. Traza (no enlace 1:1):
  - `hash_password`/`verify_password` → **FR-008** (fijar contraseña Argon2id) y **CU-BE-02** (canje de token
    fija contraseña); **NFR-001** (Argon2id).
  - `create_access_token`/`decode_access_token` → **FR-001** (login emite access, TTL corto, **sin
    capacidades** embebidas) y **CU-BE-01** (login→access). El wiring a `get_settings()` (secreto/ttl) es del
    **plan de auth**, no de esta tarea.

## Follow-ups
- **Política de contraseña** (longitud/fuerza) → diferida al **plan de auth/producto** (primitiva pura aquí).
- El wiring de `security.py` a `get_settings()` + refresh/rotación/logout/one-time tokens → **plan de auth**
  (posterior a la capa DB).
