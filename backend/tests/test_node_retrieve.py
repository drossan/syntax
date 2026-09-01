"""Tests unit del nodo `retrieve` (tarea `backend-agent-graph-05` + `backend-rag-domain-fallback-01`),
mocks de puertos, sin infra.

CU-BE-05, escenarios 1 (dominio filtra el retrieval), 1a (fallback sin filtro de dominio) y 1c (dominio
asignado pero equivocado → fallback ampliado, ADR-0019).
"""

import uuid

import structlog.testing
from app.agents.nodes.retrieve import make_retrieve_node
from app.domain.entities.enums import KbDomain, KbEstado, TicketPriority
from app.domain.errors import PortError
from app.domain.ports.vector import Hit
from app.domain.services.classification import Classification
from app.rag.reranker import RankedHit
from langchain_core.messages import HumanMessage

DOMAIN_FALLBACK_MARGIN = 0.05


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


def _classification(domain: KbDomain | None) -> Classification:
    return Classification(
        categoria="incidencia", dominio=domain, prioridad=TicketPriority.normal, resoluble=True
    )


def _hit(uc_id: str, score: float) -> RankedHit:
    hit = Hit(
        uc_id=uc_id,
        chunk_id=uuid.uuid4(),
        section_type="comportamiento",
        title=f"Título de {uc_id}",
        source_url=f"packages/x/docs/aiup/use-cases/{uc_id}.md",
        domain=KbDomain.media_and_dam,
        estado=KbEstado.draft,
        score=score,
        content="contenido",
    )
    return RankedHit(hit=hit, weighted_score=score)


class _FakeRetriever:
    """Doble de `Retriever`: `embed_query`/`search` por separado, hits configurables por dominio, y
    registro del HISTORIAL completo de llamadas (no solo la última) — necesario para verificar cuántas
    veces se llama a `search` según el caso."""

    def __init__(
        self,
        hits_by_domain: dict[KbDomain | None, list[RankedHit]] | None = None,
        *,
        vector: list[float] | None = None,
        search_error_on_domain: object = "__none_sentinel__",
    ) -> None:
        self._hits_by_domain = hits_by_domain if hits_by_domain is not None else {}
        self._vector = vector if vector is not None else [0.1, 0.2]
        self._search_error_on_domain = search_error_on_domain
        self.embed_calls: list[str] = []
        self.search_calls: list[dict[str, object]] = []

    async def embed_query(self, query: str) -> list[float]:
        self.embed_calls.append(query)
        return self._vector

    async def search(
        self, vector: list[float], *, top_k: int, domain: KbDomain | None = None, **kwargs: object
    ) -> list[RankedHit]:
        self.search_calls.append({"vector": vector, "top_k": top_k, "domain": domain})
        if domain == self._search_error_on_domain:
            raise PortError("proveedor caído")
        return self._hits_by_domain.get(domain, [])


async def test_recognized_domain_filters_the_first_retrieval() -> None:
    """CU-BE-05 escenario 1: `classification.dominio` fijado → primera búsqueda con ese filtro."""
    retriever = _FakeRetriever({KbDomain.media_and_dam: [_hit("UC-1", 0.9)]})
    node = make_retrieve_node(retriever, top_k=5, domain_fallback_margin=DOMAIN_FALLBACK_MARGIN)

    await node(_state(classification=_classification(KbDomain.media_and_dam)))

    assert retriever.search_calls[0]["domain"] is KbDomain.media_and_dam
    assert retriever.search_calls[0]["top_k"] == 5


async def test_no_domain_classification_falls_back_to_unfiltered_search() -> None:
    """CU-BE-05 escenario 1a: `classification.dominio=None` → una única búsqueda sin filtro."""
    retriever = _FakeRetriever()
    node = make_retrieve_node(retriever, top_k=5, domain_fallback_margin=DOMAIN_FALLBACK_MARGIN)

    await node(_state(classification=_classification(None)))

    assert retriever.search_calls[0]["domain"] is None


