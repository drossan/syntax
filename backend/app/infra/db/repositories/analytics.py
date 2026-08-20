"""app.infra.db.repositories.analytics — adaptador SQLAlchemy de `AnalyticsRepository` (tarea 12).

Un agregado SQL por métrica (no en Python): `tickets_by_status` vía `GROUP BY` (rellenado con las 6
claves de `TicketStatus` a `0` tras la query, ya que `GROUP BY` puro solo devuelve los status con al
menos un ticket); `approvals_pending` y `sla_breaches` vía `COUNT(*)` filtrado;
`avg_confidence` vía `AVG(...)` sobre las filas con `confidence IS NOT NULL` (sin filas → `AVG`
de Postgres ya devuelve `NULL`, se propaga tal cual — nunca `NaN` ni división por cero).
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.business import AnalyticsSummary
from app.domain.entities.enums import TicketStatus
from app.domain.errors import PortError
from app.infra.db.models import AgentRun as AgentRunModel
from app.infra.db.models import ApprovalTask as ApprovalTaskModel
from app.infra.db.models import Ticket as TicketModel
from app.infra.db.models.enums import ApprovalStatus as ApprovalStatusOrm
from app.infra.db.models.enums import TicketStatus as TicketStatusOrm

_TERMINAL_STATUSES = (TicketStatusOrm.resolved, TicketStatusOrm.closed)


class SqlAlchemyAnalyticsRepository:
    """Adaptador de `AnalyticsRepository` (`app.domain.ports.analytics`)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def summary(self, tenant_id: uuid.UUID | None) -> AnalyticsSummary:
        ticket_scope = () if tenant_id is None else (TicketModel.tenant_id == tenant_id,)
        approval_scope = () if tenant_id is None else (ApprovalTaskModel.tenant_id == tenant_id,)
        agent_run_scope = () if tenant_id is None else (AgentRunModel.tenant_id == tenant_id,)

        try:
            status_rows = (
                await self._session.execute(
                    select(TicketModel.status, func.count())
                    .where(*ticket_scope)
                    .group_by(TicketModel.status)
                )
            ).all()
            tickets_by_status = {status.value: 0 for status in TicketStatus}
            for status_orm, count in status_rows:
                tickets_by_status[status_orm.value] = count

            approvals_pending = (
                await self._session.execute(
                    select(func.count())
                    .select_from(ApprovalTaskModel)
                    .where(*approval_scope, ApprovalTaskModel.status == ApprovalStatusOrm.pending)
                )
            ).scalar_one()

            avg_confidence = (
                await self._session.execute(
                    select(func.avg(AgentRunModel.confidence)).where(
                        *agent_run_scope, AgentRunModel.confidence.is_not(None)
                    )
                )
            ).scalar_one()

            sla_breaches = (
                await self._session.execute(
                    select(func.count())
                    .select_from(TicketModel)
                    .where(
                        *ticket_scope,
                        TicketModel.sla_due < func.now(),
                        TicketModel.status.notin_(_TERMINAL_STATUSES),
                    )
                )
            ).scalar_one()
        except Exception as exc:
            raise PortError("fallo al calcular analytics summary") from exc

        return AnalyticsSummary(
            tickets_by_status=tickets_by_status,
            approvals_pending=approvals_pending,
            avg_confidence=float(avg_confidence) if avg_confidence is not None else None,
            sla_breaches=sla_breaches,
        )
