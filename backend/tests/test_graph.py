"""Tests de `app.agents.graph.build_graph()` (tarea `backend-agent-graph-06`).

Rutas end-to-end del grafo COMPLETO compilado con `InMemorySaver` (checkpointer de PRUEBA, ADR-0007
prohíbe `MemorySaver` en producción — la persistencia real es integración obligatoria, tareas 07/08/09).
Puertos (ChatModel/Retriever/MessageRepository) mockeados: son los mismos dobles que ya prueban cada
nodo por separado en `test_node_*.py` — aquí se verifica el ENSAMBLAJE (routing), no la lógica de cada
nodo otra vez.
"""

import uuid

import pytest
from app.agents.graph import build_graph
from app.agents.nodes.grade import Grade
from app.domain.entities.business import Message
from app.domain.entities.enums import KbDomain, KbEstado, TicketPriority
from app.domain.errors import PortError
from app.domain.ports.vector import Hit
from app.domain.services.classification import Classification
from app.rag.reranker import RankedHit
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver


def _hit(uc_id: str = "CU-BE-05", score: float = 0.9) -> RankedHit:
    hit = Hit(
        uc_id=uc_id,
        chunk_id=uuid.uuid4(),
        section_type="comportamiento",
        title="Título",
        source_url=f"packages/x/docs/aiup/use-cases/{uc_id}.md",
        domain=KbDomain.media_and_dam,
        estado=KbEstado.draft,
        score=score,
        content="contenido",
    )
    return RankedHit(hit=hit, weighted_score=score)


class _FakeChatModel:
    def __init__(
        self,
        *,
        classification: Classification,
        grade: Grade | None = None,
        draft: str = "un draft",
    ) -> None:
        self._classification = classification
        self._grade = grade
        self._draft = draft
        self.grade_calls = 0
        self.generate_calls = 0

    async def classify(self, text: str, schema: type) -> Classification:
        return self._classification

    async def grade(self, prompt: str, schema: type) -> Grade:
        self.grade_calls += 1
        assert self._grade is not None
        return self._grade

    async def generate(self, prompt: str) -> str:
        self.generate_calls += 1
        return self._draft


class _FakeRetriever:
    def __init__(
        self, hits: list[RankedHit] | None = None, *, error: Exception | None = None
    ) -> None:
        self._hits = hits if hits is not None else []
        self._error = error
        self.calls = 0

    async def retrieve(self, query: str, *, top_k: int, domain=None, **kwargs) -> list[RankedHit]:
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._hits


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


def _initial_state(*, auto_approve: bool, messages: list | None = None) -> dict:
    return {
        "messages": messages
        if messages is not None
        else [HumanMessage(content="¿cómo subo un vídeo?")],
        "tenant_id": uuid.uuid4(),
        "ticket_id": uuid.uuid4(),
        "auto_approve": auto_approve,
        "classification": None,
        "retrieved": [],
        "grade": None,
        "confidence": None,
        "requires_approval": False,
        "draft_response": None,
        "human_note": None,
        "human_decision": None,
    }


def _compile(chat_model, retriever, messages_repo):
    graph = build_graph(
        chat_model,
        retriever,
        messages_repo,
        top_k=5,
        confidence_threshold=0.5,
        trim_max_tokens=50,
    )
    return graph.compile(checkpointer=InMemorySaver())


async def test_unresolvable_ticket_skips_generate_and_escalates_directly() -> None:
    """CU-BE-05 extensión 1b: `resoluble=false` → escala sin pasar por `retrieve`/`grade`/`generate`."""
    classification = Classification(
        categoria="otros", dominio=None, prioridad=TicketPriority.normal, resoluble=False
    )
    chat_model = _FakeChatModel(classification=classification)
    retriever = _FakeRetriever()
    messages_repo = _FakeMessageRepository()
    compiled = _compile(chat_model, retriever, messages_repo)
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    result = await compiled.ainvoke(_initial_state(auto_approve=True), config=config)

    assert "__interrupt__" in result
    assert retriever.calls == 0
    assert chat_model.grade_calls == 0
    assert chat_model.generate_calls == 0
    assert result["draft_response"] is None
    assert messages_repo.added == []


@pytest.mark.parametrize(
    ("resoluble", "suficiente", "auto_approve", "expect_interrupt", "expect_published"),
    [
        (False, None, True, True, False),
        (True, False, True, True, False),
        (True, True, False, True, False),
        (True, True, True, False, True),
    ],
    ids=["no_resoluble", "insuficiente", "requiere_aprobacion", "auto_publicado"],
)
async def test_signal_combinations_produce_the_expected_routing(
    resoluble: bool,
    suficiente: bool | None,
    auto_approve: bool,
    expect_interrupt: bool,
    expect_published: bool,
) -> None:
    classification = Classification(
        categoria="incidencia",
        dominio=KbDomain.media_and_dam,
        prioridad=TicketPriority.normal,
        resoluble=resoluble,
    )
    grade = Grade(suficiente=suficiente, motivo="motivo") if suficiente is not None else None
    chat_model = _FakeChatModel(
        classification=classification, grade=grade, draft="respuesta generada"
    )
    retriever = _FakeRetriever([_hit()])
    messages_repo = _FakeMessageRepository()
    compiled = _compile(chat_model, retriever, messages_repo)
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    result = await compiled.ainvoke(_initial_state(auto_approve=auto_approve), config=config)

    assert ("__interrupt__" in result) is expect_interrupt
    assert (len(messages_repo.added) == 1) is expect_published


async def test_a_port_failure_propagates_uncaught_through_the_compiled_graph() -> None:
    """Un fallo de un puerto (Retriever caído) llega al llamante sin que LangGraph lo silencie."""
    classification = Classification(
        categoria="incidencia",
        dominio=KbDomain.media_and_dam,
        prioridad=TicketPriority.normal,
        resoluble=True,
    )
    chat_model = _FakeChatModel(classification=classification)
    retriever = _FakeRetriever(error=PortError("proveedor caído"))
    messages_repo = _FakeMessageRepository()
    compiled = _compile(chat_model, retriever, messages_repo)
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    with pytest.raises(PortError, match="proveedor caído"):
        await compiled.ainvoke(_initial_state(auto_approve=True), config=config)


@pytest.mark.parametrize("messages", [[], [HumanMessage(content="único mensaje")]])
async def test_zero_or_one_message_thread_does_not_break_trim_on_the_way_to_classify(
    messages: list,
) -> None:
    """Un hilo con 0 o 1 mensajes no rompe el grafo al pasar por `trim` antes de `classify`."""
    classification = Classification(
        categoria="otros", dominio=None, prioridad=TicketPriority.low, resoluble=False
    )
    chat_model = _FakeChatModel(classification=classification)
    retriever = _FakeRetriever()
    messages_repo = _FakeMessageRepository()
    compiled = _compile(chat_model, retriever, messages_repo)
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    result = await compiled.ainvoke(
        _initial_state(auto_approve=True, messages=messages), config=config
    )

    assert result["classification"] == classification
