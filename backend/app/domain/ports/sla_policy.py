"""app.domain.ports.sla_policy — puerto de política de SLA (nace con `ticket_service`).

`data-model.md §11` deja la política real (horas/días por prioridad) explícitamente indefinida: "solo se
modelan `priority`+`sla_due`; el cómputo es 18". Este puerto se diseña ya pensando en que la tarea 18
(scheduler) necesitará la misma política para el escalado — de ahí `tenant_id` en la firma (política
potencialmente por tenant) — pero **no fija ningún valor real** aquí.
"""

import uuid
from datetime import datetime
from typing import Protocol

from app.domain.entities.enums import TicketPriority


class SlaPolicy(Protocol):
    """Calcula el `sla_due` de un ticket a partir de su prioridad."""

    def due_at(
        self, priority: TicketPriority, from_: datetime, tenant_id: uuid.UUID
    ) -> datetime | None:
        """Vencimiento de SLA, o `None` si la prioridad no tiene política de vencimiento asociada."""
        ...
