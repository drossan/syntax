---
id: backend-routers-core-07
package: backend
plan: routers-core
status: done
priority: 1
depends_on: [backend-routers-core-05]
estimate: 4h
actual: 5h
issue:
created: 2026-08-19
updated: 2026-08-19
---

# TicketRepository (paginación/filtros/orden) + TicketService (PATCH parcial) + router tickets

## Description

Primer adaptador/router de **negocio** (con `TenantMixin`/RLS real, a diferencia de identidad). Amplía el
puerto `TicketRepository` (plan 10 solo tenía `list(tenant_id) -> list[Ticket]`, sin paginación/filtros/
orden — el contrato exige `page/page_size/status/priority/domain/assignee_id/sort`) y añade a
`TicketService` el método que falta para el `PATCH` parcial (ningún método existente cubre editar
`subject`/`priority`/`category` sueltos). Spec: CU-BE-04, FR-016/017/018/020/021.

## Spec

- **`app/domain/ports/repositories.py`**: `TicketRepository.list()` gana `page`, `page_size`, `status:
  TicketStatus | None`, `priority: TicketPriority | None`, `domain: KbDomain | None`, `assignee_id:
  uuid.UUID | None`, `sort: str = "-updated_at"` (**whitelist** de columnas ordenables — un valor fuera de
  la whitelist se rechaza en el router, 422, nunca llega a interpolarse en SQL) → devuelve `(items:
  list[Ticket], total: int)`. `domain` es un filtro **funcionalmente inerte hoy** (ningún ticket tendrá
  `Ticket.domain` distinto de `None` hasta que exista un clasificador — planes 12/15); se implementa
  porque el contrato lo exige, documentado como comportamiento esperado, no un bug.
- **`app/infra/db/repositories/ticket.py`**: adaptador sobre `BaseRepository[Ticket]` (SÍ aplica, `Ticket`
  lleva `TenantMixin`) + una query propia para el `list` paginado/filtrado (WHERE dinámico por los
  filtros presentes, `ORDER BY` desde la whitelist, `COUNT(*)` para `total`).
- **`app/domain/services/ticket_service.py`**: método nuevo `update_fields(ticket_id, *, subject=None,
  priority=None, category=None) -> Ticket` — solo muta los campos no-`None` pasados, audita
  `ticket.updated` con el diff, no reimplementa la máquina de estados (eso sigue en `transition`).
- **Router `tickets.py`**:
  - `GET /tickets` (`ticket.read`) → `Page[Ticket]` con los filtros/paginación de arriba.
  - `POST /tickets` (`ticket.create`) → `ticket_service.create`.
  - `GET /tickets/{id}` (`ticket.read`) → `ticket_service._get_or_raise`-equivalente vía el repo
    (tenant-scoped: fuera del tenant → 404, ya lo da la RLS+filtro app-level sin lógica extra).
  - `PATCH /tickets/{id}` (`ticket.update`, capacidad nueva de esta tarea — ver `rbac.md`) →
    `ticket_service.update_fields` para `subject`/`priority`/`category`; `csat` (también en
    `TicketUpdate`, contrato) NO pasa por `update_fields` — usa el `set_csat` YA existente
    (`domain-services`, con su propia validación 1..5), el router llama a ambos métodos según qué
    campos traiga el payload.
  - `POST /tickets/{id}/transition` (`ticket.transition`) → `ticket_service.transition` (409 en
    `InvalidTransition`, vía el envelope de la 03).
  - `POST /tickets/{id}/assign` (`ticket.assign`) → `ticket_service.assign`.

## Fuera de alcance

- `messages`/`attachments` → tarea 08.
- Disparar el grafo (`ai-draft`) → plan 12/15/16.
- Notificar tras `assign` (FR-038) → hueco nombrado, plan 12 (ver plan).
- **CAS en `transition`/`update_fields`**: riesgo de lost-update en dos escrituras concurrentes sobre el
  mismo ticket, documentado como conocido (ver plan) — no se rediseña `ticket_service` (plan
  `domain-services`, ya cerrado) por esta tarea.

## Scenarios (Gherkin)

Criterios de aceptación (Gherkin) en el caso de uso:
- [CU-BE-04 — Ciclo de vida del ticket](../../../specs/backend/casos-de-uso/CU-BE-04-ciclo-de-vida-del-ticket.md)

