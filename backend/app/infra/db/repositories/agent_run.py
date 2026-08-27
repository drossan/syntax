"""app.infra.db.repositories.agent_run — adaptador SQLAlchemy de `AgentRunRepository` (tarea 12).

`add()` es el punto donde vive el CAS real: captura la violación del índice único parcial
`ix_agent_run_active_per_ticket` (`agent_run(ticket_id) WHERE status IN ('queued', 'running')`, migración
0003) vía `IntegrityError` y la traduce a `app.domain.errors.Conflict` — la garantía atómica bajo
concurrencia vive en la constraint de Postgres, no en `get_active_for_ticket` (ese es solo un pre-check
best-effort de `agent_service`, sin garantía bajo carrera).
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.business import AgentRun
from app.domain.entities.enums import AgentRunStatus
from app.domain.errors import Conflict, PortError
from app.infra.db.models import AgentRun as AgentRunModel
from app.infra.db.models.enums import AgentRunStatus as AgentRunStatusOrm
from app.infra.db.repositories._enum_bridge import to_domain, to_orm

_ACTIVE_STATUSES = (AgentRunStatusOrm.queued, AgentRunStatusOrm.running)


def _to_domain(row: AgentRunModel) -> AgentRun:
    return AgentRun(
        id=row.id,
        tenant_id=row.tenant_id,
        ticket_id=row.ticket_id,
        langgraph_thread_id=row.langgraph_thread_id,
        run_seq=row.run_seq,
        status=to_domain(AgentRunStatus, row.status),
        confidence=row.confidence,
        escalated=row.escalated,
        sources=row.sources,
        error=row.error,
        langsmith_trace_url=row.langsmith_trace_url,
        created_at=row.created_at,
        finished_at=row.finished_at,
    )


class SqlAlchemyAgentRunRepository:
    """Adaptador de `AgentRunRepository` (`app.domain.ports.repositories`)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, agent_run_id: uuid.UUID) -> AgentRun | None:
        try:
            row = await self._session.get(AgentRunModel, agent_run_id)
        except Exception as exc:
            raise PortError("fallo al leer agent_run") from exc
        return _to_domain(row) if row is not None else None

    async def add(self, run: AgentRun) -> AgentRun:
        row = AgentRunModel(
            id=run.id,
            tenant_id=run.tenant_id,
            ticket_id=run.ticket_id,
            langgraph_thread_id=run.langgraph_thread_id,
            run_seq=run.run_seq,
            status=to_orm(AgentRunStatusOrm, run.status),
            confidence=run.confidence,
            escalated=run.escalated,
            sources=run.sources,
            error=run.error,
            langsmith_trace_url=run.langsmith_trace_url,
        )
        self._session.add(row)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise Conflict(
                f"ya hay un run activo para el ticket {run.ticket_id}",
                code="agent_run.active_run_exists",
            ) from exc
        except Exception as exc:
            raise PortError("fallo al crear agent_run") from exc
        return _to_domain(row)

    async def update_status(self, agent_run_id: uuid.UUID, status: str) -> AgentRun:
        try:
            row = await self._session.get(AgentRunModel, agent_run_id)
        except Exception as exc:
            raise PortError("fallo al leer agent_run") from exc
        if row is None:
            raise PortError(f"agent_run {agent_run_id} no existe")
        row.status = to_orm(AgentRunStatusOrm, AgentRunStatus(status))
        try:
            await self._session.flush()
            await self._session.refresh(row)
        except Exception as exc:
            raise PortError("fallo al actualizar agent_run") from exc
        return _to_domain(row)

    async def update_result(
        self,
        agent_run_id: uuid.UUID,
        *,
        status: AgentRunStatus,
        confidence: float | None = None,
        sources: list[dict[str, Any]] | None = None,
        error: str | None = None,
        escalated: bool | None = None,
        finished_at: datetime | None = None,
        langsmith_trace_url: str | None = None,
    ) -> AgentRun:
        try:
            row = await self._session.get(AgentRunModel, agent_run_id)
        except Exception as exc:
            raise PortError("fallo al leer agent_run") from exc
        if row is None:
            raise PortError(f"agent_run {agent_run_id} no existe")
        row.status = to_orm(AgentRunStatusOrm, status)
        row.confidence = confidence
        row.sources = sources
        row.error = error
        row.escalated = bool(escalated)
        row.finished_at = finished_at
        row.langsmith_trace_url = langsmith_trace_url
        try:
            await self._session.flush()
            await self._session.refresh(row)
        except Exception as exc:
            raise PortError("fallo al actualizar el resultado de agent_run") from exc
        return _to_domain(row)

    async def next_run_seq(self, ticket_id: uuid.UUID) -> int:
        try:
            max_seq = (
                await self._session.execute(
                    select(func.max(AgentRunModel.run_seq)).where(
                        AgentRunModel.ticket_id == ticket_id
                    )
                )
            ).scalar_one()
        except Exception as exc:
            raise PortError("fallo al calcular next_run_seq") from exc
        return 1 if max_seq is None else max_seq + 1

    async def get_active_for_ticket(self, ticket_id: uuid.UUID) -> AgentRun | None:
        try:
            row = (
                (
                    await self._session.execute(
                        select(AgentRunModel).where(
                            AgentRunModel.ticket_id == ticket_id,
                            AgentRunModel.status.in_(_ACTIVE_STATUSES),
                        )
                    )
                )
                .scalars()
                .first()
            )
        except Exception as exc:
            raise PortError("fallo al leer el run activo del ticket") from exc
        return _to_domain(row) if row is not None else None
