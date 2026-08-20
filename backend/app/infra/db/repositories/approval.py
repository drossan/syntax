"""app.infra.db.repositories.approval — adaptador SQLAlchemy de `ApprovalRepository` (tarea 12).

Primer adaptador real de este puerto (nacido en `domain-services`, sin implementación hasta ahora).
`list()` ordena por `ticket.sla_due, agent_run.confidence` (contrato, `api-contract.yaml`) — ninguna de
las dos columnas vive en `approval_task`, así que requiere `JOIN` con `ticket`/`agent_run`.
`decide_if_pending` es el CAS real: **una sola sentencia** `UPDATE ... WHERE status='pending' ...
RETURNING` (mismo patrón que `SqlAlchemyRefreshSessionRepository.rotate_if_active`), nunca `get`+`if`+
`update` en pasos separados.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.business import ApprovalTask
from app.domain.entities.enums import ApprovalStatus
from app.domain.errors import NotFound, PortError
from app.domain.ports.repositories import PageResult
from app.infra.db.models import AgentRun as AgentRunModel
from app.infra.db.models import ApprovalTask as ApprovalTaskModel
from app.infra.db.models import Ticket as TicketModel
from app.infra.db.models.enums import ApprovalStatus as ApprovalStatusOrm
from app.infra.db.repositories._enum_bridge import to_domain, to_orm


def _to_domain(row: ApprovalTaskModel) -> ApprovalTask:
    return ApprovalTask(
        id=row.id,
        tenant_id=row.tenant_id,
        ticket_id=row.ticket_id,
        agent_run_id=row.agent_run_id,
        status=to_domain(ApprovalStatus, row.status),
        draft_body=row.draft_body,
        final_body=row.final_body,
        human_note=row.human_note,
        decided_by=row.decided_by,
        decided_at=row.decided_at,
        created_at=row.created_at,
    )


class SqlAlchemyApprovalRepository:
    """Adaptador de `ApprovalRepository` (`app.domain.ports.repositories`)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, task: ApprovalTask) -> ApprovalTask:
        row = ApprovalTaskModel(
            id=task.id,
            tenant_id=task.tenant_id,
            ticket_id=task.ticket_id,
            agent_run_id=task.agent_run_id,
            status=to_orm(ApprovalStatusOrm, task.status),
            draft_body=task.draft_body,
            final_body=task.final_body,
            human_note=task.human_note,
            decided_by=task.decided_by,
            decided_at=task.decided_at,
        )
        self._session.add(row)
        try:
            await self._session.flush()
        except Exception as exc:
            raise PortError("fallo al crear approval_task") from exc
        return _to_domain(row)

    async def list(
        self,
        tenant_id: uuid.UUID | None,
        *,
        status: ApprovalStatus | None = None,
        sort: str = "sla_due,confidence",
        page: int,
        page_size: int,
    ) -> PageResult[ApprovalTask]:
        wanted_status = status if status is not None else ApprovalStatus.pending
        conditions = [ApprovalTaskModel.status == to_orm(ApprovalStatusOrm, wanted_status)]
        if tenant_id is not None:
            conditions.append(ApprovalTaskModel.tenant_id == tenant_id)
        offset = (page - 1) * page_size
        try:
            total = (
                await self._session.execute(
                    select(func.count()).select_from(ApprovalTaskModel).where(*conditions)
                )
            ).scalar_one()
            rows = (
                await self._session.execute(
                    select(ApprovalTaskModel)
                    .join(TicketModel, TicketModel.id == ApprovalTaskModel.ticket_id)
                    .join(AgentRunModel, AgentRunModel.id == ApprovalTaskModel.agent_run_id)
                    .where(*conditions)
                    .order_by(TicketModel.sla_due.asc(), AgentRunModel.confidence.asc())
                    .offset(offset)
                    .limit(page_size)
                )
            ).scalars()
            items = [_to_domain(row) for row in rows]
        except Exception as exc:
            raise PortError("fallo al listar approval_task") from exc
        return PageResult(items=items, total=total)

    async def decide_if_pending(
        self,
        task_id: uuid.UUID,
        decision: str,
        final_body: str | None,
        human_note: str | None,
    ) -> ApprovalTask | None:
        stmt = (
            update(ApprovalTaskModel)
            .where(
                ApprovalTaskModel.id == task_id,
                ApprovalTaskModel.status == ApprovalStatusOrm.pending,
            )
            .values(
                status=to_orm(ApprovalStatusOrm, ApprovalStatus(decision)),
                final_body=final_body,
                human_note=human_note,
                decided_at=datetime.now(UTC),
            )
            .returning(ApprovalTaskModel)
        )
        try:
            updated_row = (await self._session.execute(stmt)).scalar_one_or_none()
        except Exception as exc:
            raise PortError("fallo al decidir approval_task") from exc
        if updated_row is not None:
            return _to_domain(updated_row)

        try:
            exists = (
                await self._session.execute(
                    select(ApprovalTaskModel.id).where(ApprovalTaskModel.id == task_id)
                )
            ).scalar_one_or_none()
        except Exception as exc:
            raise PortError("fallo al comprobar approval_task") from exc
        if exists is None:
            raise NotFound(f"approval task {task_id} no existe", code="approval.not_found")
        return None
