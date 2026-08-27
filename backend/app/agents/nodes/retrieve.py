"""app.agents.nodes.retrieve — recuperación de contexto RAG (CU-BE-05, escenarios 1/1a).

Invoca `app.rag.retriever.Retriever` con el `dominio` de `state["classification"]` como filtro; si no
hay clasificación con dominio (ticket no clasificable, o el nodo se testea aislado sin `classify`
previo) → **sin filtro de dominio** (fallback, CU-BE-05 1a). Fija `state["retrieved"]`.
"""

from app.agents.nodes import NodeFn
from app.agents.state import HelpdeskState
from app.rag.retriever import Retriever


def make_retrieve_node(retriever: Retriever, top_k: int) -> NodeFn:
    """Factory-closure: recupera contexto para el último mensaje del hilo, filtrado por dominio si lo hay."""

    async def node(state: HelpdeskState) -> HelpdeskState:
        query = str(state["messages"][-1].content) if state["messages"] else ""
        classification = state["classification"]
        domain = classification.dominio if classification is not None else None
        state["retrieved"] = await retriever.retrieve(query, top_k=top_k, domain=domain)
        return state

    return node
