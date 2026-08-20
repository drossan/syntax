"""app.api.v1.routers.agent — disparo del agente y estado del run (contrato 06/12).

Primer router que expone una capacidad **compuesta** (`require_any_capability`, `app.core.deps`):
`GET /agent-runs/{id}` se protege con `agent.trigger` OR `ticket.read` — un `support_viewer`/
`client_viewer` (sin `agent.trigger`) puede consultar el estado de un draft de un ticket que ya puede
leer, sin poder dispararlo. El grafo real (15/16) no existe todavía: `agent_service.trigger()` compone
`StubAgentRunner` (crea el `AgentRun`, no ejecuta ningún nodo) — ver `agent_service.py`/`stub.py`.
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.agent import AgentRun as AgentRunSchema
from app.api.v1.schemas.agent import Citation
from app.core.deps import get_agent_service, require_any_capability, require_capability
from app.domain.entities.business import AgentRun as AgentRunEntity
from app.domain.entities.identity import Subject
from app.domain.services.agent_service import AgentService

router = APIRouter(tags=["ai-flow"])

_TRIGGER_CAPABILITY = "agent.trigger"
_READ_CAPABILITIES = ("agent.trigger", "ticket.read")


def _to_schema(run: AgentRunEntity) -> AgentRunSchema:
    return AgentRunSchema(
        id=run.id,
        ticket_id=run.ticket_id,
        run_seq=run.run_seq,
        status=run.status.value,
        confidence=run.confidence,
        escalated=run.escalated,
        sources=[Citation(**source) for source in run.sources] if run.sources else [],
        error=run.error,
        langsmith_trace_url=run.langsmith_trace_url,
        created_at=run.created_at,
        finished_at=run.finished_at,
    )


@router.post("/tickets/{id}/ai-draft", status_code=status.HTTP_202_ACCEPTED)
async def trigger_ai_draft(
    id: uuid.UUID,
    subject_session: tuple[Subject, AsyncSession] = Depends(
        require_capability(_TRIGGER_CAPABILITY)
    ),
    agent_service: AgentService = Depends(get_agent_service),
) -> AgentRunSchema:
    subject, _session = subject_session
    run = await agent_service.trigger(subject.tenant_id, id)
    return _to_schema(run)


@router.get("/agent-runs/{id}")
async def get_agent_run(
    id: uuid.UUID,
    subject_session: tuple[Subject, AsyncSession] = Depends(
        require_any_capability(*_READ_CAPABILITIES)
    ),
    agent_service: AgentService = Depends(get_agent_service),
) -> AgentRunSchema:
    _subject, _session = subject_session
    run = await agent_service.get(id)
    return _to_schema(run)
