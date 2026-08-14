---
id: backend-executable-foundation-04
package: backend
plan: executable-foundation
status: pending
priority: 1
depends_on: [backend-executable-foundation-02]
estimate: 2.5h
actual:
created: 2026-08-14
updated: 2026-08-14
---

# Primitivas de seguridad sin estado: Argon2id + JWT access (app/core/security.py)

## Description

Primitivas de **identidad puras y sin estado**: hashing de contraseñas (Argon2id) y JWT de acceso.
**No** deciden autorización (eso es RBAC/dominio), **no** tocan DB, y **no** leen config: reciben lo que
necesitan **por parámetro** (decisión de diseño 2026-08-14 — más testeable/hexagonal; el wiring a
`get_settings()` lo hace el servicio de auth en su plan). Guión: `backend/app/core/security.py`; specs:
FR-001, FR-008, NFR-001. Consumidas por `CU-BE-01` (login → access) y `CU-BE-02` (fijar contraseña
Argon2id) — se **trazan**, no se enlazan 1:1 (el CU necesita DB/endpoints, fuera de alcance).

## Spec

- **Hashing (Argon2id, `argon2-cffi`)**: `hash_password(password: str) -> str` (salt aleatorio, esquema
  `argon2id`); `verify_password(password: str, hash: str) -> bool`. **Fail-closed**: un hash malformado
  (no-Argon2id / vacío) → `False`, no excepción propagada. Nunca almacenar la contraseña en claro.
- **JWT access puro (`pyjwt`, HS256)**:
  - `create_access_token(sub, tenant_id, *, secret, algorithm, ttl, now) -> str` con claims `sub`,
    `tenant_id`, `iat`, `exp` (= `now + ttl`). **NO** incluye capacidades (A1.7/FR-005).
  - `decode_access_token(token, *, secret, algorithm, now=None) -> claims` — **fija
    `algorithms=[algorithm]`** en `jwt.decode` (rechaza `alg=none` y confusión de algoritmo); verifica
    firma; verifica `exp` contra `now` (inyectable → expiración determinista); exige `sub` y `tenant_id`
    presentes; lanza en inválido/expirado/malformado.
- **Determinismo** (testing.md §5): `now` inyectable en creación y decodificación.
- **Política de contraseña** (longitud/fuerza): **fuera de alcance** — diferida al plan de auth/producto
  (no hay requisito fijado en specs). `hash_password` hashea lo que reciba.

## Fuera de alcance

- Refresh tokens, rotación, reuse-detection, `logout` server-side, `auth_token` de un solo uso (necesitan
  la tabla `refresh_session`/`auth_token` → plan de auth).
- Autorización por capacidad/ámbito (RBAC, dominio); resolución de capacidades.
- Lectura de `get_settings()` (el wiring lo hace el llamador en el plan de auth).
- Política de validación de contraseña (longitud mínima, etc.) → plan de auth/producto.
- Persistencia; endpoints de auth.

## Scenarios (Gherkin)

<!-- SDD: primitivas de infra. Gherkin LOCAL ("sin cambios de spec/CU") con TRAZA explícita a
     FR-001/FR-008 y a CU-BE-01/CU-BE-02 como flujos consumidores. Endurecido por scenario-coverage:
     alg=none, confusión de algoritmo, malformado, claims requeridos, exp positivo, fail-closed. -->

