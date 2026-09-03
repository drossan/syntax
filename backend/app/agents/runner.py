"""app.agents.runner — `LangGraphAgentRunner` completo (`trigger`/`resume`, ADR-0007, núcleo de riesgo).

Implementa `AgentRunner` (`app.domain.ports.agent_runner`) sobre el grafo real (`build_graph`, tarea
06) compilado con el checkpointer real (`get_checkpointer`, tarea 07). `trigger()` cubre el camino
**auto** (sin HITL, `respond` publica directo) y el que llega a `interrupt()` y queda pendiente de
aprobación (crea la `ApprovalTask`, mapeo 1:1 interrupt↔ApprovalTask). `resume()` reanuda tras la
decisión humana (`hitl.py`, tarea 09) — el estado vive SOLO en el checkpoint Postgres, así que una
instancia nueva del runner (proceso reiniciado) reanuda igual de bien que la original.

**NO es un singleton de proceso**: se construye por request (mismo criterio que `StubAgentRunner`,
decisión de diseño #4 del plan) — evita que el `MessageRepository` con sesión de una request quede
capturado en un objeto de vida más larga. `build_graph()` (estructura del grafo, sin I/O) se construye
en `__init__`; `.compile(checkpointer=...)` se hace en `trigger()`/`resume()` porque
`get_checkpointer()` es `async` (abre el pool en el primer uso real) y `__init__` no puede `await` —
`.compile()` en sí es barato (solo wiring, sin I/O), así que repetirlo por llamada no cuesta nada real.
"""

import uuid
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tracers.context import tracing_v2_enabled
from langsmith import Client

from app.agents.checkpointer import get_checkpointer
from app.agents.graph import build_graph
from app.agents.hitl import to_resume_command
from app.agents.state import HelpdeskState
from app.domain.entities.business import AgentRun, ApprovalTask
from app.domain.entities.enums import AgentRunStatus, ApprovalStatus, MessageVisibility
from app.domain.errors import NotFound, PortError
from app.domain.ports.agent_runner import ApprovalOutcome
from app.domain.ports.clock import Clock
from app.domain.ports.llm import ChatModel
from app.domain.ports.repositories import (
    AgentRunRepository,
    ApprovalRepository,
    MessageRepository,
    TenantRepository,
)
from app.domain.services.ticket_service import TicketService
from app.rag.citations import build_citations
from app.rag.retriever import Retriever


