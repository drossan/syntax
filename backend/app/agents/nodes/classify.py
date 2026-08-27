"""app.agents.nodes.classify — clasificación tipada del ticket (CU-BE-05, escenario 1).

Delega en `app.domain.services.classification.classify()` (ya real, plan `domain-services`): este nodo
solo extrae el texto del ticket del estado y fija `state["classification"]`, sin reimplementar la
llamada al LLM ni el mapeo de errores (ya los resuelve el servicio de dominio).

**Prompt-injection (RN-3 de CU-BE-06)**: el texto del ticket se reenvía TAL CUAL a `chat_model.classify`
— nunca se parsea, nunca se ejecutan instrucciones que contenga. `dominio` filtra el `retrieve` siguiente.
"""

from app.agents.nodes import NodeFn
from app.agents.state import HelpdeskState
from app.domain.ports.llm import ChatModel
from app.domain.services.classification import classify


def make_classify_node(chat_model: ChatModel) -> NodeFn:
    """Factory-closure: clasifica el último mensaje del hilo y fija `state["classification"]`."""

    async def node(state: HelpdeskState) -> HelpdeskState:
        ticket_text = str(state["messages"][-1].content) if state["messages"] else ""
        state["classification"] = await classify(ticket_text, chat_model)
        return state

    return node
