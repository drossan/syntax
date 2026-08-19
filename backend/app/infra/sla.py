"""app.infra.sla — adaptador STUB del puerto `SlaPolicy` (política real: tarea 18).

`data-model.md §11` deja la política real (horas/días por prioridad) explícitamente indefinida y fuera
de esta fase — inventar aquí un valor (p.ej. "urgent = 4h") sería una decisión de negocio no pedida por
ningún spec. `due_at` devuelve siempre `None` (sin vencimiento) hasta que la tarea 18 (scheduler de SLA)
implemente la política real; `Ticket.sla_due` ya es nullable para este caso.
"""

import uuid
from datetime import datetime

from app.domain.entities.enums import TicketPriority


class StubSlaPolicy:
    """Adaptador STUB de `SlaPolicy`: sin política real todavía (tarea 18)."""

    def due_at(
        self, priority: TicketPriority, from_: datetime, tenant_id: uuid.UUID
    ) -> datetime | None:
        return None
