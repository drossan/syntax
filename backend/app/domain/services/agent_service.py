"""app.domain.services.agent_service — disparo y lectura de un run de agente (FR-022, CU-BE-06
ampliado por esta tarea con los escenarios de disparo).

`trigger()` compone 4 puertos en orden de coste creciente (`scenario-coverage` #1/#3): ticket
existe/tenant (`NotFound`, el chequeo más barato) → run activo (`Conflict`, pre-check best-effort,
consulta de lectura) → rate-limit (`RateLimited`, consume cuota) → creación (`agent_runner.trigger()`,
la garantía **atómica** real bajo concurrencia vive en el índice único parcial que el adaptador traduce
a `Conflict`, el pre-check de arriba es solo optimización). Ningún chequeo posterior corre si uno
anterior falla — un disparo que iba a fallar gratis no gasta cuota de rate-limit ni toca la constraint
de BD.
"""

import uuid

from app.domain.entities.business import AgentRun
from app.domain.errors import Conflict, NotFound, RateLimited
from app.domain.ports.agent_runner import AgentRunner
from app.domain.ports.rate_limiter import RateLimiter
from app.domain.ports.repositories import AgentRunRepository, TicketRepository


class AgentService:
    """Disparo (`trigger`) y lectura (`get`) de un `AgentRun`. Puertos por inyección de constructor."""

    def __init__(
        self,
        tickets: TicketRepository,
        agent_runs: AgentRunRepository,
        agent_runner: AgentRunner,
        rate_limiter: RateLimiter,
    ) -> None:
        self._tickets = tickets
        self._agent_runs = agent_runs
        self._agent_runner = agent_runner
        self._rate_limiter = rate_limiter

    async def trigger(self, tenant_id: uuid.UUID, ticket_id: uuid.UUID) -> AgentRun:
        """Dispara un draft IA para `ticket_id` (`POST /tickets/{id}/ai-draft`) sin ejecutar el grafo
        real (`classify→retrieve→grade→generate→decide`, FR-022) — eso es 15/16.

        :raises app.domain.errors.NotFound: si el ticket no existe (el ámbito de tenant ya lo resolvió
            el router vía RLS, mismo patrón que `ticket_service.get`).
        :raises app.domain.errors.Conflict: si ya hay un `AgentRun` no-terminal (`queued`/`running`)
            para el ticket.
        :raises app.domain.errors.RateLimited: si el tenant excede
            `Settings.ai_draft_rate_limit_per_minute` en la ventana actual.
        """
        ticket = await self._tickets.get(ticket_id)
        if ticket is None:
            raise NotFound(f"ticket {ticket_id} no existe", code="agent_run.ticket_not_found")

        active = await self._agent_runs.get_active_for_ticket(ticket_id)
        if active is not None:
            raise Conflict(
                f"ya hay un run activo para el ticket {ticket_id}",
                code="agent_run.active_run_exists",
            )

        if not await self._rate_limiter.check_and_increment(str(tenant_id)):
            raise RateLimited(f"límite de ai-draft excedido para el tenant {tenant_id}")

        run_seq = await self._agent_runs.next_run_seq(ticket_id)
        thread_id = f"ticket_{ticket_id}_run_{run_seq}"
        return await self._agent_runner.trigger(tenant_id, ticket_id, run_seq, thread_id)

    async def get(self, agent_run_id: uuid.UUID) -> AgentRun:
        """`GET /agent-runs/{id}`: `NotFound` si no existe (ámbito de tenant ya resuelto por el
        router — un run de otro tenant es invisible, nunca 403)."""
        run = await self._agent_runs.get(agent_run_id)
        if run is None:
            raise NotFound(f"agent_run {agent_run_id} no existe", code="agent_run.not_found")
        return run

    async def get_active_for_ticket(self, ticket_id: uuid.UUID) -> AgentRun | None:
        """`GET /tickets/{id}/agent-runs/active`: el run no-terminal (`queued`/`running`) de
        `ticket_id`, o `None` si no hay ninguno — a diferencia de `get()`, "sin run activo" es un
        resultado legítimo (p.ej. nadie lo ha disparado todavía), nunca `NotFound`. Reutiliza el
        mismo pre-check de `trigger()` (`AgentRunRepository.get_active_for_ticket`), no duplica lógica.

        Cierra el gap de descubrimiento: con `tenant.ai_auto_draft` el run se crea en el servidor sin
        que el cliente lo dispare, así que nunca recibe el `id` en la respuesta de `POST /tickets` —
        sin este método, un cliente que abre el ticket tras el auto-disparo no tiene forma de saber
        que ya hay un draft en curso."""
        return await self._agent_runs.get_active_for_ticket(ticket_id)
