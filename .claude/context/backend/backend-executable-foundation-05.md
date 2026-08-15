# Session log — backend-executable-foundation-05

Tarea: **Logging estructurado (structlog) + request-id + ADR-0015** (`app/core/logging.py`).
Plan: `.claude/plans/active/backend/executable-foundation.md`. Rama: `plan/backend/executable-foundation`.
Modo enseñanza (owner Python básico): explicar structlog, contextvars, middleware ASGI, tests async.

Append-only.

---

## 2026-08-15 — Arranque

- depends_on: 03 (done). Tarea movida a `active/` (`git mv`), `status: active`. Una sola active por plan OK.
- Ficheros: `backend/tests/test_logging.py` + `backend/app/core/logging.py` (reemplaza guión) + **ADR-0015**
  (`.claude/specs/adr/0015-backend-observabilidad-structlog-request-id.md`) + entrada en `adr-index.md`.
- **Spike de surface verificado** (structlog 26.1.0, starlette 1.6.0):
  - `PrintLoggerFactory()` resuelve `sys.stdout` en tiempo de escritura → `capsys` captura la salida.
  - `merge_contextvars` inyecta `request_id`; renderer `JSONRenderer` (env != development) vs
    `ConsoleRenderer(colors=False)` (development).
  - `bound_contextvars(request_id=…)` (context manager) restaura el valor previo al salir (sin previo → `None`)
    → reset del middleware. `get_contextvars().get("request_id")` para `get_request_id()`.
  - Doble `configure` → 1 línea (idempotente por construcción, sin handlers stdlib).
- Diseño: `configure_logging(settings)` structlog-only (PrintLoggerFactory), sin efectos en import;
  middleware `RequestIDMiddleware(BaseHTTPMiddleware)` con `dispatch(request, call_next)` que sanea el header
  entrante (filtra no-printable/CRLF, recorta a 128) o genera uuid4, bindea vía `bound_contextvars` y ecoa
  `X-Request-ID`. Unit test = invocar `dispatch` con `Request`/`call_next` dobles (el echo HTTP e2e → tarea 06).
- **Footgun para la 06** (a verificar en integración): la propagación de contextvars de `BaseHTTPMiddleware`
  al handler de ruta; si no propaga en Starlette 1.6.0, la 06 usará middleware ASGI puro. Aquí (unit) no aplica.

## 2026-08-15 — TDD de logging.py + gates (owner escribe código; asistente guía/explica)

Implementado `app/core/logging.py` por TDD (14 tests en `tests/test_logging.py`).

- **`configure_logging(settings)`**: pipeline structlog `merge_contextvars → add_log_level → TimeStamper(iso)
  → renderer` (`JSONRenderer` si `app_env != development`, si no `ConsoleRenderer(colors=False)`);
  `PrintLoggerFactory` + `cache_logger_on_first_use=False`. Idempotente (sin handlers stdlib). Tests con `capsys`.
- **`get_request_id()`** = `structlog.contextvars.get_contextvars().get("request_id")` → `None` fuera de request.
- **`RequestIDMiddleware(BaseHTTPMiddleware)`**: `dispatch` sanea `X-Request-ID` (`_sanitize_request_id`:
  filtra no-imprimibles con `isprintable()`, recorta a `_MAX_REQUEST_ID_LEN=128`, vacío→None) o genera
  `uuid4` (`_new_request_id`), bindea con `bound_contextvars` (reset al salir) y ecoa el header. Unit test:
  `dispatch` invocado con `Request`(scope) + `call_next` dobles.
- Escenarios: log-lleva-id / None-sin-contexto / renderer-por-env(Outline) / idempotencia / genera /
  respeta / vacío / **CRLF** (anti-inyección) / **gigante**(recorte) / **concurrencia**(async.gather, sin fuga) /
  **reset**. Verificado en spike que un header con `\r\n` llega intacto y `isprintable()` lo limpia.

### Gate de mutation (cosmic-ray, scope `logging.py` + `test_logging.py`)
- 1er run: 49 mutantes, **4 supervivientes (8.16%)**. Matados 2 (gaps reales): `colors=False`→`True` (añadido
  `assert "\x1b[" not in out` en la rama consola) y `!=`→`>` en `app_env != "development"` (añadido env
  `"ci"`→JSON, que distingue `!=` de `>`).
- 2º run: **survival 4.08% ≤ 20** (gate verde). **2 supervivientes equivalentes documentados**:
  (a) `!=`→`is not` — coincide con `!=` por *string interning* del literal (no es diferencia de comportamiento);
  (b) `cache_logger_on_first_use=False`→`True` — `structlog.configure()` resetea la caché en cada llamada →
  sin salida observable distinta (flag de rendimiento).

### Verificación (salida real, esta sesión)
- pytest full → **55 passed** · `ruff check` (+`S`) + `ruff format --check` limpios · `mypy app` strict →
  Success (79 ficheros) · `make mutation` → survival 4.08%, gate verde.
- **ADR-0015** creada (`0015-backend-observabilidad-structlog-request-id.md`, accepted) + entrada en `adr-index.md`.

## Follow-ups (a la 06)
- Montar `RequestIDMiddleware` + `configure_logging` en la app factory; **test HTTP e2e del echo** y
  **correlación log↔header**; verificar propagación de contextvars de `BaseHTTPMiddleware` al handler (si no
  propaga en Starlette 1.6.0 → middleware ASGI puro).
- Diferido: integración de logs uvicorn/stdlib, hook Sentry/métricas, enlace `langsmith_trace_url`.