```gherkin
Feature: router de tickets con paginación real y PATCH parcial

  Scenario: listar tickets pagina y respeta el orden por defecto
    Given 25 tickets de un tenant
    When se pide GET /tickets sin filtros (page=1, page_size=20)
    Then llegan 20 items, total=25, ordenados por -updated_at

  Scenario Outline: filtrar tickets por un campo concreto
    Given tickets con distintos <campo>
    When se pide GET /tickets?<campo>=<valor>
    Then solo llegan los que coinciden con <valor>

    Examples:
      | campo       | valor  |
      | status      | open   |
      | priority    | urgent |
      | assignee_id | u1     |

  Scenario: crear un ticket devuelve 201 con el ticket creado
    Given un subject con ticket.create
    When hace POST /tickets con subject/body válidos
    Then recibe 201 con el Ticket, status=new

  Scenario: leer un ticket de otro tenant da 404
    Given un ticket que pertenece al tenant B
    When un subject del tenant A hace GET /tickets/{id}
    Then recibe 404 (no revela que existe en otro tenant)

  Scenario: sort fuera de la whitelist se rechaza sin tocar la base de datos
    Given una columna que no está en la whitelist ordenable (p.ej. "password_hash")
    When se pide GET /tickets?sort=password_hash
    Then recibe 422, y no se ejecuta ninguna consulta con esa columna

  Scenario Outline: page_size fuera de rango se rechaza
    Given el contrato fija page_size entre 1 y 100
    When se pide GET /tickets?page_size=<valor>
    Then <resultado>

    Examples:
      | valor | resultado          |
      | 0     | 422                |
      | -1    | 422                |
      | 101   | 422                |
      | 100   | 200 (límite válido)|

  Scenario: combinar varios filtros a la vez los aplica todos (AND)
    Given tickets con distintas combinaciones de status/priority/assignee_id
    When se pide GET /tickets?status=open&priority=urgent
    Then solo llegan los que cumplen AMBOS filtros

  Scenario: un filtro que no matchea nada da una página vacía, no un error
    Given ningún ticket con un assignee_id concreto
    When se pide GET /tickets?assignee_id=<id-sin-tickets>
    Then recibe 200 con Page{items: [], total: 0}

  Scenario: PATCH parcial solo cambia los campos enviados
    Given un ticket con subject="s1", priority=normal, category=None
    When se hace PATCH /tickets/{id} con solo priority=high
    Then subject sigue "s1", category sigue None, y priority pasa a high

  Scenario: PATCH con un valor de priority inválido se rechaza
    Given un ticket existente
    When se hace PATCH /tickets/{id} con priority="no-es-una-prioridad"
    Then recibe 422, sin modificar el ticket

  Scenario: PATCH con csat lo fija vía set_csat
    Given un ticket existente
    When se hace PATCH /tickets/{id} con csat=5
    Then recibe 200 con csat=5 (misma validación 1..5 de set_csat, no update_fields)

  Scenario: PATCH con csat fuera de 1..5 se rechaza
    Given un ticket existente
    When se hace PATCH /tickets/{id} con csat=6
    Then recibe 422

  Scenario: transición inválida da 409
    Given un ticket en new
    When se hace POST /tickets/{id}/transition con status=resolved (no es una arista válida)
    Then recibe 409 problem+json

  Scenario: asignar a alguien de otro tenant se rechaza
    Given un ticket del tenant A y un usuario del tenant B
    When se hace POST /tickets/{id}/assign con ese assignee_id
    Then recibe 422/409 (Validation de ticket_service, cross-tenant)

  Scenario: asignar a un assignee_id que no existe en absoluto se rechaza
    Given un ticket existente
    When se hace POST /tickets/{id}/assign con un assignee_id que no corresponde a ningún User
    Then recibe un error controlado (404/422), no una excepción cruda
```

## Provides

`TicketRepository` (paginado/filtrado/ordenado) en `app.infra.db.repositories.ticket`;
`TicketService.update_fields` nuevo; router `tickets` completo montado en `/api/v1`.

## Definition of Done

- [x] Tests escritos ANTES de la implementación (Red → Green → Refactor).
- [x] Cada escenario tiene al menos un test de integración.
- [x] Todos los tests en verde (`make test`) — 559 tests, verde.
- [x] `Provides` disponible.
- [x] `ruff check` (+`S`) + `ruff format --check` + `mypy` strict OK.
- [x] Gate de mutation `cosmic-ray` (`break: 80`) sobre el adaptador (11.41%) y el router (7.62%).
- [x] Gate `/sdd-lint` (1 ERROR encontrado y corregido —cobertura de `csat`—; 2 AVISO reconocidos).
- [x] Gate de `fact-checker` (17/18 VERIFICADO, 1 INCORRECTO corregido — conteo de tests).
- [x] Documentación: docstrings (por qué `update_fields` no reimplementa la máquina de estados); session
  log con la traza a CU-BE-04 (`.claude/context/backend/backend-routers-core-07.md`).
