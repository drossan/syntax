"""app.domain.services.approval_service — aprobación humana (HITL) de drafts IA (FR-026/027/028/029,
CU-BE-06).

`decide()` **compone** tres puertos ya existentes en un único acto: (1) `ApprovalRepository.
decide_if_pending` — CAS; la atomicidad real vive en el **contrato del puerto**, no en un
check-then-act de este servicio (no demostrable con fakes, design-review B3); (2) en `approve`/`edit`,
`TicketService.transition` a `pending` (decisión de design-review B2, antes "p.ej." sin fijar); (3)
`AgentRunner.resume`, **una sola vez**, tras el CAS.

**NO** emite `Message(public)` ni toca `agent_run.status`: esa emisión es del nodo `respond` del grafo
(tarea 16) — contradicción detectada en design-review (B1) entre un guión previo de este servicio y
`agent-graph.md §6.3`/CU-BE-06/`api-contract.yaml`, resuelta a favor de la evidencia cruzada. **NO**
recibe `ApprovalPolicy`/`auto_approve`: ningún método de este servicio **crea** una `ApprovalTask` (la
crea el grafo vía `interrupt()`, CU-BE-06) — sin ese consumidor el puerto quedaba sin llamante
(scenario-coverage); queda como hueco nombrado para la tarea 16.

**Riesgo conocido, documentado, SIN compensación en este plan**: si `ticket_service.transition()` falla
tras el CAS (paso 2), la `ApprovalTask` ya quedó `approved`/`edited` (CAS irreversible) y la excepción se
propaga tal cual — no hay unit-of-work cross-repo a este nivel (servicio + fakes); una transacción real
que cubra ambos repos es de infra (11/12).
"""

import uuid
from typing import Literal

from app.domain.entities.business import ApprovalTask
from app.domain.entities.enums import ApprovalStatus, TicketStatus
from app.domain.errors import Conflict, Validation
from app.domain.ports.agent_runner import AgentRunner, ApprovalOutcome
from app.domain.ports.repositories import ApprovalRepository
from app.domain.services.ticket_service import TicketService

Decision = Literal["approve", "edit", "reject"]

_DECISION_TO_STATUS: dict[Decision, ApprovalStatus] = {
    "approve": ApprovalStatus.approved,
    "edit": ApprovalStatus.edited,
    "reject": ApprovalStatus.rejected,
}
_TRANSITIONS_TICKET: frozenset[Decision] = frozenset({"approve", "edit"})


class ApprovalService:
    """Cola de aprobación (aislada por tenant) + `decide()`. Puertos por inyección de constructor."""

    def __init__(
        self,
        approvals: ApprovalRepository,
        ticket_service: TicketService,
        agent_runner: AgentRunner,
    ) -> None:
        self._approvals = approvals
        self._ticket_service = ticket_service
        self._agent_runner = agent_runner

    async def list_pending(self, tenant_id: uuid.UUID) -> list[ApprovalTask]:
        """Cola de `tenant_id`, orden `sla_due,confidence` (contrato del puerto). Aislada por tenant:
        el filtro lo aplica el puerto, este servicio no filtra en memoria."""
        return await self._approvals.list_pending(tenant_id)

    async def decide(
        self,
        task_id: uuid.UUID,
        decision: Decision,
        final_body: str | None,
        human_note: str | None,
    ) -> ApprovalTask:
        """Aprueba/edita/rechaza una `ApprovalTask` pendiente.

        `NotFound` si `task_id` no corresponde a ninguna tarea (se propaga del puerto). `Conflict` si la
        tarea existe pero ya no estaba `pending` (doble decisión — no-op de estado, 409 de respuesta;
        sin segundo `resume`). `edit` exige `final_body`; `reject` exige `human_note` (validación de
        dominio, antes del CAS: una decisión inválida no debe llegar a mutar nada). Un `decision` fuera
        de `Decision` (`Literal` no forzado en runtime — p.ej. un valor sin validar que llegue de un
        futuro router) se rechaza aquí con `Validation`, nunca con el `KeyError` crudo de un `dict`.
        """
        if decision not in _DECISION_TO_STATUS:
            raise Validation(
                f"decisión desconocida: {decision!r}", code="approval.unknown_decision"
            )
        if decision == "edit" and not final_body:
            raise Validation("edit requiere final_body", code="approval.edit_requires_final_body")
        if decision == "reject" and not human_note:
            raise Validation(
                "reject requiere human_note", code="approval.reject_requires_human_note"
            )

        status = _DECISION_TO_STATUS[decision]
        updated = await self._approvals.decide_if_pending(
            task_id, status.value, final_body, human_note
        )
        if updated is None:
            raise Conflict(
                f"approval task {task_id} ya no estaba pending",
                code="approval.already_decided",
            )

        if decision in _TRANSITIONS_TICKET:
            await self._ticket_service.transition(updated.ticket_id, TicketStatus.pending)

        await self._agent_runner.resume(
            updated.agent_run_id,
            ApprovalOutcome(status=status, final_body=final_body, human_note=human_note),
        )
        return updated
