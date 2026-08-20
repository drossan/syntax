"""app.api.v1.routers.analytics — resumen agregado del dashboard (contrato 06/12).

`tenant_id = None` (agrega cross-tenant) cuando el subject tiene `analytics.read` en ámbito `global`;
`subject.tenant_id` en ámbito `tenant` — mismo patrón que `approvals.py` (tarea 02). Sin CU dedicado
(decisión del owner, `grilling`): FR-041 en `spec.md` es la única fuente EARS.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.analytics import AnalyticsSummary as AnalyticsSummarySchema
from app.core.deps import get_analytics_repository, require_capability
from app.domain.entities.business import AnalyticsSummary as AnalyticsSummaryEntity
from app.domain.entities.identity import Subject
from app.domain.ports.analytics import AnalyticsRepository
from app.domain.services.analytics import summary

router = APIRouter(prefix="/analytics", tags=["analytics"])

_CAPABILITY = "analytics.read"


def _to_schema(entity: AnalyticsSummaryEntity) -> AnalyticsSummarySchema:
    return AnalyticsSummarySchema(
        tickets_by_status=entity.tickets_by_status,
        approvals_pending=entity.approvals_pending,
        avg_confidence=entity.avg_confidence,
        sla_breaches=entity.sla_breaches,
    )


@router.get("/summary")
async def get_summary(
    subject_session: tuple[Subject, AsyncSession] = Depends(require_capability(_CAPABILITY)),
    analytics_repository: AnalyticsRepository = Depends(get_analytics_repository),
) -> AnalyticsSummarySchema:
    subject, _session = subject_session
    tenant_id = None if (_CAPABILITY, "global") in subject.capabilities else subject.tenant_id
    result = await summary(analytics_repository, tenant_id)
    return _to_schema(result)
