"""Tests unit del nodo `retrieve` (tarea `backend-agent-graph-05`), mocks de puertos, sin infra.

CU-BE-05, escenarios 1 (dominio filtra el retrieval) y 1a (fallback sin filtro de dominio).
"""

import uuid

from app.agents.nodes.retrieve import make_retrieve_node
from app.domain.entities.enums import KbDomain, TicketPriority
from app.domain.services.classification import Classification
from app.rag.reranker import RankedHit
from langchain_core.messages import HumanMessage


def _state(
    *, classification: Classification | None, question: str = "¿cómo subo un vídeo?"
) -> dict:
    return {
        "messages": [HumanMessage(content=question)],
        "tenant_id": uuid.uuid4(),
        "ticket_id": uuid.uuid4(),
        "auto_approve": False,
        "classification": classification,
        "retrieved": [],
        "grade": None,
        "confidence": None,
        "requires_approval": False,
        "draft_response": None,
        "human_note": None,
        "human_decision": None,
    }


class _FakeRetriever:
    def __init__(self, hits: list[RankedHit]) -> None:
        self._hits = hits
        self.captured_kwargs: dict[str, object] = {}

    async def retrieve(self, query: str, *, top_k: int, domain=None, **kwargs) -> list[RankedHit]:
        self.captured_kwargs = {"query": query, "top_k": top_k, "domain": domain, **kwargs}
        return self._hits


async def test_recognized_domain_filters_the_retrieval() -> None:
    """CU-BE-05 escenario 1: `classification.dominio` fijado → se pasa como filtro al retriever."""
    classification = Classification(
        categoria="incidencia",
        dominio=KbDomain.media_and_dam,
        prioridad=TicketPriority.normal,
        resoluble=True,
    )
    retriever = _FakeRetriever([])
    node = make_retrieve_node(retriever, top_k=5)

    await node(_state(classification=classification))

    assert retriever.captured_kwargs["domain"] is KbDomain.media_and_dam
    assert retriever.captured_kwargs["top_k"] == 5


async def test_no_domain_classification_falls_back_to_unfiltered_search() -> None:
    """CU-BE-05 escenario 1a: `classification.dominio=None` → retrieval SIN filtro de dominio."""
    classification = Classification(
        categoria="consulta", dominio=None, prioridad=TicketPriority.low, resoluble=True
    )
    retriever = _FakeRetriever([])
    node = make_retrieve_node(retriever, top_k=5)

    await node(_state(classification=classification))

    assert retriever.captured_kwargs["domain"] is None


async def test_missing_classification_also_falls_back_to_unfiltered_search() -> None:
    """Nodo testeado aislado: sin `classification` en el estado (p.ej. `resoluble=false` saltó a
    escalado antes), tampoco se fuerza un dominio inventado."""
    retriever = _FakeRetriever([])
    node = make_retrieve_node(retriever, top_k=5)

    await node(_state(classification=None))

    assert retriever.captured_kwargs["domain"] is None


async def test_retrieve_queries_with_the_last_message_not_the_first() -> None:
    """En un hilo con varios mensajes, recupera contexto para el ÚLTIMO, no el primero."""
    retriever = _FakeRetriever([])
    node = make_retrieve_node(retriever, top_k=5)
    state = _state(classification=None)
    state["messages"] = [
        HumanMessage(content="pregunta original"),
        HumanMessage(content="pregunta nueva"),
    ]

    await node(state)

    assert retriever.captured_kwargs["query"] == "pregunta nueva"


async def test_retrieved_hits_are_stored_in_state() -> None:
    """Los hits devueltos por el retriever quedan en `state["retrieved"]`, tal cual (sin deduplicar,
    ADR-0018 D3a — la dedup es del camino HTTP, no del agente)."""
    from app.domain.entities.enums import KbEstado
    from app.domain.ports.vector import Hit

    hit = Hit(
        uc_id="CU-BE-05",
        chunk_id=uuid.uuid4(),
        section_type="comportamiento",
        title="Título",
        source_url="packages/x/docs/aiup/use-cases/CU-BE-05.md",
        domain=KbDomain.media_and_dam,
        estado=KbEstado.draft,
        score=0.8,
        content="contenido",
    )
    ranked = RankedHit(hit=hit, weighted_score=0.8)
    retriever = _FakeRetriever([ranked])
    node = make_retrieve_node(retriever, top_k=5)

    result = await node(_state(classification=None))

    assert result["retrieved"] == [ranked]
