---
id: backend-executable-foundation-06
package: backend
plan: executable-foundation
status: pending
priority: 1
depends_on: [backend-executable-foundation-03, backend-executable-foundation-05]
estimate: 3h
actual:
created: 2026-08-14
updated: 2026-08-14
---

# App factory + /health/live + CORS + envelope problem+json (app/main.py)

## Description

Ensambla la aplicación FastAPI (**composición**): `create_app()` valida settings, configura logging,
monta middleware (request-id + CORS) y los handlers de error **problem+json** (incl. **i18n por
`Accept-Language`**), y expone `GET /health/live`. Cierra el plan → deja un esqueleto de API ejecutable
(`make run`). Guión: `backend/app/main.py`; specs: envelope problem+json (`api-contract.md`, RFC 9457),
NFR-003, NFR-007 (i18n). Tests de **integración** con `httpx.ASGITransport` (app en proceso, sin servidor ni DB).

## Spec

- `create_app() -> FastAPI`: valida settings (`get_settings()` — si son inválidas, **falla en el arranque**
  con error claro), llama a `configure_logging`, monta el **middleware de request-id** (tarea 05) —
  aplicado a **todas** las respuestas, incluidas las de error — y `CORSMiddleware`, registra los handlers
  de error, monta `GET /health/live`. Exporta `app = create_app()`.
- **CORS**: orígenes de `settings.cors_origins`. En `development` con `cors_origins` vacío → permisivo
  (`allow_origins=["*"]`); en otro caso, solo los orígenes listados.
- **Handlers de error → `application/problem+json`** (`{type, title, status, detail, errors[]}`):
  - `HTTPException`/`StarletteHTTPException` (incl. **404** y **405**) → problem+json.
  - `RequestValidationError` → **422** con `errors[]` (`field`/`message`/`code`).
  - `Exception` no controlada → **500** problem+json (no traza por defecto de FastAPI/Starlette).
  - **i18n**: `title`/`detail` se localizan según `Accept-Language` (base + al menos un idioma alterno;
    fallback al idioma base si no hay match) — NFR-007 / `api-contract.md`.
- `GET /health/live` → **200** con cuerpo de estado vivo; **no** toca DB ni dependencias externas.
- `/health/ready` y el alias `/health` **no existen** en este plan → responden **404 limpio** (no 500).
- **Sin efectos en import**: nada de clientes/conexiones al importar; la validación de settings ocurre en el factory.
- Documentar (docstring/README) que `/health/ready` + alias `/health` llegan en el plan de capa DB.

## Fuera de alcance

- `/health/ready` + alias `/health` (DB + pgvector → plan de capa DB); el `HEALTHCHECK` del servicio `api`
  seguirá rojo hasta entonces (aviso conocido, F2).
- Routers de negocio, throttling de `/auth/*`, `/metrics`, hook Sentry (planes posteriores).
- `deps.py` real (DB session / tenant / subject / require_capability).

## Scenarios (Gherkin)

<!-- SDD: infra/composición sin CU de actor → Gherkin LOCAL, "sin cambios de spec/CU". Ancla el envelope
     problem+json (api-contract.md, RFC 9457) + NFR-003/007. Integración vía httpx.ASGITransport. Cierra
     el end-to-end del request-id middleware de la 05. Endurecido por scenario-coverage: 422/500, request-id
     en errores, settings inválidas, 404/405 limpios, i18n, lazo de correlación. -->

