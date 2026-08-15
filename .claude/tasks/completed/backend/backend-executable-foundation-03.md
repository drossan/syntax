---
id: backend-executable-foundation-03
package: backend
plan: executable-foundation
status: done
priority: 1
depends_on: [backend-executable-foundation-02]
estimate: 2.5h
actual: ~4h
created: 2026-08-14
updated: 2026-08-15
---

# Settings inyectables + CORS_ORIGINS (app/core/config.py)

## Description

Primera tarea de **código real (TDD)**. Implementa la configuración por entorno **inyectable y sin
efectos en import**, base de todas las capas. Es también el **shakeout del toolchain de mutation** (primer
gate real; `mutmut` no puntuó → se adoptó **cosmic-ray**, ADR-0014). Guión: `backend/app/core/config.py`;
spec: NFR-003, `IMPLEMENTATION-GUIDE` §3.

## Spec

- `class Settings(BaseSettings)` (pydantic-settings v2) con los campos de `.env.example`: `APP_ENV`;
  `DATABASE_URL`; `JWT_SECRET`/`JWT_ALGORITHM`/`JWT_ACCESS_TTL`/`JWT_REFRESH_TTL`; `LLM_PROVIDER`/
  `OPENAI_API_KEY`/`CHAT_MODEL`/`EMBEDDING_MODEL`/`EMBEDDING_DIM`; `LANGSMITH_*`; límites B.1
  (`LOGIN_MAX_ATTEMPTS`, `LOGIN_WINDOW_SECONDS`, `AI_DRAFT_MAX_PER_TICKET`) con defaults; y **`CORS_ORIGINS`**.
- `model_config = SettingsConfigDict(env_file=".env", extra="ignore")`.
- `get_settings() -> Settings` con `@lru_cache` (una instancia perezosa por proceso).
- **Sin efectos en import**: no instanciar `Settings()` a nivel de módulo; nada de clientes/validación al importar.
- **`CORS_ORIGINS`**: acepta cadena separada por comas del entorno y la normaliza a `list[str]` — **strip**
  de cada origen, **descarta vacíos**, **deduplica preservando orden**.
- Tipos correctos: `EMBEDDING_DIM`/`JWT_*_TTL`/límites B.1 son `int`; un valor no parseable → error de validación.
- **Aislamiento de tests** (transversal): añadir a `backend/tests/conftest.py` una fixture (autouse) que
  haga `get_settings.cache_clear()` alrededor de cada test, para que cada test inyecte sus settings sin
  contaminación del `lru_cache` entre suites (lo necesitan 05 y 06).

## Fuera de alcance

- Uso de las settings (logging, factory → 05/06); validación en el arranque (factory, 06).
- Secretos reales; clientes DB/OpenAI.

## Scenarios (Gherkin)

<!-- SDD: infra transversal sin CU de actor → Gherkin LOCAL, "sin cambios de spec/CU". Ancla NFR-003
     (hexagonal / settings inyectables) + el guión de config.py. Endurecido por scenario-coverage. -->

```gherkin
Feature: configuración por entorno inyectable

  Scenario: importar el módulo no tiene efectos
    Given un entorno sin `.env` ni variables requeridas
    When se importa `app.core.config`
    Then la importación no lanza error ni lee el entorno (Settings no se instancia en import)

  Scenario: get_settings devuelve una instancia cacheada
    Given el proceso arrancado
    When se llama a `get_settings()` dos veces
    Then devuelve la misma instancia (identidad)

  Scenario: las settings reflejan el entorno inyectado
    Given un entorno de test con los campos requeridos fijados (DATABASE_URL, JWT_SECRET, JWT_ALGORITHM, LLM_PROVIDER, OPENAI_API_KEY, CHAT_MODEL, EMBEDDING_MODEL, JWT_ACCESS_TTL=900, EMBEDDING_DIM=1536)
    When se resuelven las settings
    Then cada campo refleja su valor de entorno And `jwt_access_ttl == 900` (int) And `embedding_dim == 1536` (int)

  Scenario: tipo inválido produce error de validación
    Given `JWT_ACCESS_TTL="abc"` (no numérico) en el entorno
    When se resuelven las settings
    Then se produce un error de validación claro

  Scenario: variable de entorno desconocida no rompe (extra=ignore)
    Given una variable desconocida `FOO=bar` en el entorno
    When se resuelven las settings
    Then no falla And `FOO` no aparece como campo

  Scenario Outline: defaults de los límites B.1 cuando no vienen en el entorno
    Given un entorno sin `<var>`
    When se resuelven las settings
    Then `<campo>` toma su valor por defecto documentado

    Examples:
      | var                  | campo                  |
      | LOGIN_MAX_ATTEMPTS   | login_max_attempts     |
      | LOGIN_WINDOW_SECONDS | login_window_seconds   |
      | AI_DRAFT_MAX_PER_TICKET | ai_draft_max_per_ticket |

  Scenario: un límite B.1 se puede sobreescribir por entorno
    Given `LOGIN_MAX_ATTEMPTS=9` en el entorno
    When se resuelven las settings
    Then `login_max_attempts == 9` (no el default)

  Scenario Outline: CORS_ORIGINS se normaliza a lista (strip + drop vacíos + dedup)
    Given `CORS_ORIGINS=<entrada>` en el entorno
    When se resuelven las settings
    Then `cors_origins == <esperado>`

    Examples:
      | entrada                                | esperado                          |
      | (var ausente)                          | []                                |
      | (var presente, cadena vacía)           | []                                |
      | https://a.com                          | ["https://a.com"]                 |
      | " https://a.com , https://b.com "      | ["https://a.com","https://b.com"] |
      | https://a.com,https://a.com            | ["https://a.com"]                 |
```

## Provides

`Settings` y `get_settings()` (cacheada, inyectable, con fixture de reset en conftest) — consumidos por
logging (05), la app factory (06) y todas las capas posteriores; `cors_origins` normalizado para el
`CORSMiddleware` de la 06.

## Definition of Done

- [x] Tests escritos ANTES de la implementación (Red → Green → Refactor).
- [x] Cada escenario Gherkin tiene al menos un test (feliz + bordes: import sin entorno, tipo inválido, extra=ignore, defaults/override B.1, CORS ausente/vacío/uno/espacios/duplicados).
- [x] Todos los tests en verde (`make test`).
- [x] `Provides` disponible: `get_settings()` inyectable sin efectos en import + fixture de reset del `lru_cache` en `conftest.py`.
- [x] `ruff check` + `ruff format --check` + `mypy` strict OK.
- [x] Gate de mutation `cosmic-ray` (`make mutation`, survival ≤ 20% = score ≥ 80) sobre `app/core/config.py` — score **91.7%**, 1 mutante **equivalente** documentado (`@classmethod` sin uso de `cls`).
- [x] Gate `/sdd-lint` sin ERROR (SDD: sin cambios de CU — infra; anclada a NFR-003).
- [x] Gate de `fact-checker` (tras mutation, antes de commit/resumen).
- [x] Documentación: docstrings en `Settings`/`get_settings`; session log.

<!-- github-tracking off → sin línea de proyección. Sin changeset (backend). -->
