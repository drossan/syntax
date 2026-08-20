# Session log — backend-routers-flujo-ia-03

Tarea: `NotificationRepository` ampliado (paginación + `unread` + `get`) + adaptador
`SqlAlchemyNotificationRepository` + `notification_service` (passthrough + `get`) + router
`notifications.py` completo. Tercera tarea del plan `routers-flujo-ia` (depends_on: —).

## Entradas

- 2026-08-20 — Arranque. Tarea movida a `active/`. Continúa en la misma rama `plan/backend/
  routers-flujo-ia` (tareas 01/02 ya cerradas y commiteadas).
- 2026-08-20 — Cierre.

## Resumen

TDD completo. Orden real: (1) `NotificationRepository.list_for_user` gana `unread`/`page`/`page_size`
→ `PageResult[Notification]`; nuevo `get(notification_id)` en `app/domain/ports/repositories.py`; (2)
`notification_service.list_for_user` (passthrough) + `get(notification_id, user_id)` (`NotFound` si no
existe o no es del usuario, sin distinguir); (3) `SqlAlchemyNotificationRepository` (nuevo, primer
adaptador real de este puerto) — `list_for_user` con `read_at IS NULL`/`IS NOT NULL` + paginación; (4)
`get_notification_service` en `deps.py`; (5) router `notifications.py` (sin capacidad dedicada,
`tenant_scope` directo) + schema + `main.py`.

## Decisiones técnicas + porqué

- **Router sin `require_capability`/`require_any_capability`**: es el primer endpoint del backend
  donde el control de acceso es "cualquier autenticado, acotado a sí mismo", no una capacidad RBAC. Se
  abre `tenant_scope(session, subject.tenant_id)` directamente (import de `app.infra.db.session`) para
  que la RLS de la tabla `notification` no bloquee la query, sin pasar por la maquinaria de capacidades
  que no aplica aquí.
- **Orden `get()` → `mark_read()` → `get()` en `PATCH /{id}/read`**: el primer `get()` da el 404 real
  (no existe / no es mía) ANTES de tocar nada; `mark_read()` es idempotente pero silencioso (no dice si
  ya estaba leída); el segundo `get()` devuelve el estado posterior a la mutación. Sin este orden, un
  intento de marcar la notificación de OTRO usuario habría devuelto 200 (por el no-op silencioso de
  `mark_read`) en vez de 404 — la ambigüedad que la propia tarea señalaba sin resolver.
- **Bug real de test propio, no de producción**: `now()` de Postgres es estable dentro de una misma
  transacción — dos `add()` seguidos sin `commit()` intermedio generan el MISMO `created_at`, así que un
  test de orden `-created_at` con dos filas en la misma transacción no tiene garantía de qué fila viene
  primero. Corregido commiteando entre cada `add()` en los tests que verifican orden.
- **Refuerzo de mutation testing tras dos gates que fallaron por poco** (>20% survival): (1)
  `notification.py` — el cálculo `offset = (page - 1) * page_size` no tenía ningún test que distinguiera
  `page` de operadores alternativos (`%`, `>>`, `^`, `/`, `//`, `**`) porque con `page=1` todos dan el
  mismo resultado (0); añadido un test con 5 notificaciones + `page_size=2` que verifica las 3 páginas
  exactas por `id`, matando los mutantes aritméticos. (2) `notifications.py` (router) — los límites
  `ge=1`/`le=100` de `page`/`page_size` (Query) no tenían ningún test de frontera; añadido el mismo
  patrón que `test_router_tickets.py::test_list_tickets_rejects_page_size_out_of_range`.

## Tests corridos + resultado

- `tests/test_notification_service.py` (ampliado): `get`/`list_for_user` con `unread`/`PageResult` —
  6 tests nuevos (aislamiento por usuario ya cubierto, `unread=true/false`, `get` propio/inexistente/de
  otro usuario).
- `tests/test_repositories_notification.py` (nuevo, 13 tests): CRUD, orden `-created_at` (con `commit`
  intercalado), aislamiento por usuario, filtro `unread` true/false, paginación exacta por página (3
  páginas, refuerzo de mutación), `mark_read` idempotente/aislado, `count_unread`.
