---
id: backend-routers-flujo-ia-03
package: backend
plan: routers-flujo-ia
status: pending
priority: 2
depends_on: []
estimate: 4h
actual:
issue:
created: 2026-08-20
updated: 2026-08-20
---

# NotificationRepository ampliado (paginación + unread) + adaptador + router notifications

## Description

Notificaciones in-app por HTTP. `notification_service` (plan `domain-services`) ya tiene
emitir/listar/marcar-leída/contar-no-leídas, pero `list_for_user` no pagina ni filtra — el contrato exige
`Page` + filtro `unread`. Spec: CU-BE-10 (ya cubre emisión/orden/marcar-leída/aislamiento con Gherkin).

## Spec

- **`app/domain/ports/repositories.py`**: `NotificationRepository.list_for_user(user_id)` gana `unread:
  bool | None = None` (`True`→solo no leídas, `False`→**solo leídas**, `None`/ausente→sin filtro —
  `scenario-coverage`, decisión del owner: filtro simétrico), `page: int`, `page_size: int` →
  `PageResult[Notification]` (orden `-created_at` ya fijado, sin cambios). Nuevo `get(notification_id) ->
  Notification | None` (`scenario-coverage` #3 — sin él, el router no puede distinguir "no existe/no es
  mía" de "es mía y ya estaba leída": `mark_read` de dominio es un no-op silencioso en los tres casos).
- **`app/infra/db/repositories/notification.py`** (nuevo): `SqlAlchemyNotificationRepository` — adaptador
  completo (`add`/`get`/`list_for_user`/`mark_read`/`count_unread`), `WHERE read_at IS NULL`/`IS NOT
  NULL` según `unread`.
- **`app/domain/services/notification_service.py`**: `list_for_user` propaga los parámetros nuevos al
  puerto (sin lógica adicional — es un passthrough con paginación). Nuevo `get(notification_id, user_id)
  -> Notification`: `NotFound` si no existe **o** si `notification.user_id != user_id` (no revela cuál de
  los dos casos es — mismo criterio que el resto del backend).
- **Router `app/api/v1/routers/notifications.py`**:
  - `GET /notifications` (sin capacidad dedicada — autenticado, siempre acotado a `subject.id`; nunca un
    `user_id` de query) → `Page[Notification]`, filtro `unread`.
  - `PATCH /notifications/{id}/read` → 1) `notification_service.get(id, subject.id)` — `NotFound`→404 si
    no existe o no es del subject; 2) `notification_service.mark_read(id, subject.id)` (idempotente, ya
    sea que estuviera leída o no); 3) 200 + la `Notification` actualizada (re-`get` tras el `mark_read`).
    Este orden es lo que permite distinguir 404 (no es mía / no existe) de 200 idempotente (es mía, ya
    estaba leída) — la ambigüedad que la propia tarea señalaba sin resolver.
- **`app/api/v1/schemas/notifications.py`** (nuevo): `Notification` (espejo del contrato).
- **`app/core/deps.py`**: `get_notification_service` (ensambla con `SqlAlchemyNotificationRepository` +
  `SystemClock`).
- **`app/main.py`**: registra `notifications_router` bajo `/api/v1`.

## Fuera de alcance

- Emitir notificaciones desde `tickets.py`/`messages.py` (FR-038) → tarea 04 de este plan.
- `count_unread()` expuesto por HTTP → el contrato no tiene endpoint/campo para ello, sigue sin
  consumidor (hueco ya nombrado en `domain-services`).
- `approval_requested`/`sla_warning`/`sla_breach` como eventos reales → planes 15/16/18.

## Scenarios (Gherkin)

Criterios de aceptación de emisión/orden/marcar-leída/aislamiento en el caso de uso:
- [CU-BE-10 — Notificaciones in-app](../../../specs/backend/casos-de-uso/CU-BE-10-notificaciones-in-app.md)

```gherkin
Feature: router de notificaciones con paginación y filtro unread

  Scenario: listar notificaciones pagina y respeta el orden por defecto
    Given 25 notificaciones del usuario autenticado
    When hace GET /notifications sin filtros
    Then llegan 20 items, total=25, ordenados por -created_at

  Scenario: filtrar solo las no leídas
    Given notificaciones leídas y no leídas del usuario
    When hace GET /notifications?unread=true
    Then solo llegan las no leídas

  Scenario: filtrar solo las leídas
    Given notificaciones leídas y no leídas del usuario
    When hace GET /notifications?unread=false
    Then solo llegan las leídas

  Scenario: un usuario sin notificaciones recibe una página vacía
    Given un usuario autenticado sin ninguna notificación
    When hace GET /notifications
    Then recibe items=[] y total=0

  Scenario: marcar una notificación propia como leída
    Given una notificación no leída del usuario autenticado
    When hace PATCH /notifications/{id}/read
    Then recibe 200 y deja de aparecer con unread=true

  Scenario: marcar como leída una notificación propia que ya estaba leída es idempotente
    Given una notificación del usuario autenticado ya marcada como leída
    When hace PATCH /notifications/{id}/read de nuevo
    Then recibe 200 (no 404) con la notificación sin cambios

  Scenario: marcar como leída una notificación de otro usuario no la afecta
    Given una notificación que pertenece a otro usuario
    When el usuario autenticado hace PATCH /notifications/{id}/read
    Then recibe 404 y la notificación ajena sigue sin leer

  Scenario: marcar como leída un id inexistente devuelve 404
    Given un identificador que no corresponde a ninguna notificación
    When hace PATCH /notifications/{id}/read
    Then recibe 404
```

## Provides

- `app.infra.db.repositories.SqlAlchemyNotificationRepository`, `app.core.deps.
  get_notification_service`, router `notifications.py` montado en `/api/v1`.

## Definition of Done

- [ ] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [ ] Cada escenario Gherkin tiene al menos un test (camino feliz + bordes/errores)
- [ ] Todos los tests en verde
- [ ] Spec cumplida; lo declarado en `Provides` queda realmente disponible para las tareas dependientes
- [ ] Lint / format / typecheck OK
- [ ] Gate de mutation testing superado (`cosmic-ray`, `break:80`)
- [ ] Gate `sdd-lint` superado
- [ ] Gate `fact-checker` superado
- [ ] Documentación — TSDoc + doc técnica + session log
- [ ] Docs de dev/usuario donde aplique
