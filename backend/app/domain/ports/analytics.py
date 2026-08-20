"""app.domain.ports.analytics — puerto `AnalyticsRepository` (recortado a `summary()`, tarea 12).

`tenant_id=None` agrega **cross-tenant** (ámbito `global` de `analytics.read`, Soporte); con
`tenant_id` fijo, acota los agregados a ese tenant. Mismo criterio que `ApprovalRepository.list` de la
tarea 02: el puerto no comparte el árbol de `app.domain.ports.repositories` (recurso de solo lectura,
sin CAS ni paginación).
"""

import uuid
from typing import Protocol

from app.domain.entities.business import AnalyticsSummary


class AnalyticsRepository(Protocol):
    """Puerto de agregados de analytics."""

    async def summary(self, tenant_id: uuid.UUID | None) -> AnalyticsSummary:
        """Agregados del dashboard, acotados a `tenant_id` (o cross-tenant si `None`)."""
        ...
