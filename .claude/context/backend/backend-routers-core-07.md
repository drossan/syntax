# Session log — backend-routers-core-07

Tarea: `TicketRepository` (paginación/filtros/orden) + `TicketService.update_fields` (PATCH parcial)
+ router `tickets` completo — primer router/adaptador de NEGOCIO (RLS real) de la sesión. Depends_on:
05 (`done`).

## Entradas

- 2026-08-19 — Arranque. Movida de `pending/` a `active/`, `status: pending`→`status: active`.

## Resumen

`app/domain/ports/repositories.py`: `TICKET_SORT_FIELDS` (whitelist `updated_at`/`created_at`/
`priority`/`sla_due`) + `TicketRepository.list()` ampliado con `page`/`page_size`/`status`/`priority`/
`domain`/`assignee_id`/`sort` → `PageResult[Ticket]` (antes solo `list(tenant_id) -> list[Ticket]`).
`app/infra/db/repositories/ticket.py` (nuevo): adaptador con query propia (no `BaseRepository`, que no
cubre paginación/filtros dinámicos). `app/domain/services/ticket_service.py`: `update_fields` nuevo
(PATCH parcial subject/priority/category), `get`/`list_tickets` (públicos, para el router — antes solo
`_get_or_raise` privado), `create()` gana `priority: TicketPriority | None` opcional (el contrato lo
permite, el servicio cerrado en `domain-services` no). `app/api/v1/routers/tickets.py`: los 6
endpoints del contrato, montado en `/api/v1`.

Antes de poder wirear `POST /tickets` de punta a punta, hubo que cerrar 2 huecos de puerto/adaptador
que el propio `ticket_service.create()` (ya cerrado, `domain-services`) exige pero que no existían:

1. **`SqlAlchemyMessageRepository`** (nuevo, `app/infra/db/repositories/message.py`) — `create()`
   llama a `self._messages.add(...)` para el primer mensaje público del ticket; sin un adaptador
   real, `TicketService` no se podía construir con dependencias reales en absoluto. Solo `add`/
   `list_by_ticket` (el contrato completo del puerto hoy); la tarea 08 lo amplía si hace falta
   (adjuntos/`Storage`, router `messages`).
2. **`StubSlaPolicy`** (nuevo, `app/infra/sla.py`) — `create()` llama a `self._sla_policy.due_at(...)`.
   `data-model.md` §11 deja la política real (horas/días por prioridad) explícitamente para la tarea
   18 ("solo se modelan `priority`+`sla_due`; el cómputo es 18") — inventar aquí un valor de negocio
   (p.ej. "urgent = 4h") habría sido una decisión no pedida por ningún spec. El stub devuelve siempre
   `None` (`sla_due` ya es nullable para este caso exacto).

`app/core/deps.py` gana `get_ticket_service` (mismo patrón que `get_auth_service`, tarea 05): ensambla
`TicketService` con los adaptadores reales + el stub de SLA.

## Decisiones técnicas + porqué

- **Capacidad nueva `ticket.update`** (`rbac.md`): el catálogo no tenía ninguna capacidad para "editar
  campos sin cambiar de estado" (solo `read`/`create`/`reply`/`transition`/`assign`). Añadida con la
  misma distribución rol×capacidad que `transition`/`assign` (ningún rol la posee sin `ticket.read`,
  así que basta UNA capacidad en el router, no dos, pese a que el `## Spec` original de la tarea decía
  "ticket.read+edición").
- **`create()` gana `priority` opcional**: el contrato (`TicketCreate.priority`) permite fijar la
  prioridad inicial, pero el `ticket_service.create()` cerrado en `domain-services` no tenía ese
  parámetro (siempre `normal`). Extensión mínima (`priority: TicketPriority | None = None`, default
  `normal` si no llega) — evita un doble-write (crear + `update_fields` inmediato) para algo que el
  propio servicio de creación puede resolver en una sola escritura.
- **`get`/`list_tickets` públicos en `TicketService`**: el router necesitaba invocar lectura/listado
  sin acceder a `_get_or_raise`/`self._tickets` (privados) desde fuera del servicio — añadidos como
  wrappers finos, en vez de que el router accediera a atributos privados (`ruff` S/SLF001 lo habría
  marcado, y rompe la encapsulación del servicio).
- **`sort` se valida en el ROUTER contra `TICKET_SORT_FIELDS`, no en el adaptador**: 422 antes de
  tocar la base de datos si no está en la whitelist (nunca se interpola un string arbitrario en SQL).
  El adaptador traduce el `sort` YA validado a una columna ORM real vía un mapeo fijo
  (`_SORT_COLUMNS`), nunca por interpolación.
- **`assign` resuelve `assignee_tenant_id` mirando la membership del assignee EN EL TENANT DEL
  ACTOR** (no busca el `User` global): si no hay `UserTenantMembership(assignee_id, subject.tenant_id)`
  — porque el usuario no existe en absoluto, o existe pero en otro tenant — `assignee_tenant_id` queda
  `None`, y `ticket_service.assign()` (ya cerrado) rechaza con el mismo `Validation` genérico en ambos
  casos. No hace falta lógica adicional en el router para distinguir "no existe" de "es de otro
  tenant" — ambos dan el mismo error controlado (cumple el escenario de la tarea sin código extra).
