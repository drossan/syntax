---
id: backend-routers-flujo-ia-02
package: backend
plan: routers-flujo-ia
status: done
priority: 1
depends_on: []
estimate: 4h
actual: 4h
issue:
created: 2026-08-20
updated: 2026-08-20
---

# ApprovalRepository ampliado (cola paginada) + adaptador + router approvals

## Description

Cola de aprobación HITL por HTTP. `approval_service.decide()` (plan `domain-services`) ya está cerrado y
no cambia de lógica — esta tarea solo construye el adaptador que faltaba y amplía el listado para que
cubra lo que pide el contrato (`Page` + filtro `status` + `sort`, no solo "pendientes sin paginar"). Spec:
`api-contract.yaml` (`/approvals*`), CU-BE-06 (ya cubre approve/edit/reject/idempotencia con Gherkin).

## Spec

- **`app/domain/ports/repositories.py`**: `ApprovalRepository.list_pending(tenant_id)` se **reemplaza**
  por `list(tenant_id: uuid.UUID | None, *, status: ApprovalStatus | None = None, sort: str =
  "sla_due,confidence", page: int, page_size: int) -> PageResult[ApprovalTask]` — sin `status` filtra
  solo `pending` (preserva el comportamiento actual); **`tenant_id=None` agrega cross-tenant**
  (`scenario-coverage` #4, bug real corregido antes de implementar: `approval.decide` es una capacidad
  **exclusivamente `global`** — rbac.md §3, solo Soporte, tenant "syntax" — pero las `ApprovalTask`
  pertenecen a los tenants **cliente**, nunca a "syntax"; con `tenant_id` obligatorio, Soporte no vería
  jamás ninguna aprobación. Mismo patrón que `AnalyticsRepository.summary` de la tarea 05).
  `sort` **no acepta valores arbitrarios** (`scenario-coverage`, decisión del owner): el único valor
  válido es el literal `"sla_due,confidence"` (o su ausencia, mismo default) — cualquier otro → 422 en el
  router, antes de llegar al puerto.
- **`app/infra/db/repositories/approval.py`** (nuevo): `SqlAlchemyApprovalRepository` — adaptador
  completo (`add`/`list`/`decide_if_pending`), mismo patrón que `ticket.py` (`WHERE` dinámico, `ORDER BY`
  desde whitelist fija `{sla_due, confidence}`, `COUNT(*)` para `total`).
- **`app/domain/services/approval_service.py`**: el método de cola se adapta al nuevo puerto (mismo
  nombre `list_pending` con la firma ampliada, o renombrado a `list_queue` — a decidir en el propio
  código, sin cambiar `decide()`).
- **`tests/test_approval_service.py`**: actualizar `test_list_pending_isolates_by_tenant` (fake del
  puerto + expectativa `PageResult`, hallazgo de `design-review` sobre este plan — el test tenía un
  consumidor real y se rompía sin estar declarado).
- **Router `app/api/v1/routers/approvals.py`**:
  - `GET /approvals` (capacidad `approval.decide`) → `Page[ApprovalTask]`, filtros `status`/`sort` (`sort`
    validado contra el literal exacto `"sla_due,confidence"` ANTES de llegar al repo, 422 si no coincide);
    `tenant_id` resuelto vía `get_tenant_context` → `None` en ámbito `global` (agrega cross-tenant),
    `subject.tenant_id` en ámbito `tenant`.
  - `POST /approvals/{id}/approve` (body opcional `human_note`) → `approval_service.decide(..., "approve",
    None, human_note)`.
  - `POST /approvals/{id}/edit` (body `final_body` requerido, `human_note` opcional) →
    `decide(..., "edit", final_body, human_note)`.
  - `POST /approvals/{id}/reject` (body `human_note` requerido) → `decide(..., "reject", None,
    human_note)`.
  - Los 3 `POST` devuelven 200 + `ApprovalTask`; `NotFound`→404 (id inexistente), `Conflict`→409,
    `Validation`→422 (ya mapeados por el envelope central, sin lógica de error en el router).
- **`app/api/v1/schemas/approvals.py`** (nuevo): `ApprovalTask`, `ApprovalDecideRequest` (o 3 schemas de
  request separados, espejo de `api-contract.yaml`).
