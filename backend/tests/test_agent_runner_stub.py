"""Tests de `app.infra.agent_runner.stub.StubAgentRunner` (tarea `backend-routers-flujo-ia-01`).

Nivel unit: `AgentRunRepository` fake en memoria — el CAS real contra el índice único parcial se
verifica en integración (`test_repositories_agent_run.py`), aquí solo el contrato de composición
(`trigger()` construye y persiste, `add()` es el único punto de escritura).
"""

import uuid

import pytest
from app.domain.entities.business import AgentRun
from app.domain.entities.enums import AgentRunStatus, ApprovalStatus
from app.domain.errors import Conflict
from app.domain.ports.agent_runner import ApprovalOutcome
from app.infra.agent_runner.stub import StubAgentRunner


class _FakeAgentRunRepository:
    def __init__(self, *, reject: bool = False) -> None:
        self.store: dict[uuid.UUID, AgentRun] = {}
        self._reject = reject
        self.added: list[AgentRun] = []

    async def add(self, run: AgentRun) -> AgentRun:
        if self._reject:
            raise Conflict(
                f"ya hay un run activo para el ticket {run.ticket_id}",
                code="agent_run.active_run_exists",
            )
        self.store[run.id] = run
        self.added.append(run)
        return run


async def test_trigger_persists_a_queued_agent_run_with_the_given_identifiers() -> None:
    agent_runs = _FakeAgentRunRepository()
    runner = StubAgentRunner(agent_runs)
    tenant_id = uuid.uuid4()
    ticket_id = uuid.uuid4()

    run = await runner.trigger(tenant_id, ticket_id, 1, "ticket_x_run_1")

    assert agent_runs.added == [run]
    assert run.tenant_id == tenant_id
    assert run.ticket_id == ticket_id
    assert run.run_seq == 1
    assert run.langgraph_thread_id == "ticket_x_run_1"
    assert run.status is AgentRunStatus.queued


async def test_trigger_leaves_confidence_and_sources_unset() -> None:
    """Sin grafo real, no hay ninguna señal de confianza/citas todavía."""
    runner = StubAgentRunner(_FakeAgentRunRepository())

    run = await runner.trigger(uuid.uuid4(), uuid.uuid4(), 1, "t")

    assert run.confidence is None
    assert run.sources is None
    assert run.error is None
    assert run.escalated is False


async def test_trigger_generates_a_fresh_id_each_call() -> None:
    agent_runs = _FakeAgentRunRepository()
    runner = StubAgentRunner(agent_runs)
    ticket_id = uuid.uuid4()

    first = await runner.trigger(uuid.uuid4(), ticket_id, 1, "t1")
    second = await runner.trigger(uuid.uuid4(), ticket_id, 2, "t2")

    assert first.id != second.id


async def test_trigger_propagates_conflict_from_the_repository_unions_as_is() -> None:
    """El CAS real vive en `AgentRunRepository.add()` (índice único parcial) — `trigger()` no lo
    atrapa ni lo reinterpreta, se propaga tal cual (garantía atómica bajo concurrencia)."""
    runner = StubAgentRunner(_FakeAgentRunRepository(reject=True))

    with pytest.raises(Conflict):
        await runner.trigger(uuid.uuid4(), uuid.uuid4(), 1, "t1")


async def test_resume_is_a_noop_without_a_real_graph() -> None:
    """Sin grafo real (15/16), resume() no hace nada — no lanza, no muta estado."""
    runner = StubAgentRunner(_FakeAgentRunRepository())
    outcome = ApprovalOutcome(status=ApprovalStatus.approved, final_body=None, human_note=None)

    assert await runner.resume(uuid.uuid4(), outcome) is None
