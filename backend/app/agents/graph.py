"""app.agents.graph — `build_graph()`: ensambla los 7 nodos (tarea 05) en un `StateGraph` plano.

`classify → retrieve → grade → generate → decide → respond`, con UN único edge condicional tipado
(ADR-0008 — nunca texto libre del LLM): tras `classify`, si `classification.resoluble` es `False`
(CU-BE-05 extensión 1b), el grafo salta `retrieve`/`grade`/`generate` directo a `decide` — `decide` ya
trata `grade is None` como "escala siempre" (tarea 05), así que reutiliza esa regla en vez de introducir
un campo de estado nuevo: el ticket no-resoluble llega a un humano vía el mismo `interrupt()`, sin draft.

**NO compila con checkpointer todavía** — lo hace la tarea 08, con el `PostgresSaver` real de la tarea
07. `build_graph()` devuelve el `StateGraph` SIN compilar.
"""

from langgraph.graph import END, START, StateGraph

from app.agents.nodes.classify import make_classify_node
from app.agents.nodes.decide import make_decide_node
from app.agents.nodes.generate import make_generate_node
from app.agents.nodes.grade import make_grade_node
from app.agents.nodes.respond import make_respond_node
from app.agents.nodes.retrieve import make_retrieve_node
from app.agents.nodes.trim import make_trim_node
from app.agents.state import HelpdeskState
from app.domain.ports.llm import ChatModel
from app.domain.ports.repositories import MessageRepository
from app.domain.services.ticket_service import TicketService
from app.rag.retriever import Retriever


def build_graph(
    chat_model: ChatModel,
    retriever: Retriever,
    messages_repo: MessageRepository,
    ticket_service: TicketService,
    *,
    top_k: int,
    confidence_threshold: float,
    trim_max_tokens: int,
    domain_fallback_margin: float,
) -> StateGraph[HelpdeskState]:
    """Registra los 7 nodos y sus edges; devuelve el `StateGraph[HelpdeskState]` SIN compilar."""
    graph: StateGraph[HelpdeskState] = StateGraph(HelpdeskState)
    graph.add_node("trim", make_trim_node(trim_max_tokens))
    graph.add_node("classify", make_classify_node(chat_model))
    graph.add_node("retrieve", make_retrieve_node(retriever, top_k, domain_fallback_margin))
    graph.add_node("grade", make_grade_node(chat_model))
    graph.add_node("generate", make_generate_node(chat_model))
    graph.add_node("decide", make_decide_node(confidence_threshold))
    graph.add_node("respond", make_respond_node(messages_repo, ticket_service))

    graph.add_edge(START, "trim")
    graph.add_edge("trim", "classify")
    graph.add_conditional_edges(
        "classify", _route_after_classify, {"retrieve": "retrieve", "decide": "decide"}
    )
    graph.add_edge("retrieve", "grade")
    graph.add_edge("grade", "generate")
    graph.add_edge("generate", "decide")
    graph.add_edge("decide", "respond")
    graph.add_edge("respond", END)

    return graph


def _route_after_classify(state: HelpdeskState) -> str:
    """`classification.resoluble` (campo tipado, RN-1 de CU-BE-05) decide si el ticket sigue el camino
    RAG completo o escala directo, sin `generate` (CU-BE-05 extensión 1b)."""
    classification = state["classification"]
    if classification is not None and not classification.resoluble:
        return "decide"
    return "retrieve"