- **`app/core/deps.py`**: `get_approval_service` (ensambla con `SqlAlchemyApprovalRepository` +
  `TicketService` + `StubAgentRunner`/adaptador real de `AgentRunner` de la tarea 01).
- **`app/main.py`**: registra `approvals_router` bajo `/api/v1`.

## Fuera de alcance

- Lógica de `decide()` (CAS, composición con `ticket_service`/`AgentRunner`) → ya cerrada en
  `domain-services`, sin cambios en esta tarea.
- Creación de `ApprovalTask(pending)` desde el grafo (`interrupt()`) → plan 16; sin grafo real, la cola
  queda funcionalmente vacía hasta entonces (mismo criterio que `kb.search` con `VectorStore` stub).
- CAS/optimistic-concurrency en el nuevo método de listado (`list`) → es de solo lectura, no lo necesita;
  el único CAS real del dominio sigue siendo `decide_if_pending`.

## Scenarios (Gherkin)

Criterios de aceptación de la decisión HITL (approve/edit/reject/idempotencia) en el caso de uso:
- [CU-BE-06 — Draft IA y aprobación HITL](../../../specs/backend/casos-de-uso/CU-BE-06-draft-ia-y-aprobacion-hitl.md)

```gherkin
Feature: router de la cola de aprobación con paginación real

  Scenario: listar la cola sin filtro devuelve solo las pendientes, ordenadas
    Given varias ApprovalTask en distintos estados del mismo tenant
    When se pide GET /approvals sin filtro de status
    Then llegan solo las pending, ordenadas por sla_due,confidence

  Scenario: filtrar la cola por status concreto
    Given ApprovalTask en varios estados
    When se pide GET /approvals?status=rejected
    Then solo llegan las rejected

  Scenario: aprobar un draft delega en approval_service y devuelve 200
    Given una ApprovalTask pending
    When hace POST /approvals/{id}/approve
    Then recibe 200 con la tarea en status approved

  Scenario: editar sin final_body es un error de validación
    Given una ApprovalTask pending
    When hace POST /approvals/{id}/edit sin final_body en el body
    Then recibe 422

  Scenario: decidir dos veces la misma tarea es un conflicto
    Given una ApprovalTask ya decidida
    When llega una segunda decisión sobre la misma tarea
    Then recibe 409

  Scenario: decidir un id que no existe devuelve 404
    Given un identificador que no corresponde a ninguna ApprovalTask
    When llega una decisión (approve/edit/reject) sobre ese id
    Then recibe 404

  Scenario: un sort no soportado es un error de validación
    Given cualquier estado de la cola
    When se pide GET /approvals?sort=confidence
    Then recibe 422 (el único sort válido es el literal sla_due,confidence)

  Scenario: la cola está aislada por tenant en ámbito tenant
    Given ApprovalTask de dos tenants distintos
    When un subject en ámbito tenant pide GET /approvals
    Then solo ve las de su propio tenant

  Scenario: Soporte en ámbito global ve la cola de todos los tenants
    Given ApprovalTask pendientes de varios tenants distintos
    When un subject con approval.decide en ámbito global pide GET /approvals
    Then ve las pendientes de TODOS los tenants

  Scenario: un subject sin approval.decide no puede ver ni decidir la cola
    Given un subject sin la capacidad approval.decide
    When pide GET /approvals o decide una tarea
    Then recibe 403
```

## Provides

- `app.infra.db.repositories.SqlAlchemyApprovalRepository`, `app.core.deps.get_approval_service`, router
  `approvals.py` montado en `/api/v1`.

## Definition of Done

- [x] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [x] Cada escenario Gherkin tiene al menos un test (camino feliz + bordes/errores)
- [x] Todos los tests en verde (incl. `tests/test_approval_service.py` actualizado)
- [x] Spec cumplida; lo declarado en `Provides` queda realmente disponible para las tareas dependientes
- [x] Lint / format / typecheck OK
- [x] Gate de mutation testing superado (`cosmic-ray`, `break:80`)
- [x] Gate `sdd-lint` superado (sin cambios de CU nuevos en esta tarea; sincronía verificada contra rbac.md)
- [x] Gate `fact-checker` superado (12/12 afirmaciones VERIFICADO)
- [x] Documentación — TSDoc + doc técnica + session log
- [x] Docs de dev/usuario donde aplique (N/A — sin superficie de usuario final nueva, solo API)
