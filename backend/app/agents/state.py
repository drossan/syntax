"""app.agents.state — estado del grafo (`HelpdeskState`), agent-graph.md §3.

`TypedDict`, no Pydantic: es el estado de EJECUCIÓN de un run de LangGraph (lo serializa el
checkpointer, tarea 07), no una entidad de dominio persistida — `AgentRun`/`Ticket`/`ApprovalTask`
(`app.domain.entities.business`) son las entidades reales; los campos de aquí mapean a ellas al
persistir (`runner.py`, tareas 08/09), pero no las sustituyen.

Anti-patrón: guardar el histórico real de mensajes del ticket aquí — `messages` es el hilo de ESTE run
(recortado por `trim`, tarea 05), no el histórico persistido (`Message`, vive en `app.domain.entities`).
"""

import uuid
from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from app.agents.nodes.grade import Grade
from app.domain.ports.agent_runner import ApprovalOutcome
from app.domain.services.classification import Classification
from app.rag.reranker import RankedHit


class HelpdeskState(TypedDict):
    """Estado de un run del grafo `classify → retrieve → grade → generate → decide → [auto|HITL] → respond`."""

    messages: Annotated[list[AnyMessage], add_messages]
    tenant_id: uuid.UUID
    ticket_id: uuid.UUID
    auto_approve: bool
    """Resuelto UNA VEZ por `runner.trigger()` (tarea 08) al arrancar el run — `decide` (05) solo lo lee,
    sin `TenantRepository` propio (decisión de `grilling` #7)."""
    classification: Classification | None
    retrieved: list[RankedHit]
    grade: Grade | None
    confidence: float | None
    requires_approval: bool
    draft_response: str | None
    human_note: str | None
    human_decision: ApprovalOutcome | None
    """Fijado por `decide` (05) al reanudar tras `interrupt()`/`Command(resume=)` — lo lee `respond` (05)
    para decidir qué publicar (`approved`/`edited`/`rejected`)."""
