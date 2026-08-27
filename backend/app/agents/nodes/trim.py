"""app.agents.nodes.trim — recorte de la ventana de contexto antes de invocar el LLM.

Aplica `trim_messages` sobre `state["messages"]` para acotar hilos largos (reaperturas) antes de
`generate`/`grade`. `token_counter=len` cuenta **mensajes**, no tokens reales: un contador de tokens
fiel exigiría el tokenizer del modelo concreto (fuera de alcance de este nodo — `max_tokens` aquí es un
tope de mensajes, no de tokens de OpenAI); mantiene el nodo puro y testeable sin red ni modelo real.

No altera la persistencia del histórico real (`Message` vive en `app.domain.entities`, no en el estado).
"""

from typing import cast

from langchain_core.messages import AnyMessage, trim_messages

from app.agents.nodes import NodeFn
from app.agents.state import HelpdeskState


def make_trim_node(max_tokens: int) -> NodeFn:
    """Factory-closure: conserva como máximo los `max_tokens` mensajes más recientes de `state["messages"]`."""

    async def node(state: HelpdeskState) -> HelpdeskState:
        trimmed = trim_messages(
            state["messages"], max_tokens=max_tokens, token_counter=len, strategy="last"
        )
        state["messages"] = cast(list[AnyMessage], trimmed)
        return state

    return node
