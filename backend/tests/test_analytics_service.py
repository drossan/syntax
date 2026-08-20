"""Tests de app.domain.services.analytics (tarea backend-routers-flujo-ia-05).

Nivel unit: función suelta (sin clase, mismo patrón que `classification.classify()`) — passthrough
directo al puerto, sin lógica adicional propia (el agregado ya es correcto en SQL).
"""

import uuid

from app.domain.entities.business import AnalyticsSummary
from app.domain.services.analytics import summary


class _FakeAnalyticsRepository:
    def __init__(self, result: AnalyticsSummary) -> None:
        self._result = result
        self.calls: list[uuid.UUID | None] = []

    async def summary(self, tenant_id: uuid.UUID | None) -> AnalyticsSummary:
        self.calls.append(tenant_id)
        return self._result


async def test_summary_delegates_to_the_repository_with_the_given_tenant_id() -> None:
    expected = AnalyticsSummary(
        tickets_by_status={"new": 1}, approvals_pending=2, avg_confidence=0.5, sla_breaches=0
    )
    repo = _FakeAnalyticsRepository(expected)
    tenant_id = uuid.uuid4()

    result = await summary(repo, tenant_id)

    assert result is expected
    assert repo.calls == [tenant_id]


async def test_summary_with_tenant_id_none_delegates_the_global_scope() -> None:
    expected = AnalyticsSummary(
        tickets_by_status={}, approvals_pending=0, avg_confidence=None, sla_breaches=0
    )
    repo = _FakeAnalyticsRepository(expected)

    result = await summary(repo, None)

    assert result is expected
    assert repo.calls == [None]
