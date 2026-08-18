"""app.domain.ports.agent_runner — puerto `AgentRunner.resume` (nuevo, tarea 08 del plan domain-services).

`resume()` recibe `agent_run_id` (no un `thread_id` de LangGraph): `ApprovalTask` solo referencia el
`agent_run` por su `id` de dominio (no embebe la entidad `AgentRun` ni su `langgraph_thread_id`), y
`approval_service` deliberadamente **no** recibe `AgentRunRepository` para resolverlo (evita un roundtrip
extra y mantiene el servicio ajeno al detalle interno del checkpointer). Traducir `agent_run_id` al
`thread_id` real del grafo es responsabilidad del **adaptador** (tarea 16), que sí conoce esa relación.
"""

import uuid
from dataclasses import dataclass
from typing import Protocol

from app.domain.entities.enums import ApprovalStatus


@dataclass(frozen=True)
class ApprovalOutcome:
    """Resultado de una decisión HITL que el grafo necesita para continuar el run interrumpido."""

    status: ApprovalStatus
    final_body: str | None
    human_note: str | None


class AgentRunner(Protocol):
    """Puerto que reanuda un run de LangGraph interrumpido en espera de aprobación humana."""

    async def resume(self, agent_run_id: uuid.UUID, outcome: ApprovalOutcome) -> None:
        """Reanuda el run asociado a `agent_run_id` con el `outcome` decidido.

        :raises app.domain.errors.PortError: si el checkpointer/proveedor falla al reanudar.
        """
        ...
