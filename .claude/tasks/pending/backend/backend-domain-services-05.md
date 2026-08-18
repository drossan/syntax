---
id: backend-domain-services-05
package: backend
plan: domain-services
status: pending
priority: 2
depends_on: [backend-domain-services-02]
estimate: 1.5h
actual:
issue:
created: 2026-08-18
updated: 2026-08-18
---

# notification_service (emitir/listar/marcar-leída), desacoplado

## Description

Notificaciones in-app (Fase 1: solo polling, sin push). **Desacoplado**: ningún otro servicio de este
plan lo llama (decisión de grilling — criterio: la notificación es *best-effort*, no un acto atómico con
lo que la dispara, a diferencia de `approval_service`↔`ticket_service`, donde FR-027 exige abortar
junto). La orquestación "tras aprobar/asignar, notifica" es del plan de routers (11/12). Guión:
`app/domain/services/notification_service.py`. Spec: FR-038, CU-BE-10.

## Spec

- `emit(tenant_id, user_id, type: NotificationType, payload: dict) -> Notification`: crea la notificación
  vía `NotificationRepository.add`.
- `list_for_user(user_id) -> list[Notification]`: orden `-created_at` (**explícito en la firma del
  puerto**, no un fake que "ya viene ordenado" — el test asegura que el servicio pasa el orden correcto al
  puerto, no que el fake lo cumpla); lista vacía si no hay notificaciones (no `None`, no excepción).
- `count_unread(user_id) -> int`: deriva de `read_at IS NULL` (`data-model.md` RN-2) — capacidad exigida
  por CU-BE-10, ausente en el draft inicial, añadida por `scenario-coverage`.
- `mark_read(notification_id, user_id) -> Notification`: idempotente — marcar una ya leída es no-op (no
  lanza, no duplica `read_at`). Valida **titularidad**: si la notificación no pertenece a `user_id`, no la
  marca (mismo criterio app-level que `BaseRepository` de `database-foundation`). Sobre un
  `notification_id` inexistente: no-op silencioso (mismo tratamiento que "ya leída" — el servicio no
  distingue "no existe" de "no es tuya", para no revelar existencia entre usuarios).
- Sin efectos en import; puertos por inyección (`NotificationRepository`, `Clock`).

## Fuera de alcance

- Quién llama a `emit()` tras cada evento de negocio (aprobación pedida, asignación, respuesta, SLA) →
  routers (11/12); `notification_service` no depende de `ticket_service`/`approval_service`.
- Push/email/webhooks → diferido (fuera de alcance del roadmap en Fase 1).
- Schema de `payload` por `NotificationType` → hueco nombrado, sin dueño (11/12 si hace falta).
- Repos concretos → fuera de este plan.

## Scenarios (Gherkin)

Criterios de aceptación (Gherkin) en el caso de uso:
- [CU-BE-10 — Notificaciones in-app](../../../specs/backend/casos-de-uso/CU-BE-10-notificaciones-in-app.md)

> Nota de alcance: "Un evento notificable genera una notificación" se prueba como `emit()` llamado
> directamente (no disparado por otro servicio, que es la parte fuera de alcance de este plan). El
> aislamiento por tenant (escenario "Aislamiento del destinatario") se prueba a nivel de que el servicio
> pasa `tenant_id`/`user_id` correctos al puerto — el filtrado real (app-level + RLS) es de la capa de
> repos (fuera de este plan, ya cubierto conceptualmente por `database-foundation`). Añadido por
> `scenario-coverage`:
> ```gherkin
> Scenario: listar sin notificaciones devuelve lista vacía
>   Given un usuario sin notificaciones
>   When consulta su lista
>   Then recibe una lista vacía (no None, no excepción)
>
> Scenario: marcar leída una notificación inexistente es no-op
>   Given un notification_id que no existe
>   When se marca como leída
>   Then no lanza excepción y no ocurre nada observable
>
> Scenario: marcar leída una notificación de OTRO usuario no la afecta
>   Given una notificación que pertenece al usuario A
>   When el usuario B intenta marcarla como leída
>   Then la notificación de A sigue sin leer (no revela si existe ni la muta)
>
> Scenario: contar no leídas
>   Given un usuario con 2 notificaciones no leídas y 1 leída
>   When consulta su contador de no leídas
>   Then el resultado es 2
> ```

## Provides

`notification_service` (emitir/listar/marcar-leída) en `app.domain.services.notification_service`,
consumido por los routers (11/12) tras cada evento de negocio.

## Definition of Done

- [ ] Tests escritos ANTES de la implementación (Red → Green → Refactor).
- [ ] Cada escenario del CU (alcance de esta tarea) tiene al menos un test (emitir, orden por argumentos,
  lista vacía, marcar leída, idempotencia de marcar leída dos veces, marcar-leída de otro usuario no
  afecta, marcar-leída inexistente no-op, contar no leídas).
- [ ] Todos los tests en verde (`make test`).
- [ ] `Provides` disponible; el dominio no importa `app.infra`; sin dependencia de otros servicios.
- [ ] `ruff check` (+`S`) + `ruff format --check` + `mypy` strict OK.
- [ ] Gate de mutation `cosmic-ray` (`break: 80`) sobre `notification_service.py`.
- [ ] Gate `/sdd-lint` sin ERROR (CU-BE-10 Gherkin bien formado, enlace válido).
- [ ] Gate de `fact-checker`.
- [ ] Documentación: docstrings (por qué desacoplado); session log con la traza a CU-BE-10.
