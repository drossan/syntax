"""app.api.v1.schemas.analytics — DTO del router `analytics` (1:1 con `api-contract.yaml`)."""

from pydantic import BaseModel


class AnalyticsSummary(BaseModel):
    tickets_by_status: dict[str, int]
    approvals_pending: int
    avg_confidence: float | None = None
    sla_breaches: int