async def test_missing_classification_also_falls_back_to_unfiltered_search() -> None:
    """Nodo testeado aislado: sin `classification` en el estado, tampoco se fuerza un dominio inventado."""
    retriever = _FakeRetriever()
    node = make_retrieve_node(retriever, top_k=5, domain_fallback_margin=DOMAIN_FALLBACK_MARGIN)

    await node(_state(classification=None))

    assert retriever.search_calls[0]["domain"] is None


async def test_without_domain_only_one_search_is_executed() -> None:
    """scenario-coverage: sin dominio asignado, como mucho UNA búsqueda — sin comparación ni reintento."""
    retriever = _FakeRetriever()
    node = make_retrieve_node(retriever, top_k=5, domain_fallback_margin=DOMAIN_FALLBACK_MARGIN)

    await node(_state(classification=_classification(None)))

    assert len(retriever.search_calls) == 1


async def test_retrieve_queries_with_the_last_message_not_the_first() -> None:
    """En un hilo con varios mensajes, recupera contexto para el ÚLTIMO, no el primero."""
    retriever = _FakeRetriever()
    node = make_retrieve_node(retriever, top_k=5, domain_fallback_margin=DOMAIN_FALLBACK_MARGIN)
    state = _state(classification=None)
    state["messages"] = [
        HumanMessage(content="pregunta original"),
        HumanMessage(content="pregunta nueva"),
    ]

    await node(state)

    assert retriever.embed_calls == ["pregunta nueva"]


async def test_domain_assigned_with_low_relevance_falls_back_to_unfiltered_result() -> None:
    """CU-BE-05 1c: dominio asignado pero score bajo, y sin filtro mejora significativamente → usa el
    resultado sin filtro completo."""
    filtered_hit = _hit("UC-WRONG", 0.38)
    unfiltered_hit = _hit("UC-RIGHT", 0.55)
    retriever = _FakeRetriever(
        {
            KbDomain.rendering_and_publishing: [filtered_hit],
            None: [unfiltered_hit],
        }
    )
    node = make_retrieve_node(retriever, top_k=8, domain_fallback_margin=0.05)

    result = await node(_state(classification=_classification(KbDomain.rendering_and_publishing)))

    assert result["retrieved"] == [unfiltered_hit]


async def test_domain_assigned_with_good_relevance_keeps_the_filtered_result() -> None:
    """CU-BE-05 1c (caso inverso): dominio correcto, la mejora sin filtro no supera el margen → se
    mantiene el resultado filtrado, sin ruido del resto del corpus."""
    filtered_hit = _hit("UC-RIGHT", 0.65)
    unfiltered_hit = _hit("UC-NOISE", 0.66)
    retriever = _FakeRetriever(
        {
            KbDomain.identity_and_permissions: [filtered_hit],
            None: [unfiltered_hit],
        }
    )
    node = make_retrieve_node(retriever, top_k=8, domain_fallback_margin=0.05)

    result = await node(_state(classification=_classification(KbDomain.identity_and_permissions)))

    assert result["retrieved"] == [filtered_hit]


async def test_retry_without_domain_always_happens_regardless_of_filtered_score() -> None:
    """scenario-coverage (Outline): el reintento sin filtro se ejecuta SIEMPRE que hay dominio asignado,
    incluso con un score filtrado ya alto — un umbral absoluto no podría distinguir el caso real de
    dominio equivocado (score 0.611) de un caso correcto con score similar."""
    for score_filtrado in (0.384, 0.611, 0.66):
        retriever = _FakeRetriever({KbDomain.authoring_and_editor: [_hit("UC-X", score_filtrado)]})
        node = make_retrieve_node(retriever, top_k=8, domain_fallback_margin=DOMAIN_FALLBACK_MARGIN)

        await node(_state(classification=_classification(KbDomain.authoring_and_editor)))

        assert len(retriever.search_calls) == 2, f"score_filtrado={score_filtrado}"
        assert retriever.search_calls[1]["domain"] is None


