"""Tests unit del nodo `generate` (tarea `backend-agent-graph-05`), mocks de puertos, sin infra.

CU-BE-05 escenario 5 (*la respuesta cita sus fuentes*) + escenario 3 (*contexto insuficiente escala*) a
nivel de nodo, más los bordes propios de `generate` de la tarea (grade ausente, idioma, límite de salida).
"""

import uuid

from app.agents.nodes.generate import make_generate_node
from app.agents.nodes.grade import Grade
from app.domain.entities.enums import KbDomain, KbEstado
from app.domain.ports.vector import Hit
from app.rag.reranker import RankedHit
from langchain_core.messages import HumanMessage


def _ranked_hit(uc_id: str, *, title: str = "Título", content: str = "contenido") -> RankedHit:
    hit = Hit(
        uc_id=uc_id,
        chunk_id=uuid.uuid4(),
        section_type="comportamiento",
        title=title,
        source_url=f"packages/x/docs/aiup/use-cases/{uc_id}.md",
        domain=KbDomain.media_and_dam,
        estado=KbEstado.draft,
        score=0.8,
        content=content,
    )
    return RankedHit(hit=hit, weighted_score=0.8)


def _state(
    *,
    grade: Grade | None,
    retrieved: list[RankedHit] | None = None,
    question: str = "¿cómo subo un vídeo?",
) -> dict:
    return {
        "messages": [HumanMessage(content=question)],
        "tenant_id": uuid.uuid4(),
        "ticket_id": uuid.uuid4(),
        "auto_approve": False,
        "classification": None,
        "retrieved": retrieved if retrieved is not None else [],
        "grade": grade,
        "confidence": None,
        "requires_approval": False,
        "draft_response": None,
        "human_note": None,
        "human_decision": None,
    }


class _FakeChatModel:
    def __init__(self, response: str) -> None:
        self._response = response
        self.captured_prompt: str | None = None

    async def generate(self, prompt: str) -> str:
        self.captured_prompt = prompt
        return self._response

    async def classify(self, text: str, schema: type) -> object:  # pragma: no cover - no usado
        raise NotImplementedError

    async def grade(self, prompt: str, schema: type) -> object:  # pragma: no cover - no usado
        raise NotImplementedError


async def test_missing_grade_does_not_raise_and_yields_a_default_human_note() -> None:
    """`state["grade"] is None` (nodo testeado aislado) no debe romper con AttributeError."""
    chat_model = _FakeChatModel("no debería llamarse")
    node = make_generate_node(chat_model)

    result = await node(_state(grade=None))

    assert result["draft_response"] is None
    assert result["human_note"] == "contexto insuficiente"
    assert chat_model.captured_prompt is None


async def test_insufficient_grade_does_not_generate_and_keeps_the_llm_reason() -> None:
    """CU-BE-05 escenario 3: `grade.suficiente=False` → no se genera, se conserva el motivo del LLM
    como `human_note` (no una nota genérica)."""
    grade = Grade(suficiente=False, motivo="falta la sección de configuración avanzada")
    chat_model = _FakeChatModel("no debería llamarse")
    node = make_generate_node(chat_model)

    result = await node(_state(grade=grade, retrieved=[_ranked_hit("CU-BE-05")]))

    assert result["draft_response"] is None
    assert result["human_note"] == "falta la sección de configuración avanzada"
    assert chat_model.captured_prompt is None


async def test_sufficient_grade_without_any_retrieved_hit_escalates_defensively() -> None:
    """Borde de seguridad: `grade.suficiente=True` pero `retrieved=[]` (el LLM alucina suficiencia sin
    contexto) → sin citas posibles, así que escala en vez de publicar un draft sin fuentes (Objetivo 5
    del plan: generate nunca produce un draft sin al menos una cita)."""
    grade = Grade(suficiente=True, motivo="parece suficiente")
    chat_model = _FakeChatModel("un draft inventado")
    node = make_generate_node(chat_model)

    result = await node(_state(grade=grade, retrieved=[]))

    assert result["draft_response"] is None
    assert chat_model.captured_prompt is None


