# 0015. Backend: observabilidad con structlog + request-id por contextvars

- **Estado**: accepted
- **Fecha**: 2026-08-15
- **Decisores**: Owner.
- **Contexto SDD**: materializa NFR-004 (observabilidad: logging estructurado con request-id por request).

## Contexto y planteamiento del problema

El backend necesita **logs estructurados** (máquina-legibles en prod, humano-legibles en dev) y un
**identificador de correlación por petición** (`request-id`) que aparezca en **todos** los logs de esa
request, para poder seguir una petición extremo a extremo. En un servidor `async` con peticiones
concurrentes, un id global mutable se contamina entre requests: el estado por-request debe ser
**task-local** (`contextvars`), no un singleton.

## Decision drivers

- Salida **estructurada** conmutable por entorno (JSON en prod/test, consola legible en development).
- **Correlación** por request sin fugas entre peticiones concurrentes (async-safe).
- **Sin efectos en import** (config invocada desde `create_app()`), **idempotente** (no duplica salida).
- No loguear secretos/PII.

## Opciones consideradas

- **Opción 1** — `structlog` + `structlog.contextvars` (merge_contextvars) para el request-id, con un
  middleware ASGI que fija/sanea/ecoa `X-Request-ID`.
- **Opción 2** — `logging` de la stdlib con un `Formatter` JSON propio + `logging.Filter` que inyecta el
  request-id desde un `ContextVar` manual.
- **Opción 3** — `loguru`: API simple, pero opinado, menos control del pipeline de processors y otra
  dependencia grande.

## Resultado de la decisión

Elegida: **Opción 1 (`structlog`)**. Pipeline de processors: `merge_contextvars` → `add_log_level` →
`TimeStamper(iso)` → renderer (`JSONRenderer` si `APP_ENV != development`, si no `ConsoleRenderer`).
`logger_factory=PrintLoggerFactory()` (escribe a `sys.stdout`, resuelto en tiempo de escritura → testeable
con `capsys`; **sin handlers de la stdlib**, por lo que `configure_logging` es idempotente por
construcción). El request-id se guarda en los **contextvars de structlog** (`bind`/`bound_contextvars`),
task-local y async-safe; `get_request_id()` lo lee con `get_contextvars()`. El middleware
`RequestIDMiddleware`: lee `X-Request-ID` entrante, lo **sanea** (elimina no-imprimibles/CR-LF para evitar
log/header injection, recorta a 128), o genera `uuid4`; lo bindea durante la request (reset al salir vía
`bound_contextvars`, sin fuga a la siguiente) y lo ecoa en la respuesta.

### Confirmación

`backend/app/core/logging.py` + `backend/tests/test_logging.py` (TDD, gate mutation cosmic-ray) — tarea
`backend-executable-foundation-05`. El montaje del middleware en la app factory y el test HTTP e2e del echo
llegan en `backend-executable-foundation-06`.

## Consecuencias

- **Buenas**: logs estructurados conmutables por entorno; correlación async-safe sin singletons; config pura
  e idempotente; saneado anti-inyección del id entrante.
- **Malas / coste**: dependencia de runtime (`structlog`); la integración de los logs de uvicorn/stdlib
  (unificar formato) queda **diferida**; la propagación de contextvars de `BaseHTTPMiddleware` al handler se
  valida en integración (06) — si no propaga, se pasará a middleware ASGI puro.
- **Fuera de alcance** (planes posteriores): hook Sentry / métricas, y el enlace `langsmith_trace_url` del
  flujo-IA.

## Pros y contras de las opciones

- **Opción 1**: 👍 processors componibles, contextvars async-safe, testeable, idempotente · 👎 dependencia extra.
- **Opción 2**: 👍 sin dependencias nuevas · 👎 más boilerplate (Formatter+Filter), fácil de romper la idempotencia con handlers.
- **Opción 3**: 👍 API mínima · 👎 opinado, menos control del pipeline, dependencia grande.