async def test_empty_filtered_result_does_not_crash_the_comparison() -> None:
    """scenario-coverage: `filtered` vacío (0 hits) → la comparación usa 0.0 como score máximo filtrado,
    sin lanzar `ValueError` de `max()` sobre secuencia vacía."""
    unfiltered_hit = _hit("UC-FOUND", 0.5)
    retriever = _FakeRetriever({None: [unfiltered_hit]})
    node = make_retrieve_node(retriever, top_k=8, domain_fallback_margin=0.05)

    result = await node(_state(classification=_classification(KbDomain.media_and_dam)))

    assert result["retrieved"] == [unfiltered_hit]


async def test_empty_filtered_result_against_a_zero_score_unfiltered_hit_does_not_fall_back() -> (
    None
):
    """El default de `filtered` vacío es `0.0`, no un valor negativo — un hit real con score `0.0`
    exacto (válido, el clamp de similitud nunca produce negativos) no debe disparar el fallback: la
    diferencia real es `0.0 - 0.0 = 0.0`, no mayor que el margen."""
    filtered_hit_missing = []
    unfiltered_zero_score_hit = _hit("UC-ZERO", 0.0)
    retriever = _FakeRetriever({None: [unfiltered_zero_score_hit]})
    node = make_retrieve_node(retriever, top_k=8, domain_fallback_margin=0.05)

    result = await node(_state(classification=_classification(KbDomain.media_and_dam)))

    assert result["retrieved"] == filtered_hit_missing


async def test_both_searches_empty_keeps_the_empty_filtered_result_without_error() -> None:
    """scenario-coverage: ni la búsqueda filtrada ni la sin filtro encuentran nada → delta 0.0, no
    dispara el fallback, se mantiene el resultado filtrado (vacío) sin ningún error."""
    retriever = _FakeRetriever({})
    node = make_retrieve_node(retriever, top_k=8, domain_fallback_margin=0.05)

    result = await node(_state(classification=_classification(KbDomain.media_and_dam)))

    assert result["retrieved"] == []


async def test_improvement_exactly_equal_to_the_margin_does_not_trigger_the_fallback() -> None:
    """scenario-coverage: el margen es un `>` ESTRICTO — una mejora exactamente igual no dispara.

    `0.125` (= 1/8) y `0.5` son exactos en binario — a diferencia de `0.05`/`0.55`, cuya resta en
    float64 no da exactamente `0.05` (`0.55 - 0.50 == 0.050000000000000044`), lo que convertiría este
    test en un falso "mayor que" por precisión, no por el comportamiento real del `>` estricto."""
    filtered_hit = _hit("UC-FILTERED", 0.5)
    unfiltered_hit = _hit("UC-UNFILTERED", 0.625)  # delta == 0.125 == margin, exacto en binario
    retriever = _FakeRetriever({KbDomain.media_and_dam: [filtered_hit], None: [unfiltered_hit]})
    node = make_retrieve_node(retriever, top_k=8, domain_fallback_margin=0.125)

    result = await node(_state(classification=_classification(KbDomain.media_and_dam)))

    assert result["retrieved"] == [filtered_hit]


async def test_margin_is_read_from_the_configured_value_not_hardcoded() -> None:
    """scenario-coverage: el trigger lee `domain_fallback_margin`, no un umbral fijo en código — mismo
    delta (0.10), dos márgenes distintos, dos resultados distintos."""
    filtered_hit = _hit("UC-FILTERED", 0.50)
    unfiltered_hit = _hit("UC-UNFILTERED", 0.60)  # delta = 0.10

    retriever_low_margin = _FakeRetriever(
        {KbDomain.media_and_dam: [filtered_hit], None: [unfiltered_hit]}
    )
    node_low_margin = make_retrieve_node(retriever_low_margin, top_k=8, domain_fallback_margin=0.05)
    result_low = await node_low_margin(
        _state(classification=_classification(KbDomain.media_and_dam))
    )
    assert result_low["retrieved"] == [unfiltered_hit]

    retriever_high_margin = _FakeRetriever(
        {KbDomain.media_and_dam: [filtered_hit], None: [unfiltered_hit]}
    )
    node_high_margin = make_retrieve_node(
        retriever_high_margin, top_k=8, domain_fallback_margin=0.20
    )
    result_high = await node_high_margin(
        _state(classification=_classification(KbDomain.media_and_dam))
    )
    assert result_high["retrieved"] == [filtered_hit]


