"""app.infra.agent_runner.stub — adaptador STUB del puerto `AgentRunner` (tarea 12).

Sin implementación real hasta las tareas 15 (grafo)/16 (checkpointer + HITL). `trigger()` construye el
`AgentRun` (`status=queued`) y lo persiste vía `AgentRunRepository.add()` — **sin ejecutar ningún nodo
del grafo**, pero SÍ crea la fila real: el CAS bajo concurrencia vive en el índice único parcial que ese
`add()` traduce a `Conflict` (`SqlAlchemyAgentRunRepository`), y este adaptador es el único punto de la
capa de dominio que llama a `add()` — `agent_service` solo lee (`get_active_for_ticket`/`next_run_seq`/
`get`), nunca escribe `agent_run` directamente. El adaptador real (15/16) sustituye esta clase sin tocar
`agent_service` ni el router `agent` — mismo criterio que `StubVectorStore`/`StubSlaPolicy`.

`resume()` es también un no-op: sin grafo real que reanudar, no hay nada que hacer todavía (consumidor
real: 16).
"""

import uuid

from app.domain.entities.business import AgentRun
from app.domain.entities.enums import AgentRunStatus
from app.domain.ports.agent_runner import ApprovalOutcome
from app.domain.ports.repositories import AgentRunRepository


class StubAgentRunner:
    """Adaptador STUB de `AgentRunner`: `trigger()` persiste el `AgentRun` sin arrancar ningún grafo."""

    def __init__(self, agent_runs: AgentRunRepository) -> None:
        self._agent_runs = agent_runs

    async def trigger(
        self, tenant_id: uuid.UUID, ticket_id: uuid.UUID, run_seq: int, thread_id: str
    ) -> AgentRun:
        run = AgentRun(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            ticket_id=ticket_id,
            langgraph_thread_id=thread_id,
            run_seq=run_seq,
            status=AgentRunStatus.queued,
            confidence=None,
            escalated=False,
            sources=None,
            error=None,
            langsmith_trace_url=None,
        )
        return await self._agent_runs.add(run)

    async def resume(self, agent_run_id: uuid.UUID, outcome: ApprovalOutcome) -> None:
        return None
