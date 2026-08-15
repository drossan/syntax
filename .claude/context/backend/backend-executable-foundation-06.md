# Session log — backend-executable-foundation-06

Tarea: **App factory + /health/live + CORS + envelope problem+json** (`app/main.py`). **Cierra el plan.**
Plan: `.claude/plans/active/backend/executable-foundation.md`. Rama: `plan/backend/executable-foundation`.
Modo: la hace el asistente entera (código + TDD + gates + cierre), a petición del owner.

Append-only.

---

## 2026-08-15 — Arranque

- depends_on: 03 + 05 (ambas done). Tarea movida a `active/`, `status: active`. Última tarea del plan.
- Ficheros: `backend/tests/test_main.py` + `backend/app/main.py` (reemplaza guión) + nota en `backend/README.md`.
- Tests de **integración** con `httpx.ASGITransport` (app en proceso, sin servidor ni DB).
- **Spike verificado** (FastAPI 0.141.1, httpx 0.28.1, Starlette 1.6.0):
  - El contextvar de `RequestIDMiddleware` (BaseHTTPMiddleware) **propaga al endpoint** en Starlette 1.6.0
    (el footgun de la 05 NO aplica aquí) → correlación log↔header funciona (log del endpoint lleva el mismo
    `request_id` que el header `X-Request-ID`).
  - `ServerErrorMiddleware` **re-lanza** la excepción tras enviar el 500 → el test de 500 usa
    `httpx.ASGITransport(app=app, raise_app_exceptions=False)` para recibir la respuesta en vez de propagar.
  - CORS: permitido→200 + `Access-Control-Allow-Origin: <origin>`; denegado(prod)→**400** sin ACAO;
    dev permisivo (`allow_origins=["*"]` + credentials)→200 + ACAO reflejado.
- Envelope problem+json (RFC 9457, `api-contract.md`): `{type, title, status, detail, errors[]}`,
  `title`/`detail` localizables por `Accept-Language` (base `es` + `en`; fallback base). i18n = NFR-007.

## 2026-08-15 — Implementación + gates (asistente, TDD)

Implementado `app/main.py` (22 tests en `tests/test_main.py`, integración `httpx.ASGITransport`).

- **`create_app(settings=None) -> FastAPI`**: valida settings (`get_settings()` si None → falla al arrancar
  si falta requerido), `configure_logging`, monta `CORSMiddleware` + `RequestIDMiddleware`, registra handlers
  problem+json (`StarletteHTTPException`/`RequestValidationError`/`Exception`), expone `GET /health/live`.
  `app = create_app()` para uvicorn.
- **problem+json**: `_problem_response` construye `{type, title, status, detail, (errors[])}` con
  `media_type="application/problem+json"`; `_negotiate_language` (base `es`, alterno `en`, fallback base);
  422 mapea `RequestValidationError.errors()` → `errors[]` (field/message/code). Handlers tipados `exc: Exception`
  + `cast` (evita el S101 de `assert` y la contravarianza que rompería mypy strict).
- **CORS**: `development` + `cors_origins` vacío → `allow_origins=["*"]`; si no, solo los listados.
- Escenarios: build / settings-inválidas-fallan / liveness / request-id gen/echo / **correlación e2e
  log↔header** / 404 / 422+errors[] / 500 / 405 / `/health(/ready)` 404 limpio(Outline) / **i18n Accept-Language**
  (Outline: es/en/fr-fallback + `en;q=0.9` + `en-US`) / CORS permitido/denegado/dev-permisivo/**no-dev-no-permisivo**.

### Gate de mutation (cosmic-ray, scope `main.py` + `test_main.py`)
- 1er run: 93 mutantes, **11 supervivientes (11.83%)**. Matados los 11 con cobertura legítima:
  - 5 = claves del dict `_MESSAGES` (405/422/500 ±1) → añadidas aserciones de `title` localizado a esos tests.
  - 2 = parseo `Accept-Language` (`[0]`→`[-1]`) → añadidos ejemplos `en;q=0.9` y `en-US` al Outline i18n.
  - 3 = rama CORS (`==`→`>=`/`<=`, `and`→`or`) → añadido test "no-dev + cors vacío → NO permisivo" (seguridad).
- 2º run: **survival 1.08% (1 superviviente de 93) ≤ 20 → gate verde**. El superviviente es `==`→`is` en
  `app_env == "development"` (línea 139): **mutante equivalente NO DETERMINISTA por string interning**
  (`x is "literal"` puede dar True/False según si el objeto está internado; para cualquier valor real de
  `app_env`, `is` da la misma rama que `==`, porque nunca comparamos identidad). Documentado como equivalente.
  - **Corrección de honestidad**: una ejecución previa imprimió `0.00%` (el mutante `is` cayó esa vez por la
    no-determinación del interning); el valor real y reproducible es **1.08%** (lo destapó el fact-checker,
    afirmación 6 INCORRECTA → corregida aquí y re-verificado en esta sesión: 92 killed / 1 survived).

### Verificación (salida real, esta sesión)
- pytest full → **77 passed** · `ruff check` (+`S`) + `ruff format --check` limpios · `mypy app` strict →
  Success (79 ficheros) · `make mutation` → survival **1.08%** ≤ 20 (1 equivalente `Eq_Is`, ver arriba).
- README actualizado (`/health/live` + `/health/ready` diferido + envelope i18n; `make run` disponible).
- **sdd-lint** (mecánico + semántico): PASA, sin ERROR. AVISO reconocido y corregido: la i18n del envelope
  se traza a **`api-contract.md:42`** (anchor preciso: "title/detail localizables por Accept-Language"), no a
  NFR-007 (que es i18n de la respuesta del *agente* por idioma del ticket, no el envelope HTTP); NFR-007 queda
  como temático. Docstring de `main.py` corregido. **fact-checker**: pendiente.

### Spike previo (findings verificados)
- Contextvar de `BaseHTTPMiddleware` **propaga al endpoint** en Starlette 1.6.0 → correlación e2e OK.
- `ServerErrorMiddleware` re-lanza el 500 → test con `ASGITransport(raise_app_exceptions=False)`.
- CORS: denegado (prod, origen no listado) → 400 sin `Access-Control-Allow-Origin`.

## Follow-ups (fuera de alcance, planes posteriores)
- `/health/ready` + alias `/health` (DB + pgvector) → plan de capa DB; hasta entonces el `HEALTHCHECK` del
  servicio `api` de docker-compose sigue rojo (aviso F2 conocido).
- request-id en respuestas **500** (el `ServerErrorMiddleware` es el más externo → el middleware no lo etiqueta);
  aceptable (los escenarios no lo exigen). Routers de negocio, throttling `/auth/*`, `/metrics`, Sentry, `deps.py`.
