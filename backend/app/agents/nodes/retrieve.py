"""app.agents.nodes.retrieve — recuperación de contexto RAG (CU-BE-05, escenarios 1/1a/1c).

Invoca `app.rag.retriever.Retriever` con el `dominio` de `state["classification"]` como filtro; si no
hay clasificación con dominio (ticket no clasificable, o el nodo se testea aislado sin `classify`
previo) → **sin filtro de dominio** (fallback, CU-BE-05 1a), una única búsqueda.

Si SÍ hay dominio asignado, se reintenta SIEMPRE sin filtro (ADR-0019, CU-BE-05 1c): un caso real
observado con score filtrado ya por encima del umbral de confianza seguía siendo el dominio equivocado,
así que un umbral absoluto sobre el score filtrado no puede servir de trigger — el reintento es
incondicional, y solo la decisión de USAR el resultado sin filtro está gateada por
`domain_fallback_margin`. Ambas búsquedas reutilizan el mismo vector de la consulta (`embed_query` una
sola vez) para no pagar dos veces la llamada al proveedor de embeddings. Fija `state["retrieved"]`.
"""

import structlog

from app.agents.nodes import NodeFn
from app.agents.state import HelpdeskState
from app.rag.reranker import RankedHit
from app.rag.retriever import Retriever

_logger = structlog.get_logger(__name__)


def make_retrieve_node(retriever: Retriever, top_k: int, domain_fallback_margin: float) -> NodeFn:
    """Factory-closure: recupera contexto para el último mensaje del hilo, filtrado por dominio si lo
    hay, con el fallback ampliado de ADR-0019 cuando el dominio asignado da baja relevancia."""

    async def node(state: HelpdeskState) -> HelpdeskState:
        query = str(state["messages"][-1].content) if state["messages"] else ""
        classification = state["classification"]
        domain = classification.dominio if classification is not None else None

        vector = await retriever.embed_query(query)
        filtered = await retriever.search(vector, top_k=top_k, domain=domain)

        if domain is None:
            state["retrieved"] = filtered
            return state

        unfiltered = await retriever.search(vector, top_k=top_k, domain=None)
        max_filtered = _max_score(filtered)
        max_unfiltered = _max_score(unfiltered)
        used_fallback = (max_unfiltered - max_filtered) > domain_fallback_margin

        _logger.info(
            "rag_domain_fallback_compared",
            ticket_id=str(state["ticket_id"]),
            domain=domain.value,
            max_score_filtered=max_filtered,
            max_score_unfiltered=max_unfiltered,
            used_fallback=used_fallback,
        )

        state["retrieved"] = unfiltered if used_fallback else filtered
        return state

    return node


def _max_score(hits: list[RankedHit]) -> float:
    """`max(hit.score)` de `hits`, o `0.0` si está vacía — evita el `ValueError` de `max()` sobre una
    secuencia vacía cuando la búsqueda filtrada (o la sin filtro) no encuentra ningún hit."""
    return max((ranked.hit.score for ranked in hits), default=0.0)