- **Errores de parseo de `str`→enum (`priority`/`status`) nunca crudos**: `_parse_priority`/
  `_parse_status` en el router envuelven el `ValueError` de `TicketPriority(value)`/`TicketStatus(value)`
  en `Validation` (422) — sin esto, un valor inválido producía un 500 (encontrado durante el propio
  desarrollo, antes de escribir el test correspondiente).

## Errores encontrados y corregidos

- **BUG REAL de infraestructura — migración 0002 sin `GRANT` sobre `user_tenant`.** El `GRANT SELECT,
  INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO syntax_app` de la migración 0001 solo cubre
  las tablas que YA existían al ejecutarse; `user_tenant` se creó en la migración 0002 (posterior) y
  nunca recibió su propio `GRANT`. Como resultado, el rol runtime `syntax_app` (no-superuser) nunca
  pudo leer/escribir `user_tenant` en ningún entorno real — un fallo que **ninguna tarea anterior
  detectó** porque sus tests de router (05, 06) usaban `superuser_engine` (bypassa permisos) incluso
  para las requests HTTP. Esta tarea es la primera en usar `app_engine` (rol `syntax_app` real) para
  el fixture `app` de un test de router (necesario para probar RLS de verdad en tickets/messages), lo
  que expuso el bug de inmediato (`asyncpg.exceptions.InsufficientPrivilegeError: permission denied
  for table user_tenant` al asignar un ticket). Fix: `GRANT` añadido a la migración 0002 (pre-
  lanzamiento, sin datos reales — editar la migración existente es seguro, mismo criterio que congelar
  0001 en la tarea 01) + aplicado directamente a `syntax_test` para esta sesión.
- **Router 500 en vez de 422** para `priority`/`status` inválidos en `POST /tickets`, `PATCH
  /tickets/{id}`, `POST /tickets/{id}/transition` — el `ValueError` de construir el enum de dominio
  desde un string no válido no estaba capturado. Fix: `_parse_priority`/`_parse_status`.
- **Orden de escritura de tests**: el fake compartido `_FakeTicketRepository` (duplicado en
  `test_ticket_service.py` y `test_approval_service.py`) tenía la firma VIEJA de `list()` — se
  actualizó en ambos ficheros a la vez que el puerto, con lógica de filtro/orden/paginación en memoria
  para no perder cobertura de los tests existentes.

## Tests corridos + resultado

- `tests/test_repositories_ticket.py` (nuevo, **16 tests**): CRUD de `SqlAlchemyTicketRepository`,
  paginación (2 páginas de 25), aislamiento cross-tenant del `list()`, filtros por `status`/`priority`/
  `assignee_id` (con `User` real por el FK), combinación AND, filtro sin match, orden asc/desc por
  `sla_due`/`created_at`; `SqlAlchemyMessageRepository.add`/`list_by_ticket` + un test con IDs
  deterministas (`UUID(int=10/50/90)`) para matar mutantes de comparación (`==`→`<=`/`>=`/`is not`) en
  el filtro `ticket_id`.
- `tests/test_router_tickets.py` (nuevo, **19 tests**): los 13 escenarios Gherkin de la tarea (+ 2
  añadidos para `csat` vía `PATCH`, hallazgo de `/sdd-lint`) — paginación/filtros/orden/whitelist de
  `sort`, límites de `page_size`, alta, aislamiento cross-tenant de `GET /tickets/{id}` (**RLS real**,
  primer test de router de la sesión que usa `app_engine`/rol `syntax_app` en vez de
  `superuser_engine`), PATCH parcial + csat + priority inválida, transición inválida (409), asignar
  cross-tenant/inexistente/válido.
- `tests/test_ticket_service.py`/`test_approval_service.py`: actualizados (fake `list()` con la firma
  nueva) + **9 tests nuevos** (`update_fields` con/sin campos, no toca `status`, 404, auditoría;
  `create()` con prioridad explícita/por defecto; `get`/`list_tickets` públicos).
- Suite completa del backend (`pytest -q`): **559 tests, verde**, sin regresiones.
- `ruff check .`/`ruff format --check .`: OK. `mypy app` (strict): `Success: no issues found in 111
  source files`.
- Mutation (`cosmic-ray`, `--fail-over 20`):
  - `app/infra/db/repositories/ticket.py`: **11.41%** survival → PASA.
  - `app/api/v1/routers/tickets.py`: primera pasada **7.62%** → PASA directamente (sin rondas de
    refuerzo); se mantuvo en 7.62% tras añadir los tests de `csat`.
  - **Extra, más allá de la DoD** (nuevo adaptador no trivial): `app/infra/db/repositories/message.py`,
    primera pasada 55.56% (filtro `ticket_id` sin aislar con IDs deterministas) → refuerzo → **22.22%**
    final — los 2 survivors restantes son el patrón `except Exception` ya aceptado en todos los
    adaptadores desde la tarea 04 (requiere inyección contrivada de fallo de infra); documentado, no
    bloquea (no es parte de la DoD de esta tarea, que solo exige adaptador+router de tickets).
