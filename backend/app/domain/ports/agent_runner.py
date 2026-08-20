"""app.domain.ports.agent_runner — puerto `AgentRunner` (`resume` de domain-services-08, `trigger`
nuevo de esta tarea).

`resume()` recibe `agent_run_id` (no un `thread_id` de LangGraph): `ApprovalTask` solo referencia el
`agent_run` por su `id` de dominio (no embebe la entidad `AgentRun` ni su `langgraph_thread_id`), y
`approval_service` deliberadamente **no** recibe `AgentRunRepository` para resolverlo (evita un roundtrip
extra y mantiene el servicio ajeno al detalle interno del checkpointer). Traducir `agent_run_id` al
`thread_id` real del grafo es responsabilidad del **adaptador** (tarea 16), que sí conoce esa relación.

`trigger()` es el disparo inicial (`POST /tickets/{id}/ai-draft`, 12): recibe `run_seq`/`thread_id` YA
calculados por `agent_service` (el adaptador no decide numeración ni construye el `thread_id`, solo
persiste el `AgentRun` y — cuando 15/16 exista — arranca el grafo). El adaptador de esta tarea
(`StubAgentRunner`) no ejecuta ningún nodo; el adaptador real es 15/16.
"""

import uuid
from dataclasses import dataclass
from typing import Protocol

from app.domain.entities.business import AgentRun
from app.domain.entities.enums import ApprovalStatus


@dataclass(frozen=True)
class ApprovalOutcome:
    """Resultado de una decisión HITL que el grafo necesita para continuar el run interrumpido."""

    status: ApprovalStatus
    final_body: str | None
    human_note: str | None


class AgentRunner(Protocol):
    """Puerto que dispara y reanuda un run de LangGraph."""

    async def trigger(
        self, tenant_id: uuid.UUID, ticket_id: uuid.UUID, run_seq: int, thread_id: str
    ) -> AgentRun:
        """Crea y arranca un `AgentRun` (`status=queued`) para `ticket_id` en `thread_id`.

        `run_seq`/`thread_id` los calcula `agent_service` (puerto `AgentRunRepository.next_run_seq` +
        `ticket_{id}_run_{n}`), no este adaptador — mismo criterio que `resume()`, que tampoco decide
        el `thread_id`. El adaptador STUB de esta tarea no ejecuta ningún nodo del grafo (15/16).

        :raises app.domain.errors.Conflict: si ya existe un `AgentRun` no-terminal para `ticket_id`
            (índice único parcial de `agent_run`, la garantía atómica real bajo concurrencia).
        :raises app.domain.errors.PortError: si el checkpointer/proveedor falla al arrancar.
        """
        ...

    async def resume(self, agent_run_id: uuid.UUID, outcome: ApprovalOutcome) -> None:
        """Reanuda el run asociado a `agent_run_id` con el `outcome` decidido.

        :raises app.domain.errors.PortError: si el checkpointer/proveedor falla al reanudar.
        """
        ...
