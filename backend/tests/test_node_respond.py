"""Tests unit del nodo `respond` (tarea `backend-agent-graph-05`), mock de `MessageRepository`.

CU-BE-06: *Aprobación emite la respuesta al cliente*, *Edición envía el texto corregido*, *Rechazo no
publica nada al cliente* — la parte de COMPORTAMIENTO de `respond`, sin persistencia real del
checkpointer (eso es integración obligatoria, tareas 07/08/09).
"""

import uuid

from app.agents.nodes.respond import make_respond_node
from app.domain.entities.business import Message
from app.domain.entities.enums import ApprovalStatus, MessageVisibility
from app.domain.ports.agent_runner import ApprovalOutcome
from langchain_core.messages import HumanMessage


def _state(
    *, requires_approval: bool, draft_response: str | None, human_decision=None, human_note=None
) -> dict:
    return {
        "messages": [HumanMessage(content="pregunta")],
        "tenant_id": uuid.uuid4(),
        "ticket_id": uuid.uuid4(),
        "auto_approve": False,
        "classification": None,
        "retrieved": [],
        "grade": None,
        "confidence": None,
        "requires_approval": requires_approval,
        "draft_response": draft_response,
        "human_note": human_note,
        "human_decision": human_decision,
    }


class _FakeMessageRepository:
    def __init__(self) -> None:
        self.added: list[Message] = []

    async def add(self, message: Message) -> Message:
        self.added.append(message)
        return message

    async def get(self, message_id):  # pragma: no cover - no usado
        raise NotImplementedError

    async def list_by_ticket(self, ticket_id, **kwargs):  # pragma: no cover - no usado
        raise NotImplementedError


async def test_auto_path_publishes_the_draft_directly() -> None:
    """`requires_approval=False` → publica el draft directo, sin pasar por `human_decision`."""
    repo = _FakeMessageRepository()
    node = make_respond_node(repo)

    result = await node(_state(requires_approval=False, draft_response="aquí tienes la respuesta"))

    assert len(repo.added) == 1
    message = repo.added[0]
    assert message.body == "aquí tienes la respuesta"
    assert message.visibility is MessageVisibility.public
    assert message.is_ai_draft is True
    assert message.author_id is None
    assert message.tenant_id == result["tenant_id"]
    assert message.ticket_id == result["ticket_id"]


async def test_approved_decision_publishes_the_original_draft() -> None:
    """CU-BE-06: *Aprobación emite la respuesta al cliente* — publica `draft_body` (el draft original)."""
    repo = _FakeMessageRepository()
    node = make_respond_node(repo)
    outcome = ApprovalOutcome(status=ApprovalStatus.approved, final_body=None, human_note=None)

    await node(
        _state(requires_approval=True, draft_response="draft original", human_decision=outcome)
    )

    assert len(repo.added) == 1
    assert repo.added[0].body == "draft original"


async def test_edited_decision_publishes_the_corrected_text() -> None:
    """CU-BE-06: *Edición envía el texto corregido* — publica `final_body` (el texto editado), no el draft."""
    repo = _FakeMessageRepository()
    node = make_respond_node(repo)
    outcome = ApprovalOutcome(
        status=ApprovalStatus.edited, final_body="texto corregido", human_note=None
    )

    await node(
        _state(requires_approval=True, draft_response="draft original", human_decision=outcome)
    )

    assert len(repo.added) == 1
    assert repo.added[0].body == "texto corregido"


async def test_rejected_decision_publishes_nothing_and_keeps_the_human_note() -> None:
    """CU-BE-06: *Rechazo no publica nada al cliente* — no se llama a `messages_repo.add`, y se
    conserva la nota del humano."""
    repo = _FakeMessageRepository()
    node = make_respond_node(repo)
    outcome = ApprovalOutcome(
        status=ApprovalStatus.rejected, final_body=None, human_note="no es correcto"
    )

    result = await node(
        _state(requires_approval=True, draft_response="draft original", human_decision=outcome)
    )

    assert repo.added == []
    assert result["human_note"] == "no es correcto"
