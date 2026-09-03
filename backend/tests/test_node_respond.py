"""Tests unit del nodo `respond` (tarea `backend-agent-graph-05`), mock de `MessageRepository`.

CU-BE-06: *Aprobación emite la respuesta al cliente*, *Edición envía el texto corregido*, *Rechazo no
publica nada al cliente* — la parte de COMPORTAMIENTO de `respond`, sin persistencia real del
checkpointer (eso es integración obligatoria, tareas 07/08/09). Camino auto (`resolved` + casos borde)
en `tests/test_runner.py`, integración real (footgun RLS) — aquí solo un doble mínimo de
`TicketService` para poder invocar el nodo sin infra.
"""

import uuid
from types import SimpleNamespace

from app.agents.nodes.respond import make_respond_node
from app.domain.entities.business import Message
from app.domain.entities.enums import ApprovalStatus, MessageVisibility, TicketStatus
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


class _FakeTicketService:
    """Doble mínimo — el comportamiento real de `advance_to()`/la máquina de estados ya está cubierto
    por `test_ticket_service.py` y por la integración real de `test_runner.py`; aquí solo hace falta
    que `respond` pueda invocar `.get()`/`.advance_to()` sin infra."""

    def __init__(self, initial_status: TicketStatus = TicketStatus.new) -> None:
        self.status = initial_status
        self.advance_to_calls: list[TicketStatus] = []

    async def get(self, ticket_id: uuid.UUID) -> SimpleNamespace:
        return SimpleNamespace(status=self.status)

    async def advance_to(
        self, ticket_id: uuid.UUID, target: TicketStatus, *, actor_id: uuid.UUID | None = None
    ) -> SimpleNamespace:
        self.advance_to_calls.append(target)
        self.status = target
        return SimpleNamespace(status=self.status)


async def test_auto_path_publishes_the_draft_directly() -> None:
    """`requires_approval=False` → publica el draft directo, sin pasar por `human_decision`."""
    repo = _FakeMessageRepository()
    node = make_respond_node(repo, _FakeTicketService())

    result = await node(_state(requires_approval=False, draft_response="aquí tienes la respuesta"))

    assert len(repo.added) == 1
    message = repo.added[0]
    assert message.body == "aquí tienes la respuesta"
    assert message.visibility is MessageVisibility.public
    assert message.is_ai_draft is True
    assert message.author_id is None
    assert message.tenant_id == result["tenant_id"]
    assert message.ticket_id == result["ticket_id"]


async def test_auto_path_advances_the_ticket_to_resolved_before_publishing() -> None:
    """Camino auto (CU-BE-06 4c): encadena el ticket hasta `resolved` — aquí solo se verifica que
    `respond` LLAMA a `advance_to(resolved)` (el ensamblaje); el recorrido real de la máquina de
    estados lo cubre `test_ticket_service.py`."""
    repo = _FakeMessageRepository()
    ticket_service = _FakeTicketService(initial_status=TicketStatus.new)
    node = make_respond_node(repo, ticket_service)

    await node(_state(requires_approval=False, draft_response="respuesta"))

    assert ticket_service.advance_to_calls == [TicketStatus.resolved]


async def test_auto_path_on_an_already_resolved_ticket_does_not_call_advance_to() -> None:
    """CU-BE-06 4d: si el ticket YA está en `resolved`/`closed`, no se intenta ninguna transición —
    `advance_to()` nunca se llama, pero SÍ se publica el mensaje."""
    repo = _FakeMessageRepository()
    ticket_service = _FakeTicketService(initial_status=TicketStatus.resolved)
    node = make_respond_node(repo, ticket_service)

    await node(_state(requires_approval=False, draft_response="respuesta"))

    assert ticket_service.advance_to_calls == []
    assert len(repo.added) == 1


async def test_approved_decision_publishes_the_original_draft() -> None:
    """CU-BE-06: *Aprobación emite la respuesta al cliente* — publica `draft_body` (el draft original)."""
    repo = _FakeMessageRepository()
    node = make_respond_node(repo, _FakeTicketService())
    outcome = ApprovalOutcome(status=ApprovalStatus.approved, final_body=None, human_note=None)

    await node(
        _state(requires_approval=True, draft_response="draft original", human_decision=outcome)
    )

    assert len(repo.added) == 1
    assert repo.added[0].body == "draft original"


async def test_edited_decision_publishes_the_corrected_text() -> None:
    """CU-BE-06: *Edición envía el texto corregido* — publica `final_body` (el texto editado), no el draft."""
    repo = _FakeMessageRepository()
    node = make_respond_node(repo, _FakeTicketService())
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
    node = make_respond_node(repo, _FakeTicketService())
    outcome = ApprovalOutcome(
        status=ApprovalStatus.rejected, final_body=None, human_note="no es correcto"
    )

    result = await node(
        _state(requires_approval=True, draft_response="draft original", human_decision=outcome)
    )

    assert repo.added == []
    assert result["human_note"] == "no es correcto"
