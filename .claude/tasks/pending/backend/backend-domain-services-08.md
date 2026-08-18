---
id: backend-domain-services-08
package: backend
plan: domain-services
status: pending
priority: 1
depends_on: [backend-domain-services-02, backend-domain-services-04]
estimate: 3h
actual:
issue:
created: 2026-08-18
updated: 2026-08-18
---

# approval_service (cola aislada por tenant, decide() compone ticket_service+AgentRunner, CAS)

## Description

Aprobación humana (HITL) de drafts IA. Cola de `ApprovalTask` pendientes **por tenant** (orden
`sla_due,confidence`, `api-contract.yaml`). `decide()` **compone**: (1) `ApprovalRepository.
decide_if_pending` — la atomicidad real vive en el **contrato del puerto** (compare-and-set), no en un
check-then-act del servicio (no demostrable con fakes, design-review B3); tarea inexistente → `NotFound`;
tarea existente pero ya no `pending` → `None` del puerto → `Conflict` (reconcilia `data-model.md §4.2`
"no-op" de estado con `spec.md` FR-028/CU-BE-06 RN-2 "409" de respuesta — mismo hecho, dos niveles;
distinción `NotFound`/`Conflict` añadida por `scenario-coverage`, antes ambos casos colapsaban); (2) en
`approve`/`edit`: transición del ticket a **`pending`** vía `ticket_service` (fijado ahora, decisión de
design-review B2 — antes "p.ej." sin fijar); (3) `AgentRunner.resume`. **NO** emite `Message(public)` ni
toca `agent_run.status` — contradicción real detectada en design-review (B1) entre el guión original del
servicio y `agent-graph.md §6.3`/CU-BE-06/`api-contract.yaml`, que coinciden en que la emisión del mensaje
es del nodo `respond` del grafo (tarea 16), resuelta a favor de la evidencia cruzada. Nace aquí el puerto
**`AgentRunner`** (resume). **`ApprovalPolicy`/`auto_approve` NO forman parte de esta tarea**:
`scenario-coverage` detectó que ningún método de `approval_service` en este plan **crea** una
`ApprovalTask` (lo hace el grafo vía `interrupt()`, CU-BE-06) — sin ese consumidor, el puerto quedaba sin
llamante; se retira y queda como hueco nombrado para la tarea 16. Guión: `app/domain/services/
approval_service.py`, `app/domain/ports/agent_runner.py` (nuevo). Spec: FR-026/027/028/029, CU-BE-06.

## Spec

- `app/domain/ports/agent_runner.py` (nuevo): `AgentRunner.resume(thread_id: str, outcome:
  ApprovalOutcome) -> None` (async). `ApprovalOutcome` (dataclass/enum): `approved | edited | rejected` +
  `final_body: str | None` + `human_note: str | None`.
- `list_pending(tenant_id) -> list[ApprovalTask]`: orden `sla_due,confidence` **explícito en la firma del
  puerto** (`ApprovalRepository.list_pending(tenant_id)`), no un fake que "ya viene ordenado"; **aislado
  por tenant** — el servicio pasa `tenant_id` al puerto, no filtra en memoria.
- `decide(task_id, decision: Literal["approve","edit","reject"], final_body: str | None, human_note: str
  | None) -> ApprovalTask`:
  1. `try: updated = await approval_repo.decide_if_pending(task_id, decision, final_body, human_note)`;
     si el puerto lanza `NotFound` → se propaga (la tarea no existe); si devuelve `None` → `raise
     Conflict(...)` (la tarea existe pero ya no estaba `pending`; **no** llama a `resume`).
  2. `edit` **exige** `final_body` (`Validation` si falta — simétrico a que `reject` exige `human_note`).
  3. Si `approve`/`edit`: `await ticket_service.transition(ticket_id, TicketStatus.pending)`. **Riesgo
     conocido, documentado, sin compensación en este plan**: si `transition()` lanza aquí, la
     `ApprovalTask` ya quedó `approved`/`edited` (CAS irreversible) y la excepción se propaga tal cual —
     no hay unit-of-work cross-repo a este nivel (servicio + fakes); una transacción real que cubra
     ambos repos es de infra (11/12).
  4. `await agent_runner.resume(updated.agent_run.thread_id, outcome)` — **una sola vez**, tras el CAS.
  5. `reject`: **no** transiciona el ticket; `human_note` es obligatorio (validación de dominio, no del
     puerto).
- Sin efectos en import; puertos por inyección (`ApprovalRepository`, `AgentRunner`, `ticket_service`).

## Fuera de alcance

- Emisión de `Message(public)` y transición de `agent_run.status` → nodo `respond` del grafo (tarea 16).
- La atomicidad real del CAS (concurrencia de verdad) → integración, fuera de este plan (11/12/16); aquí
  solo se prueba que el servicio **reacciona** correctamente a `None`/`NotFound` del puerto.
