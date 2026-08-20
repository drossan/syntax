# Session log — backend-routers-core-03

Tarea: envelope de error único (`DomainError`+`Deny`→`application/problem+json`) + schemas
compartidos (`Page[T]`, `Problem`). Nivel: integración (cliente HTTP de FastAPI sobre `create_app()`
real, mismo patrón que `test_main.py`). Independiente de 01/02 (`depends_on: —`).

## Entradas

- 2026-08-19 — Arranque. Tarea 03 `active`. TDD escenario a escenario (Red primero: tests importando
  módulos inexistentes).

## Resumen

`app/api/errors.py` (nuevo): handlers de `NotFound`→404, `Conflict`/`InvalidTransition`→409,
`Validation`→422, `PortError`→502 (fallo de un proveedor externo, no del cliente — no un 500
genérico), y `AuthorizationDenied` (envuelve un `Deny` de `rbac_service.authorize`, que no es una
excepción — el "no" es el camino esperado): `no_capability`→403, `out_of_scope`→404. Centraliza los
mensajes localizados (`Accept-Language` es/en) que antes vivían solo en `app/main.py`. `app/main.py`
refactorizado para reusar `app.api.errors.problem_response`/`register_exception_handlers` en vez de
duplicar la lógica — sus propios handlers de 404/405/422/500/503 (infra HTTP: ruta desconocida,
método no permitido, validación de request, excepción no controlada, readiness) ahora comparten la
misma fuente de mensajes. `app/api/v1/schemas/common.py` (nuevo): `Page[T]` (PEP 695) y `Problem`
(con `ProblemErrorEntry` para `errors[]`).

## Decisiones técnicas + porqué

- **Solo 4 handlers registrados** (`NotFound`/`Conflict`/`Validation`/`PortError`), no 5: Starlette
  recorre el `__mro__` de la excepción lanzada buscando el handler más específico registrado, así que
  `InvalidTransition` (subclase de `Conflict`) encuentra el handler de `Conflict` sin registro propio
  — mismo status (409) de todas formas. Evita una entrada redundante en `register_exception_handlers`.
- **`_validation_errors` solo actúa si `details` tiene AMBAS claves `field` y `message`** (no una sola):
  cualquier otra forma de `details` (la mayoría de los `Validation` existentes usan claves de dominio
  arbitrarias — `capability`, `from`/`to`, `ticket_id` — no `field`/`message`) se traduce solo como
  `detail` de texto libre, sin `errors[]`. Decisión de diseño explícita, no un descuido: el contrato
  `Problem.errors[]` es para errores por-campo, y forzar esa forma sobre `details` arbitrarios
  produciría entradas sin sentido.
- **Refactor de `app/main.py` para eliminar duplicación**, no solo añadir el envelope nuevo al lado:
  antes de esta tarea, `main.py` tenía su propio `_MESSAGES`/`_negotiate_language`/`_problem_response`
  privados; mantenerlos en paralelo a los de `app/api/errors.py` habría significado DOS fuentes de
  mensajes localizados que podrían divergir (p.ej. el título de 404 distinto según viniera de una ruta
  desconocida o de un `NotFound` de dominio). Se centralizó todo en `app/api/errors.py` y `main.py`
  pasa a ser un consumidor.
- **`Page` con sintaxis PEP 695** (`class Page[T](BaseModel)`) en vez de `Generic[T]`/`TypeVar` — Ruff
  (`UP046`) lo exige en Python 3.12 (versión fijada del proyecto); Pydantic v2 lo soporta nativamente.

## Tests corridos + resultado

- `tests/test_api_errors.py` (nuevo): **26 tests** — los 9 escenarios Gherkin de la tarea (outline de
  5 `DomainError`, `Deny` no_capability/out_of_scope, excepción no mapeada sin fugar detalle,
  localización es/en/fallback, `Validation.details` con y sin forma field/message) más 8 reforzados
  durante el endurecimiento de mutación (títulos localizados por status, rama de fallback de
  `_status_for_domain_error`, `and` vs `or` en `_validation_errors`).
- `tests/test_schemas_common.py` (nuevo): **4 tests** (`Page[T]` serializa exactamente 4 claves,
  genérico de verdad sobre el tipo de item; `Problem` con shape y `errors[]` del contrato).
- `tests/test_main.py`: sigue **verde** tras el refactor (mismo comportamiento HTTP, prueba que la
  extracción a `app.api.errors` no cambió nada observable).
- Suite completa del backend (`pytest -q`): **verde**, sin regresiones.
- `ruff check .`: OK. `ruff format --check .`: OK en todos los ficheros tocados (el único fichero con
  drift, `docs/domain-services-explicado.md`, es preexistente y no se tocó en esta tarea).
- `mypy app` (strict): `Success: no issues found in 95 source files`.
- Mutation (`cosmic-ray` sobre `app/api/errors.py`, test-command: `test_api_errors.py`+`test_main.py`):
  primera pasada 10.58% survival (11 survivors: claves del dict `MESSAGES` sin verificar el título,
  rama de fallback de `_status_for_domain_error` inalcanzable vía HTTP, `and`/`or` en
  `_validation_errors`) → tras reforzar (tests directos de `localized_messages`/`_status_for_domain_
  error`/`_validation_errors` a nivel de unidad, más tests HTTP de título por status) → **0.00%
  survival (100% mutation score)**.
- Gate `/sdd-lint`: **N/A** (declarado en la tarea — sin cambios de spec/CU; `Page`/`Problem` ya
  estaban documentados en `api-contract.yaml` desde antes de esta tarea).
- `fact-checker`: ver informe en la respuesta al usuario de esta sesión.

## Docs actualizadas

- Docstrings de `app/api/errors.py` (por qué `PortError`→502 y no 500, por qué `Deny` necesita
  `AuthorizationDenied` en vez de mapear directo, por qué basta registrar 4 handlers y no 5) y de
  `app/api/v1/schemas/common.py`. `app/main.py` actualizado para reflejar que ya no es la fuente de
  los mensajes localizados. Este session log.

## Ficheros / commits

- `backend/app/api/errors.py` (nuevo), `backend/app/api/v1/schemas/common.py` (nuevo).
- `backend/app/main.py` (refactor: reusa `app.api.errors`).
- `backend/tests/test_api_errors.py` (nuevo), `backend/tests/test_schemas_common.py` (nuevo).
- `backend/cosmic-ray.toml` (apunta a `app/api/errors.py`).

## Tiempo real

- `estimate: 2h` → real: sesión propia, sin incidencias de las descubiertas en 01/02 (tarea aislada,
  sin tocar migraciones ni specs).

## Follow-ups

- Ninguno propio. Los routers que consumen este envelope (05-09) deberán registrar `AuthorizationDenied`
  al llamar a `rbac_service.authorize()` y obtener `Deny` — patrón: `if isinstance(decision, Deny):
  raise AuthorizationDenied(decision)`.