```gherkin
Feature: app factory, liveness y envelope de error

  Scenario: la app se construye con settings inyectados
    Given settings de test válidas
    When se llama a `create_app()`
    Then devuelve una instancia FastAPI sin tocar red ni DB

  Scenario: settings inválidas fallan en el arranque
    Given settings a las que les falta un campo requerido
    When se llama a `create_app()`
    Then falla con un error claro (no arranca a medias)

  Scenario: liveness responde sin tocar dependencias
    When se hace `GET /health/live`
    Then el código es 200 And el cuerpo indica estado vivo

  Scenario: la respuesta propaga un request-id generado
    Given una petición sin header `X-Request-ID`
    When se hace `GET /health/live`
    Then la respuesta incluye un header `X-Request-ID` no vacío

  Scenario: la respuesta respeta el request-id entrante
    Given una petición con `X-Request-ID: abc-123`
    When se hace `GET /health/live`
    Then la respuesta devuelve `X-Request-ID: abc-123`

  Scenario: correlación end-to-end (log ↔ header)
    Given una petición real a `/health/live`
    When se procesa
    Then la línea de log emitida contiene el mismo `request_id` que el header `X-Request-ID` de la respuesta

  Scenario: ruta desconocida devuelve problem+json con request-id
    When se hace `GET /ruta-inexistente`
    Then el código es 404 And el content-type es `application/problem+json`
    And el cuerpo cumple el envelope `{type, title, status, detail}` And la respuesta lleva `X-Request-ID`

  Scenario: error de validación devuelve 422 problem+json con errors[]
    Given un endpoint con validación de entrada
    When se invoca con un body/params inválidos
    Then el código es 422 And el cuerpo problem+json incluye `errors[]` con field/message/code

  Scenario: excepción no controlada devuelve 500 problem+json
    Given un endpoint que lanza una excepción no capturada
    When se invoca
    Then el código es 500 And el cuerpo es problem+json (no la traza por defecto)

  Scenario: método no permitido devuelve 405 problem+json
    When se hace `POST /health/live`
    Then el código es 405 And el cuerpo es problem+json

  Scenario Outline: /health/ready y /health responden 404 limpio mientras están diferidos
    When se hace `GET <ruta>`
    Then el código es 404 (no 500) And el cuerpo es problem+json

    Examples:
      | ruta           |
      | /health/ready  |
      | /health        |

  Scenario Outline: title/detail se localizan por Accept-Language
    Given una request de error con `Accept-Language: <lang>`
    When se genera el envelope problem+json
    Then `title` viene en <idioma resultante>

    Examples:
      | lang  | idioma resultante        |
      | es    | español (base)           |
      | en    | inglés                   |
      | fr    | idioma base (fallback)   |

  Scenario: CORS refleja un origen permitido
    Given `CORS_ORIGINS` incluye `https://app.example`
    When llega un preflight CORS desde ese origen a `/health/live`
    Then la respuesta autoriza el origen (`Access-Control-Allow-Origin`)

  Scenario: CORS no refleja un origen no permitido
    Given `APP_ENV=production` y `CORS_ORIGINS` sin `https://malo.example`
    When llega un preflight CORS desde ese origen
    Then la respuesta no autoriza ese origen

  Scenario: CORS permisivo en development sin orígenes configurados
    Given `APP_ENV=development` y `CORS_ORIGINS` vacío
    When llega un preflight CORS desde cualquier origen
    Then la respuesta lo autoriza (permisivo en dev)
```

## Provides

`create_app()` (fábrica testeable) y `app` (instancia para uvicorn/Docker): el esqueleto de API ejecutable
sobre el que los planes de routers montarán sus endpoints. Cierra el plan `executable-foundation`.

## Definition of Done

- [ ] Tests escritos ANTES de la implementación (Red → Green → Refactor).
- [ ] Cada escenario Gherkin tiene al menos un test (construcción, settings inválidas, liveness, request-id gen/echo/en-error, correlación e2e, 404/422/500/405 problem+json, /health(/ready) 404 limpio, i18n Accept-Language, CORS permitido/denegado/dev-permisivo).
- [ ] Todos los tests en verde (`make test`, integración `httpx.ASGITransport`).
- [ ] `Provides` disponible: `create_app()`/`app` arrancan sin efectos en import.
- [ ] `ruff check` + `ruff format --check` + `mypy` strict OK.
- [ ] Gate de mutation `mutmut` (`break: 80`) sobre `app/main.py`.
- [ ] Gate `/sdd-lint` sin ERROR (SDD: sin cambios de CU — infra/composición).
- [ ] Gate de `fact-checker`.
- [ ] Documentación: docstrings; nota en `backend/README.md` sobre `/health/live` (y `/health/ready` diferido) + i18n del envelope; session log.
- [ ] Cierre del plan: última tarea → PR de `plan/backend/executable-foundation` a `main` (auto-pr; git-automation).

<!-- github-tracking off. Sin changeset (backend). -->