class LangGraphAgentRunner:
    """Adaptador real de `AgentRunner` sobre el grafo (06) + checkpointer (07)."""

    def __init__(
        self,
        *,
        chat_model: ChatModel,
        retriever: Retriever,
        messages_repo: MessageRepository,
        tenants: TenantRepository,
        agent_runs: AgentRunRepository,
        approvals: ApprovalRepository,
        ticket_service: TicketService,
        clock: Clock,
        top_k: int,
        confidence_threshold: float,
        trim_max_tokens: int,
        domain_fallback_margin: float,
        langsmith_tracing: bool = False,
        langsmith_api_key: str = "",
        langsmith_project: str = "syntax",
    ) -> None:
        self._messages_repo = messages_repo
        self._tenants = tenants
        self._agent_runs = agent_runs
        self._approvals = approvals
        self._clock = clock
        self._graph = build_graph(
            chat_model,
            retriever,
            messages_repo,
            ticket_service,
            top_k=top_k,
            confidence_threshold=confidence_threshold,
            trim_max_tokens=trim_max_tokens,
            domain_fallback_margin=domain_fallback_margin,
        )
        # `langsmith_tracing=True` sin `langsmith_api_key` es tracing desactivado (spec de la tarea
        # 11), no un error — mismo criterio permisivo que `agent_confidence_threshold` sin calibrar.
        self._tracing_enabled = langsmith_tracing and bool(langsmith_api_key)
        self._langsmith_api_key = langsmith_api_key
        self._langsmith_project = langsmith_project

    async def _invoke_traced(
        self, compiled: Any, input_: Any, config: RunnableConfig
    ) -> tuple[HelpdeskState, str | None]:
        """`compiled.ainvoke(...)` bajo `tracing_v2_enabled` si el tracing está activo; devuelve
        `(result, langsmith_trace_url)`.

        Un fallo de LangSmith (red, cuota) nunca tumba el run: `LangChainTracer` tiene
        `raise_error=False` por defecto (verificado contra el paquete instalado, `langsmith==0.11.0`)
        — sus propios fallos de logging se tragan y solo se loguean, nunca rompen el chain. Solo
        `tracer.get_run_url()` puede lanzar (`ValueError`, tras reintentos) si LangSmith no responde;
        aquí se trata como "sin URL", no como fallo del run (Scenario 3)."""
        if not self._tracing_enabled:
            return await compiled.ainvoke(input_, config=config), None
        client = Client(api_key=self._langsmith_api_key)
        with tracing_v2_enabled(project_name=self._langsmith_project, client=client) as tracer:
            result = await compiled.ainvoke(input_, config=config)
        try:
            return result, tracer.get_run_url()
        except Exception:
            return result, None

    async def trigger(
        self, tenant_id: uuid.UUID, ticket_id: uuid.UUID, run_seq: int, thread_id: str
    ) -> AgentRun:
        """Resuelve `tenant.auto_approve`, crea el `AgentRun` (`status=queued`, CAS real vía el índice
        único parcial de `add()`) e invoca el grafo hasta `interrupt()` o `respond`.

        `tenant` se resuelve ANTES de `add()`: `agent_run.tenant_id` es FK a `tenant.id`, así que un
        `tenant_id` que no existe no se puede persistir en ningún `AgentRun` — el error controlado se
        devuelve como un `AgentRun` en memoria (`status=failed`, sin persistir), no como una fila real.

        :raises app.domain.errors.Conflict: si ya hay un `AgentRun` no-terminal para `ticket_id`
            (propagado tal cual desde `AgentRunRepository.add()` — no se traga aquí).
        """
        tenant = await self._tenants.get(tenant_id)
        if tenant is None:
            return AgentRun(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                ticket_id=ticket_id,
                langgraph_thread_id=thread_id,
                run_seq=run_seq,
                status=AgentRunStatus.failed,
                error=f"tenant {tenant_id} no existe",
                finished_at=self._clock.now(),
            )

        run = await self._agent_runs.add(
            AgentRun(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                ticket_id=ticket_id,
                langgraph_thread_id=thread_id,
                run_seq=run_seq,
                status=AgentRunStatus.queued,
            )
        )

        thread_messages = await self._messages_repo.list_by_ticket(
            ticket_id, page=1, page_size=100, visibilities=[MessageVisibility.public]
        )
        initial_state: HelpdeskState = {
            "messages": [HumanMessage(content=m.body) for m in thread_messages.items],
            "tenant_id": tenant_id,
            "ticket_id": ticket_id,
            "auto_approve": tenant.auto_approve,
            "classification": None,
            "retrieved": [],
            "grade": None,
            "confidence": None,
            "requires_approval": False,
            "draft_response": None,
            "human_note": None,
            "human_decision": None,
        }
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        compiled = self._graph.compile(checkpointer=await get_checkpointer())

        try:
            result, trace_url = await self._invoke_traced(compiled, initial_state, config)
        except PortError as exc:
            return await self._agent_runs.update_result(
                run.id, status=AgentRunStatus.failed, error=str(exc), finished_at=self._clock.now()
            )

        sources = build_citations(result["retrieved"])
        interrupted = "__interrupt__" in result
        # `escalated` se deriva de si el grafo interrumpió, NO de `result["requires_approval"]`: el
        # nodo `decide` muta ese campo del estado ANTES de llamar a `interrupt()`, pero `interrupt()`
        # lanza una excepción de control de flujo que corta el nodo antes de su `return` — LangGraph
        # solo aplica los cambios de un nodo cuando termina de ejecutarse, así que esa escritura NUNCA
        # llega al `result` de la invocación interrumpida (verificado con un script mínimo contra el
        # SDK instalado). `interrupt()` solo se llama cuando `requires_approval` es `True`
        # (`decide.py`), así que "hubo interrupt" y "requires_approval" son equivalentes por
        # construcción — sin ese equivalente, `escalated` quedaría `False` en TODO run escalado.
        escalated = interrupted

        if interrupted:
            await self._approvals.add(
                ApprovalTask(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    ticket_id=ticket_id,
                    agent_run_id=run.id,
                    status=ApprovalStatus.pending,
                    draft_body=result["draft_response"] or "",
                    human_note=result["human_note"],
                )
            )
            return await self._agent_runs.update_result(
                run.id,
                status=AgentRunStatus.running,
                confidence=result["confidence"],
                sources=sources,
                escalated=escalated,
                langsmith_trace_url=trace_url,
            )

        return await self._agent_runs.update_result(
            run.id,
            status=AgentRunStatus.succeeded,
            confidence=result["confidence"],
            sources=sources,
            escalated=escalated,
            finished_at=self._clock.now(),
            langsmith_trace_url=trace_url,
        )

    async def resume(self, agent_run_id: uuid.UUID, outcome: ApprovalOutcome) -> None:
        """Reanuda el run interrumpido asociado a `agent_run_id` con la decisión humana `outcome`.

        Resuelve `thread_id` desde `agent_run_id` (este adaptador, no `approval_service`, traduce
        entre ambos — ver `agent_runner.py`). Compila el MISMO grafo con el checkpointer real: el
        estado vive solo en Postgres, así que una instancia nueva del runner (proceso reiniciado)
        reanuda igual — no se re-ejecutan los nodos ya completados.

        **Defensa en profundidad** (no la garantía primaria — esa es el CAS de
        `approval_service.decide_if_pending`, fuera de alcance de este adaptador): reanudar un thread
        SIN interrupt pendiente (verificado contra el SDK instalado, no asumido) no lanza ni re-ejecuta
        nada — `ainvoke(Command(resume=...))` sobre un grafo ya terminado devuelve el estado final tal
        cual, así que llamar a `resume()` dos veces es, en la práctica, un no-op la segunda vez.

        :raises app.domain.errors.NotFound: si `agent_run_id` no existe.
        """
        run = await self._agent_runs.get(agent_run_id)
        if run is None:
            raise NotFound(f"agent_run {agent_run_id} no existe", code="agent_run.not_found")
        if run.status is not AgentRunStatus.running:
            # Ya terminal (succeeded/failed) — nada que reanudar. Defensa en profundidad adicional:
            # ni siquiera toca el checkpointer, así que no arriesga sobreescribir `escalated`/
            # `finished_at` de un run que ya cerró (la garantía primaria de no-doble-resume es el CAS
            # de `approval_service.decide_if_pending`, fuera de alcance de este adaptador).
            return

        config: RunnableConfig = {"configurable": {"thread_id": run.langgraph_thread_id}}
        compiled = self._graph.compile(checkpointer=await get_checkpointer())

        try:
            result, resume_trace_url = await self._invoke_traced(
                compiled, to_resume_command(outcome), config
            )
        except PortError as exc:
            await self._agent_runs.update_result(
                run.id,
                status=AgentRunStatus.failed,
                error=str(exc),
                finished_at=self._clock.now(),
                langsmith_trace_url=run.langsmith_trace_url,
            )
            return

        # Preserva la URL de `trigger()` si ya existe (Scenario 4: "no se sobrescribe con una traza
        # desconectada") en vez de reemplazarla por la de este `ainvoke` — dos invocaciones separadas
        # de `ainvoke` producen dos runs raíz de LangSmith distintos (no hay enlace de trace_id entre
        # ellos verificado contra el SDK instalado), así que la URL de `trigger()` sigue siendo la más
        # completa (cubre TODO el trabajo hasta el interrupt); si `trigger()` no trazó nada (tracing
        # desactivado entonces, activado ahora), cae a la de este `resume()`.
        trace_url = run.langsmith_trace_url or resume_trace_url
        sources = build_citations(result["retrieved"])
        await self._agent_runs.update_result(
            run.id,
            status=AgentRunStatus.succeeded,
            confidence=result["confidence"],
            sources=sources,
            escalated=True,
            finished_at=self._clock.now(),
            langsmith_trace_url=trace_url,
        )