async def test_generated_draft_always_includes_at_least_one_citation() -> None:
    """Objetivo 5 del plan: con contexto suficiente, el draft SIEMPRE incluye al menos una cita con `uc_id`."""
    grade = Grade(suficiente=True, motivo="basta")
    chat_model = _FakeChatModel("Puedes subir el vídeo desde el panel de medios.")
    node = make_generate_node(chat_model)

    result = await node(
        _state(grade=grade, retrieved=[_ranked_hit("CU-BE-05", title="Subida de vídeo")])
    )

    assert result["draft_response"] is not None
    assert "CU-BE-05" in result["draft_response"]
    assert result["human_note"] is None


async def test_generate_uses_the_last_message_not_the_first() -> None:
    """En un hilo con varios mensajes, redacta para el ÚLTIMO, no el primero."""
    grade = Grade(suficiente=True, motivo="basta")
    chat_model = _FakeChatModel("respuesta")
    node = make_generate_node(chat_model)
    state = _state(grade=grade, retrieved=[_ranked_hit("CU-BE-05")])
    state["messages"] = [
        HumanMessage(content="pregunta original"),
        HumanMessage(content="pregunta nueva"),
    ]

    await node(state)

    assert chat_model.captured_prompt is not None
    assert "pregunta nueva" in chat_model.captured_prompt
    assert "pregunta original" not in chat_model.captured_prompt


async def test_a_draft_exactly_at_the_output_limit_is_not_truncated() -> None:
    """Frontera exacta: una respuesta de EXACTAMENTE el límite no se trunca (`<=`, no `<`)."""
    grade = Grade(suficiente=True, motivo="basta")
    exact_response = "x" * 4000
    chat_model = _FakeChatModel(exact_response)
    node = make_generate_node(chat_model)

    result = await node(_state(grade=grade, retrieved=[_ranked_hit("CU-BE-05")]))

    assert result["draft_response"] is not None
    body = result["draft_response"].split("\n\nFuentes:")[0]
    assert body == exact_response
    assert len(body) == 4000


async def test_prompt_asks_to_answer_in_the_ticket_language_and_response_is_used_verbatim() -> None:
    """Refuerzo idioma (agent-graph.md §9): el prompt pide responder en el idioma del ticket; el nodo
    usa el texto devuelto tal cual (no traduce ni reformatea él mismo — la KB está en español, el
    ticket en inglés, la respuesta del LLM mockeado ya viene en inglés)."""
    grade = Grade(suficiente=True, motivo="basta")
    chat_model = _FakeChatModel("You can upload the video from the media panel.")
    node = make_generate_node(chat_model)

    result = await node(
        _state(
            grade=grade,
            retrieved=[_ranked_hit("CU-BE-05")],
            question="How do I upload a video?",
        )
    )

    assert result["draft_response"] is not None
    assert "You can upload the video" in result["draft_response"]
    assert "vídeo" not in result["draft_response"].split("Fuentes:")[0]
    assert chat_model.captured_prompt is not None
    assert "idioma" in chat_model.captured_prompt.lower()


async def test_a_draft_exceeding_the_output_limit_is_truncated_not_published_unbounded() -> None:
    """Refuerzo límites de salida (agent-graph.md §8): una respuesta del LLM que excede el límite se
    trunca de forma controlada, nunca se propaga sin límite."""
    grade = Grade(suficiente=True, motivo="basta")
    oversized_response = "x" * 10_000
    chat_model = _FakeChatModel(oversized_response)
    node = make_generate_node(chat_model)

    result = await node(_state(grade=grade, retrieved=[_ranked_hit("CU-BE-05")]))

    assert result["draft_response"] is not None
    body = result["draft_response"].split("\n\nFuentes:")[0]
    assert len(body) <= 4000