- El adaptador real de `AgentRunner`/checkpointer LangGraph → tarea 16.
- **`auto_approve` por tenant** (puerto `ApprovalPolicy`, quién decide crear `ApprovalTask(pending)` vs.
  auto-materializar) → hueco nombrado para la tarea 16 (el grafo crea las `ApprovalTask`s vía
  `interrupt()`; es ahí donde hay un consumidor real de la política).
- **Fallo tras el CAS** (paso 3 de `decide()`) → riesgo conocido documentado, sin compensación (ver Spec).
- El límite de ai-draft por ticket/tenant (B.1) → aplicado por el router (12).
- Notificar tras aprobar (`notification_service`) → orquestación del router (11/12).

## Scenarios (Gherkin)

Criterios de aceptación (Gherkin) en el caso de uso:
- [CU-BE-06 — Draft IA y aprobación HITL](../../../specs/backend/casos-de-uso/CU-BE-06-draft-ia-y-aprobacion-hitl.md)

> Nota de alcance: de CU-BE-06, esta tarea cubre **solo la parte de `approval_service`** de cada
> escenario — no el nodo `respond` del grafo (fuera de alcance, ver arriba). "Aprobación emite la
> respuesta al cliente" → esta tarea prueba que `decide("approve")` hace el CAS + transiciona a `pending`
> + llama `resume` (NO que se publique el mensaje, eso es 16). "Edición envía el texto corregido" →
> ídem con `final_body`. "Rechazo no publica nada" → esta tarea prueba que `reject` NO transiciona el
> ticket y exige `human_note`. "Doble decisión es idempotente" → `decide_if_pending` devuelve `None` →
> `Conflict`, sin segundo `resume`. "Reinicio a mitad de run"/"Fallo del LLM" → **fuera de alcance**
> (checkpointer real, tarea 16); no se prueban aquí.
>
> **Hueco a incorporar al CU** (pendiente de un ajuste posterior a CU-BE-06): el CU no fija explícitamente
> que `approve`/`edit` transicionan el ticket a `pending` (`agent-graph.md §6.4` solo dice "p.ej. open/
> pending"). Esta tarea fija `pending` por decisión del owner (design-review B2); el CU debería ganar un
> escenario/regla de negocio que lo confirme.
>
> Añadido por `scenario-coverage`:
> ```gherkin
> Scenario: decidir una tarea que nunca existió da NotFound
>   Given un task_id que no corresponde a ninguna ApprovalTask
>   When se llama a decide() sobre ese task_id
>   Then se lanza NotFound (distinto de la tarea "ya decidida")
>
> Scenario: editar sin final_body se rechaza
>   Given un borrador pendiente de aprobación
>   When se decide "edit" sin proporcionar final_body
>   Then se rechaza (Validation), sin CAS aplicado
>
> Scenario: list_pending aísla por tenant
>   Given tareas pendientes de los tenants A y B
>   When se listan las pendientes del tenant A
>   Then solo aparecen las de A
>
> Scenario: fallo tras el CAS de aprobación se propaga sin compensar
>   Given una approval_task pendiente cuyo ticket ya no admite la transición a pending
>   When se decide "approve"
>   Then la excepción de ticket_service se propaga (riesgo conocido: la approval_task ya quedó approved)
> ```

## Provides

`approval_service` (cola/decide) en `app.domain.services.approval_service`, y el puerto `AgentRunner` en
`app.domain.ports.agent_runner`, consumidos por el router de aprobaciones (12) y por el adaptador
LangGraph/checkpointer (16).

## Definition of Done

- [ ] Tests escritos ANTES de la implementación (Red → Green → Refactor).
- [ ] Cada escenario del CU (alcance de esta tarea) tiene al menos un test: approve→CAS+pending+resume,
  edit→ídem con final_body (y rechazo si falta), reject→sin transición+human_note obligatorio, tarea
  inexistente→NotFound, doble decisión→Conflict sin segundo resume, cola aislada por tenant, fallo tras
  el CAS se propaga.
- [ ] Todos los tests en verde (`make test`).
- [ ] `Provides` disponible; el dominio no importa `app.infra`; `approval_service` NO recibe
  `MessageRepository`, `AgentRunRepository` ni `ApprovalPolicy` (verificar por la firma del constructor).
- [ ] `ruff check` (+`S`) + `ruff format --check` + `mypy` strict OK.
- [ ] Gate de mutation `cosmic-ray` (`break: 80`) sobre `approval_service.py` (`agent_runner.py` es
  Protocol, N/A).
- [ ] Gate `/sdd-lint` sin ERROR (CU-BE-06 Gherkin bien formado, enlace válido; aviso reconocido sobre el
  hueco de "aprobar→pending" no fijado aún en el CU).
- [ ] Gate de `fact-checker`.
- [ ] Documentación: docstrings (por qué NO emite Message, por qué NO tiene `ApprovalPolicy`, contrato
  CAS, `ApprovalOutcome`, el riesgo conocido de fallo post-CAS); session log con la traza a CU-BE-06 y el
  hueco a incorporar al CU.