async def test_a_failure_in_the_unfiltered_retry_is_not_masked_by_the_filtered_result() -> None:
    """scenario-coverage: si la segunda búsqueda (sin filtro) falla tras haber tenido éxito la filtrada,
    el fallo se propaga — nunca se degrada en silencio al resultado filtrado (mismo principio que
    `Retriever`: un fallo de dependencia nunca se disfraza de resultado válido)."""
    retriever = _FakeRetriever(
        {KbDomain.media_and_dam: [_hit("UC-1", 0.5)]}, search_error_on_domain=None
    )
    node = make_retrieve_node(retriever, top_k=8, domain_fallback_margin=0.05)

    try:
        await node(_state(classification=_classification(KbDomain.media_and_dam)))
        raise AssertionError("se esperaba PortError")
    except PortError:
        pass


async def test_the_query_vector_is_embedded_once_and_reused_in_both_searches() -> None:
    """ADR-0019: la razón de negocio del refactor `embed_query`/`search` — la consulta se embebe UNA
    sola vez y ambas búsquedas (filtrada y sin filtro) usan ese mismo vector."""
    retriever = _FakeRetriever({KbDomain.media_and_dam: [_hit("UC-1", 0.5)]}, vector=[0.7, 0.8])
    node = make_retrieve_node(retriever, top_k=8, domain_fallback_margin=0.05)

    await node(_state(classification=_classification(KbDomain.media_and_dam)))

    assert retriever.embed_calls == ["¿cómo subo un vídeo?"]
    assert len(retriever.search_calls) == 2
    assert retriever.search_calls[0]["vector"] == [0.7, 0.8]
    assert retriever.search_calls[1]["vector"] == [0.7, 0.8]


async def test_every_comparison_is_logged_regardless_of_whether_the_fallback_wins() -> None:
    """scenario-coverage: el log se emite en TODA comparación (dominio asignado), gane o no el
    fallback — si solo logueara "cuando se dispara", los casos límite nunca se verían."""
    retriever_no_win = _FakeRetriever(
        {KbDomain.media_and_dam: [_hit("UC-A", 0.60)], None: [_hit("UC-B", 0.61)]}
    )
    node = make_retrieve_node(retriever_no_win, top_k=8, domain_fallback_margin=0.05)
    state = _state(classification=_classification(KbDomain.media_and_dam))

    with structlog.testing.capture_logs() as logs:
        await node(state)

    assert len(logs) == 1
    entry = logs[0]
    assert entry["event"] == "rag_domain_fallback_compared"
    assert entry["ticket_id"] == str(state["ticket_id"])
    assert entry["domain"] == "media-and-dam"
    assert entry["max_score_filtered"] == 0.60
    assert entry["max_score_unfiltered"] == 0.61
    assert entry["used_fallback"] is False


async def test_no_domain_assigned_does_not_log_the_comparison() -> None:
    """Sin dominio no hay comparación que loguear — solo se registra cuando hay dominio asignado."""
    retriever = _FakeRetriever()
    node = make_retrieve_node(retriever, top_k=5, domain_fallback_margin=DOMAIN_FALLBACK_MARGIN)

    with structlog.testing.capture_logs() as logs:
        await node(_state(classification=_classification(None)))

    assert logs == []


async def test_retrieved_hits_are_stored_in_state_without_deduplicating() -> None:
    """Los hits devueltos quedan en `state["retrieved"]`, tal cual (sin deduplicar, ADR-0018 D3a)."""
    ranked = _hit("CU-BE-05", 0.8)
    retriever = _FakeRetriever({None: [ranked]})
    node = make_retrieve_node(retriever, top_k=5, domain_fallback_margin=DOMAIN_FALLBACK_MARGIN)

    result = await node(_state(classification=None))

    assert result["retrieved"] == [ranked]