- `tests/test_router_notifications.py` (nuevo, 9 tests): los 9 escenarios Gherkin de la tarea vía HTTP
  real — paginación/orden, filtros `unread`, página vacía, marcar propia (200)/ya-leída (200
  idempotente)/de-otro (404, sin afectarla)/inexistente (404), fronteras `page`/`page_size` (refuerzo de
  mutación).
- Suite completa del backend (`pytest`): **717 tests, verde** (baseline 691 + 26 nuevos/ampliados).
- `ruff check .`/`ruff format --check .`: OK. `mypy app` (strict): `Success: no issues found in 130
  source files`.
- Mutation (`cosmic-ray`, `--fail-over 20`, `session.sqlite` borrada entre corridas, fichero mutado
  releído completo tras cada corrida):
  - `app/infra/db/repositories/notification.py`: primera pasada **19.27%** (survivors reales sobre el
    cálculo de `offset`, ver Decisiones) → reforzado → **11.93%** (re-confirmado por `fact-checker`:
    12.84%) → PASA.
  - `app/api/v1/routers/notifications.py`: primera pasada **21.74%** (survivors sobre límites `ge`/`le`
    de `page`/`page_size`, ver Decisiones) → **FALLA** → reforzado → **4.35%** → PASA.
  - `app/domain/services/notification_service.py`: **13.89%** (re-confirmado: 11.11%) → PASA
    directamente.
  - `app/core/deps.py`: acotado a `test_router_notifications.py`+`test_router_approvals.py`+
    `test_router_agent.py`+`test_router_auth.py` juntos (mismo criterio de las tareas 01/02 para
    ficheros compartidos): **12.20%** → PASA.
- `/sdd-lint`: sin cambios de CU en esta tarea. Sincronía verificada: CU-BE-10 ya menciona `read_at` y
  el contador de no-leídas derivado de `read_at IS NULL` (RN-2), coherente con lo implementado.
- `fact-checker`: **12/12 afirmaciones VERIFICADO**, 0 INCORRECTO, 0 NO VERIFICABLE (incluye
  re-ejecución independiente de los 4 gates de mutation; el propio subagente documentó y gestionó
  correctamente un incidente propio de su proceso de verificación — un `session.sqlite` borrado
  prematuramente durante una corrida en background causó una mutación capturada transitoriamente, que
  NO corrigió a mano: releyó, confirmó que se revirtió sola, y repitió la corrida de forma síncrona).

## Docs actualizadas

- Docstrings de todos los ficheros nuevos/tocados (repositories.py, notification_service.py,
  notification.py adaptador, deps.py, notifications.py router) — el porqué de cada decisión no obvia.
- Este session log.

## Ficheros / commits

- Nuevos: `backend/app/infra/db/repositories/notification.py`,
  `backend/app/api/v1/routers/notifications.py`, `backend/app/api/v1/schemas/notifications.py`,
  `backend/tests/test_repositories_notification.py`, `backend/tests/test_router_notifications.py`.
- Tocados: `backend/app/domain/ports/repositories.py` (`NotificationRepository.list_for_user`/`get`),
  `backend/app/domain/services/notification_service.py` (`list_for_user`/`get`), `backend/app/core/
  deps.py` (`get_notification_service`), `backend/app/infra/db/repositories/__init__.py`,
  `backend/app/main.py` (monta `notifications_router`), `backend/tests/test_notification_service.py`.
- `backend/cosmic-ray.toml` (apunta a `app/api/v1/routers/notifications.py`, último módulo mutado).
- Commit: uno solo, `backend-routers-flujo-ia-03: feat(backend): NotificationRepository ampliado +
  router notifications`.

## Tiempo real

- `estimate: 4h` → real: cercana a la estimación, ampliada por dos rondas de refuerzo de mutation
  testing (paginación del adaptador + fronteras del router) — ninguna reveló un bug real, ambas eran
  huecos de test genuinos sobre código ya correcto.

## Follow-ups

- Ninguno propio bloqueante. `backend-routers-flujo-ia-04` (wiring FR-038: `notification_service.emit()`
  en `tickets.py`/`messages.py`) depende de esta tarea (`depends_on: 03`) — puede arrancar ahora.
