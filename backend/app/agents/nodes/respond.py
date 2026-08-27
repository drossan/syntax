"""app.agents.nodes.respond — publica la respuesta al cliente (CU-BE-06, escenario principal paso 4).

Sumado al alcance en `design-review` (ajuste 9 — el guión previo de `nodes/__init__.py` solo listaba 6
nodos). Edge `decide → respond` es incondicional: este nodo decide QUÉ publicar (o si publica algo)
mirando `state["requires_approval"]`/`state["human_decision"]`, campos tipados (RN-1 de CU-BE-05).

- `requires_approval=False` (ruta auto) → publica `draft_response` directo.
- `requires_approval=True` → lee `state["human_decision"]` (`ApprovalOutcome`, fijado por `decide` al
  reanudar tras `interrupt()`/`Command(resume=)`): `rejected` → no publica nada, conserva `human_note`
  (CU-BE-06 3b); `approved` → publica el draft original; `edited` → publica `final_body` (CU-BE-06 3a).
"""

import uuid

from app.agents.nodes import NodeFn
from app.agents.state import HelpdeskState
from app.domain.entities.business import Message
from app.domain.entities.enums import ApprovalStatus, MessageVisibility
from app.domain.ports.repositories import MessageRepository


def make_respond_node(messages_repo: MessageRepository) -> NodeFn:
    """Factory-closure: publica (o no) un `Message` público según el resultado de `decide`."""

    async def node(state: HelpdeskState) -> HelpdeskState:
        if not state["requires_approval"]:
            await _publish(messages_repo, state, state["draft_response"])
            return state

        decision = state["human_decision"]
        if decision is None:
            return state
        if decision.status is ApprovalStatus.rejected:
            state["human_note"] = (
                decision.human_note if decision.human_note is not None else state["human_note"]
            )
            return state
        if decision.status is ApprovalStatus.edited:
            await _publish(messages_repo, state, decision.final_body)
            return state
        if decision.status is ApprovalStatus.approved:
            await _publish(messages_repo, state, state["draft_response"])
            return state
        return state

    return node


async def _publish(
    messages_repo: MessageRepository, state: HelpdeskState, body: str | None
) -> None:
    if body is None:
        raise RuntimeError(
            "respond solo publica cuando hay un cuerpo (draft_response/final_body) disponible"
        )
    await messages_repo.add(
        Message(
            id=uuid.uuid4(),
            tenant_id=state["tenant_id"],
            ticket_id=state["ticket_id"],
            author_id=None,
            visibility=MessageVisibility.public,
            is_ai_draft=True,
            body=body,
        )
    )