```gherkin
Feature: primitivas de seguridad sin estado

  # ── Hashing (Argon2id) ──
  Scenario: el hash oculta la contraseña
    Given la contraseña "s3cr3t!"
    When se calcula su hash
    Then el hash difiere del texto plano And usa el esquema Argon2id

  Scenario: verificación con la contraseña correcta
    Given el hash de "s3cr3t!"
    When se verifica "s3cr3t!" contra ese hash
    Then la verificación es verdadera

  Scenario: verificación con la contraseña incorrecta
    Given el hash de "s3cr3t!"
    When se verifica "otra" contra ese hash
    Then la verificación es falsa

  Scenario: dos hashes de la misma contraseña difieren (salt)
    Given la contraseña "s3cr3t!"
    When se hashea dos veces
    Then los dos hashes difieren And ambos verifican correctamente

  Scenario: verificación fail-closed contra hash malformado
    Given un hash malformado (cadena vacía o texto que no es Argon2id)
    When se verifica cualquier contraseña contra ese hash
    Then la verificación es falsa (sin propagar excepción)

  Scenario: contraseña vacía se hashea y verifica como clase propia
    Given la contraseña ""
    When se hashea y luego se verifica "" contra el hash
    Then la verificación es verdadera And verificar cualquier no-vacía es falsa

  # ── JWT access (puro) ──
  Scenario: round-trip de claims
    Given un sujeto y su tenant, con secreto/algoritmo/ttl/now dados
    When se emite un access token y se decodifica con el mismo secreto/algoritmo
    Then `sub` y `tenant_id` coinciden con los de origen And no hay claim de capacidades

  Scenario: exp se calcula desde now + ttl
    Given `now = T` y `ttl = 900`
    When se emite un access token
    Then su claim `exp` es `T + 900`

  Scenario: firma inválida se rechaza
    Given un token firmado con otro secreto
    When se decodifica
    Then se produce un error de firma

  Scenario: alg=none se rechaza
    Given un token con header `{"alg":"none"}` y sin firma
    When se decodifica exigiendo `algorithms=["HS256"]`
    Then se produce un error (no se acepta como válido)

  Scenario: confusión de algoritmo se rechaza
    Given un token estructuralmente válido firmado con un algoritmo distinto al configurado (p.ej. HS384)
    When se decodifica exigiendo el algoritmo configurado (HS256)
    Then se produce un error

  Scenario: cadena que no es un JWT se rechaza
    Given la cadena "no.es.jwt" (o "")
    When se decodifica
    Then se produce un error de parseo

  Scenario: token sin claim requerido se rechaza
    Given un token válido y bien firmado pero sin `tenant_id`
    When se decodifica
    Then se produce un error (claims requeridos ausentes)

  Scenario: token expirado se rechaza (now inyectado)
    Given un token con `exp` anterior al `now` inyectado en la decodificación
    When se decodifica
    Then se produce un error de expiración

  Scenario Outline: frontera de expiración exacta
    Given un token cuyo `exp` es <exp> respecto al `now` de decodificación
    When se decodifica
    Then el resultado es <resultado>

    Examples:
      | exp             | resultado |
      | 1s en el futuro | válido    |
      | igual a now     | expirado  |
      | 1s en el pasado | expirado  |
```

## Provides

`hash_password`, `verify_password`, `create_access_token`, `decode_access_token` (puras) — consumidas por
el plan de **auth** (login/refresh) cuando exista la capa DB, que les inyectará secreto/algoritmo/ttl
desde `get_settings()`. No las usa ninguna otra tarea de este plan.

## Definition of Done

- [ ] Tests escritos ANTES de la implementación (Red → Green → Refactor).
- [ ] Cada escenario Gherkin tiene al menos un test (hashing feliz/incorrecto/salt/malformado/vacío; JWT round-trip/exp/firma/alg=none/confusión/parseo/claims/expiración/frontera).
- [ ] Todos los tests en verde (`make test`).
- [ ] `Provides` disponible; `exp` y expiración testeados con `now` inyectado (determinismo); `decode` fija `algorithms=[algorithm]`.
- [ ] `ruff check` (incl. `S` bandit) + `ruff format --check` + `mypy` strict OK.
- [ ] Gate de mutation `mutmut` (`break: 80`) sobre `app/core/security.py`.
- [ ] Gate `/sdd-lint` sin ERROR (SDD: sin cambios de CU; **traza a FR-001/FR-008 + CU-BE-01/02 documentada** en el session log).
- [ ] Gate de `fact-checker`.
- [ ] Documentación: docstrings (intención, params, returns, errores); session log con la traza a los CU consumidores + follow-up "política de contraseña → plan de auth".

<!-- github-tracking off. Sin changeset (backend). -->
