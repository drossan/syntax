"""app.agents.nodes.decide — auto vs escalado (HITL gate), CU-BE-06 escenario principal paso 1.

Nodo **puro** (no captura ningún puerto, solo el umbral): calcula `requires_approval` a partir de
campos tipados del estado (RN-1 de CU-BE-05 — nunca texto libre del LLM) y, si escala, llama a
`langgraph.types.interrupt()` **inline, dentro de este mismo nodo**, con el payload de revisión. La
durabilidad ante reinicios la da compilar el grafo CON el checkpointer (tareas 07/08), no la estructura
de este nodo — un único `decide` concentra el cálculo y la llamada a `interrupt()`, en vez de un nodo
`interrupt` separado (decisión de `grilling`). Edge `decide → respond` es incondicional.
"""

from langgraph.types import interrupt

from app.agents.nodes import NodeFn
from app.agents.state import HelpdeskState


def make_decide_node(confidence_threshold: float) -> NodeFn:
    """Factory-closure: `requires_approval = (not auto_approve) OR confidence < threshold OR grade is
    None OR not grade.suficiente` — cualquiera de las cuatro condiciones fuerza HITL."""

    async def node(state: HelpdeskState) -> HelpdeskState:
        grade = state["grade"]
        confidence = state["confidence"] if state["confidence"] is not None else 0.0
        requires_approval = (
            not state["auto_approve"]
            or confidence < confidence_threshold
            or grade is None
            or not grade.suficiente
        )
        state["requires_approval"] = requires_approval
        if requires_approval:
            classification = state["classification"]
            motivo: str | None
            if grade is not None:
                motivo = grade.motivo
            elif classification is not None and not classification.resoluble:
                motivo = (
                    "El ticket se clasificó como no resoluble automáticamente; requiere revisión "
                    "manual."
                )
            else:
                motivo = state["human_note"]
            state["human_note"] = motivo
            payload = {
                "draft_response": state["draft_response"],
                "citations": state["retrieved"],
                "motivo": motivo,
            }
            state["human_decision"] = interrupt(payload)
        return state

    return node