- `/sdd-lint`: mecánico limpio. Semántico vía subagente fresco: **1 ERROR reportado + 2 AVISO**:
  - El "ERROR" (`ticket.update` en `rbac.md` promete cubrir `csat`, pero el `## Spec`/escenarios de la
    tarea no lo mencionaban) resultó ser un **gap de documentación/tests, no de código** — el router
    SÍ cableaba `csat` vía `ticket_service.set_csat` desde el principio (verificado leyendo
    `tickets.py` directamente); lo que faltaba era el test de integración y la mención explícita en el
    `## Spec` de la tarea. **Corregido**: 2 tests nuevos (`csat` válido/fuera de rango vía `PATCH`) +
    2 escenarios Gherkin + aclaración en `## Spec` (líneas actualizadas del task file).
  - AVISO (reconocido, no bloqueante): FR-021 (orden por defecto) no tiene escenario propio en
    CU-BE-04 pese a que el CU declara cubrirlo — hueco preexistente del CU, no de esta tarea.
  - AVISO (reconocido, no bloqueante): los escenarios de PATCH parcial/paginación de esta tarea no
    tienen contraparte en los criterios de aceptación de CU-BE-04 — desincronización spec↔tarea
    preexistente (el CU no se ha tocado desde antes de este plan), no una contradicción.
- `fact-checker`: pendiente de lanzar tras este session log.

## Docs actualizadas

- `.claude/specs/backend/rbac.md`: capacidad nueva `ticket.update` (catálogo + fila de matriz).
- `.claude/tasks/active/backend/backend-routers-core-07.md`: aclarado que `csat` va por `set_csat`
  (no `update_fields`) + 2 escenarios Gherkin nuevos (hallazgo de `/sdd-lint`).
- Docstrings de `app/domain/ports/repositories.py` (`TICKET_SORT_FIELDS`, el `list()` ampliado),
  `app/infra/db/repositories/ticket.py`/`message.py` (adaptadores nuevos), `app/infra/sla.py` (por qué
  el stub siempre devuelve `None`), `app/api/v1/routers/tickets.py` (por qué `sort` se valida en el
  router, por qué `assign` no necesita lógica extra para distinguir inexistente de cross-tenant),
  `alembic/versions/0002_identity_multi_tenant.py` (el `GRANT` que faltaba y por qué). Este session
  log.

## Ficheros / commits

- `backend/app/api/v1/routers/tickets.py` (de esqueleto a código real), `backend/app/api/v1/schemas/
  tickets.py` (nuevo), `backend/app/infra/db/repositories/ticket.py` (nuevo), `backend/app/infra/db/
  repositories/message.py` (nuevo), `backend/app/infra/sla.py` (nuevo).
- `backend/app/domain/ports/repositories.py` (`TICKET_SORT_FIELDS` + `TicketRepository.list`
  ampliado), `backend/app/domain/services/ticket_service.py` (`update_fields`/`get`/`list_tickets`
  nuevos, `create()` con `priority` opcional), `backend/app/core/deps.py` (`get_ticket_service`),
  `backend/app/infra/db/repositories/__init__.py` (exporta `SqlAlchemyMessageRepository`/
  `SqlAlchemyTicketRepository`), `backend/app/main.py` (monta el router `tickets`).
- `backend/alembic/versions/0002_identity_multi_tenant.py` (fix: `GRANT` sobre `user_tenant`).
- `backend/tests/test_repositories_ticket.py` (nuevo), `backend/tests/test_router_tickets.py`
  (nuevo), `backend/tests/test_ticket_service.py`/`test_approval_service.py` (fake `list()`
  actualizado + tests nuevos).
- `.claude/specs/backend/rbac.md` (`ticket.update`).
- Commit: uno solo, `backend-routers-core-07: feat(backend): TicketRepository paginado + PATCH parcial + router tickets`.

## Tiempo real

- `estimate: 4h` → real: ampliada por 2 adaptadores/puerto nuevos no anticipados explícitamente en la
  DoD (`SqlAlchemyMessageRepository`, `StubSlaPolicy`) necesarios para que `ticket_service.create()`
  (ya cerrado) tuviera dependencias reales, y por el bug real de infraestructura (GRANT ausente en
  `user_tenant`) que solo esta tarea podía exponer al ser la primera en probar RLS de verdad contra el
  rol runtime.

## Follow-ups

- Los 2 AVISO de `/sdd-lint` (FR-021 y PATCH/paginación sin reflejo en CU-BE-04) quedan como
  seguimiento nombrado de sincronización spec↔CU, no bloquean este cierre.
- `SqlAlchemyMessageRepository` queda mínimo (`add`/`list_by_ticket`) — la tarea 08 lo amplía si el
  puerto necesita más (adjuntos, `Storage`, router `messages`).
