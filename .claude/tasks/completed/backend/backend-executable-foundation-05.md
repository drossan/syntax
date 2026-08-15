---
id: backend-executable-foundation-05
package: backend
plan: executable-foundation
status: done
priority: 1
depends_on: [backend-executable-foundation-03]
estimate: 2.5h
actual: ~2.5h
created: 2026-08-14
updated: 2026-08-15
---

# Logging estructurado (structlog) + request-id + ADR-0015 (app/core/logging.py)

## Description

Observabilidad transversal: logging **estructurado** con `structlog` y un **request-id** correlacionable
por petición (`contextvar` + middleware). Guión: `backend/app/core/logging.py`; spec: NFR-004. Registra
la elección de `structlog` en **ADR-0015**. El echo HTTP de extremo a extremo se prueba en integración en
la tarea 06; aquí, unidad (invocando el dispatch del middleware con `request`/`call_next` dobles).

## Spec

- `configure_logging(settings)`: configura `structlog` — renderer **JSON** cuando `APP_ENV != development`,
  renderer de consola legible en `development`. **Sin efectos en import** (se llama desde `create_app()`).
  **Idempotente**: llamarlo dos veces no duplica handlers ni emite logs por duplicado.
- **request-id**: un `contextvar` con el id de correlación; un **middleware** que:
  - lee el header entrante `X-Request-ID`, y si viene, lo **sanea** (recorta a un máximo — p.ej. 128 chars —
    y **elimina CR/LF y caracteres de control**; si tras sanear queda vacío → genera uno);
  - si no viene (o queda vacío), **genera** un uuid4;
  - fija el id en el `contextvar`, lo **bindea** a structlog (`bind_contextvars`) y lo añade a la respuesta
    (`X-Request-ID`);
  - **resetea** el `contextvar` al terminar la request (no fuga a la siguiente en el mismo worker).
- `get_request_id() -> str | None`.
- Un processor de structlog inyecta el `request_id` en **cada** log de la request.
- **No** loguear secretos/PII (tokens, `Authorization`, cookies, contraseñas).
- ADR-0015 (structlog/observabilidad, MADR).

## Fuera de alcance

- Montaje del middleware en la app (factory, 06) y el test HTTP end-to-end del echo (06).
- Hook Sentry / métricas / enlace `langsmith_trace_url` (planes posteriores).

## Scenarios (Gherkin)

<!-- SDD: infra transversal sin CU de actor → Gherkin LOCAL, "sin cambios de spec/CU". Ancla NFR-004 +
     guión de logging.py. Crea ADR-0015 (MADR), validado por /sdd-lint. Endurecido por scenario-coverage:
     concurrencia, idempotencia, CRLF, id gigante/vacío, reset del contextvar, no-PII. -->

```gherkin
Feature: logging estructurado con request-id correlacionable

  Scenario: cada log lleva el request-id del contexto
    Given un `request_id` fijado en el contextvar
    When se emite un log estructurado
    Then la salida (JSON) contiene ese `request_id`

  Scenario: sin contexto, no hay request-id
    Given ninguna request en curso
    When se consulta `get_request_id()`
    Then devuelve `None`

  Scenario: el middleware genera un id cuando no viene
    Given una request sin header `X-Request-ID`
    When pasa por el middleware de correlación
    Then se fija un id (uuid) en el contextvar And la respuesta incluye el header `X-Request-ID`

  Scenario: el middleware respeta el id entrante válido
    Given una request con `X-Request-ID: abc-123`
    When pasa por el middleware de correlación
    Then `get_request_id()` es "abc-123" And la respuesta devuelve `X-Request-ID: abc-123`

  Scenario: id entrante vacío se trata como ausente
    Given una request con `X-Request-ID:` (presente pero vacío)
    When pasa por el middleware
    Then se genera un id nuevo (no se usa el vacío)

  Scenario: id entrante con CRLF se sanea (no header/log injection)
    Given una request con `X-Request-ID: "abc\r\nX-Evil: 1"`
    When pasa por el middleware
    Then el id fijado y ecoado no contiene CR/LF ni caracteres de control

  Scenario: id entrante desmesurado se recorta
    Given una request con `X-Request-ID` de 10.000 caracteres
    When pasa por el middleware
    Then el id fijado/ecoado se recorta al máximo permitido

  Scenario: dos requests async concurrentes no se contaminan
    Given dos requests en vuelo con `X-Request-ID` distintos ("a" y "b")
    When ambas se procesan concurrentemente
    Then cada una conserva su propio id (el contextvar no filtra entre ellas)

  Scenario: el contextvar se resetea al terminar la request
    Given una request que fijó un `request_id`
    When la request termina
    Then una consulta posterior fuera de request devuelve `None` (no queda el id viejo)

  Scenario: configure_logging es idempotente
    Given `configure_logging(settings)` ya llamado una vez
    When se llama una segunda vez y se emite un log
    Then el log se emite una sola vez (sin handlers duplicados)

  Scenario Outline: el renderer depende del entorno
    Given `APP_ENV=<env>`
    When se configura el logging y se emite un log
    Then el formato de salida es <formato>

    Examples:
      | env         | formato   |
      | production  | JSON      |
      | test        | JSON      |
      | development | consola   |
```

## Provides

`configure_logging(settings)`, el middleware de request-id (con saneado/reset) y `get_request_id()` —
montados por la app factory (06) y usados por todas las capas que logueen.

## Definition of Done

- [x] Tests escritos ANTES de la implementación (Red → Green → Refactor).
- [x] Cada escenario Gherkin tiene al menos un test (log lleva id; None sin contexto; genera/respeta/vacío/CRLF/gigante; concurrencia; reset; idempotencia; JSON vs consola por APP_ENV). — 14 tests en `tests/test_logging.py`.
- [x] Todos los tests en verde (`make test`). — 55 passed (suite completa).
- [x] `Provides` disponible; sin efectos en import; `configure_logging` idempotente.
- [x] `ruff check` + `ruff format --check` + `mypy` strict OK.
- [x] Gate de mutation **`cosmic-ray`** (`fail-over 20` = `break: 80`; ADR-0014, supersede `mutmut`) sobre `app/core/logging.py` → survival **4.08%** (2 supervivientes equivalentes documentados: `is not` por interning + `cache_logger_on_first_use` flag de rendimiento).
- [x] Gate `/sdd-lint` sin ERROR (SDD: sin cambios de CU — infra; ADR-0015 MADR bien formado). AVISO menor (Then compuesto) reconocido.
- [x] Gate de `fact-checker` — 9/9 afirmaciones VERIFICADAS.
- [x] Documentación: docstrings; **ADR-0015** (structlog/observabilidad, doc técnica) + `adr-index`; session log.

<!-- github-tracking off. Sin changeset (backend). -->
