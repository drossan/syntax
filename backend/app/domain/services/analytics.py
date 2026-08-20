"""app.domain.services.analytics — resumen agregado del dashboard (FR-041).

Función suelta, sin clase de servicio (`grilling` P3 del plan `routers-flujo-ia`) — mismo criterio que
`classification.classify()`: sin estado que inyectar por constructor, una clase de un solo método sería
ceremonia sin beneficio. El agregado ya es correcto en SQL (`SqlAlchemyAnalyticsRepository`); esta
función es un passthrough directo, sin lógica de negocio propia.
"""

import uuid

from app.domain.entities.business import AnalyticsSummary
from app.domain.ports.analytics import AnalyticsRepository


async def summary(repo: AnalyticsRepository, tenant_id: uuid.UUID | None) -> AnalyticsSummary:
    """Resumen agregado, acotado a `tenant_id` (o cross-tenant si `None`, ámbito `global`)."""
    return await repo.summary(tenant_id)
