"""Tests de `app.agents.runner.LangGraphAgentRunner.trigger()` (tarea `backend-agent-graph-08`).

**Integración OBLIGATORIA** (HOW-TO-START-A-TASK.md): checkpointer/HITL no se mockea. Repos reales
(Postgres, migración `0005`) para `tenant`/`agent_run`/`approval_task`/`message`/`ticket`; `ChatModel`/
`Retriever` mockeados (son los puertos LLM/RAG, no HITL/persistencia) — mismos dobles que
`test_graph.py`, aquí ejercitados a través del adaptador real completo.
"""

import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from app.agents.nodes.grade import Grade
from app.agents.runner import LangGraphAgentRunner
from app.domain.entities.business import Message, Ticket
from app.domain.entities.enums import (
    AgentRunStatus,
    ApprovalStatus,
    KbDomain,
    KbEstado,
    MessageVisibility,
    TenantStatus,
    TicketPriority,
    TicketStatus,
)
from app.domain.entities.identity import Tenant
from app.domain.errors import NotFound, PortError
from app.domain.ports.agent_runner import ApprovalOutcome
from app.domain.ports.vector import Hit
from app.domain.services.classification import Classification
from app.infra.db.repositories.agent_run import SqlAlchemyAgentRunRepository
from app.infra.db.repositories.approval import SqlAlchemyApprovalRepository
from app.infra.db.repositories.message import SqlAlchemyMessageRepository
from app.infra.db.repositories.tenant import SqlAlchemyTenantRepository
from app.infra.db.repositories.ticket import SqlAlchemyTicketRepository
from app.rag.reranker import RankedHit
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

_TRUNCATE_TABLES = (
    "TRUNCATE approval_task, agent_run, message, ticket, tenant RESTART IDENTITY CASCADE"
)


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables(superuser_engine: AsyncEngine) -> AsyncIterator[None]:
    async with superuser_engine.begin() as conn:
        await conn.execute(text(_TRUNCATE_TABLES))
    yield
    async with superuser_engine.begin() as conn:
        await conn.execute(text(_TRUNCATE_TABLES))


@pytest_asyncio.fixture
async def session(superuser_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with async_sessionmaker(superuser_engine, expire_on_commit=False)() as s:
        yield s


@pytest_asyncio.fixture(autouse=True)
async def _checkpointer_pool(
    app_db_url: str, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[None]:
    """El pool singleton de `app.agents.checkpointer` apunta a `syntax_test` (rol `syntax_app`) —
    mismo patrón de reset que `test_checkpointer.py`, autouse aquí porque TODOS los tests de este
    fichero pasan por `LangGraphAgentRunner`, que compila el grafo con el checkpointer real."""
    from app.core.config import get_settings

    monkeypatch.setenv("DATABASE_URL", app_db_url)
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()

    import app.agents.checkpointer as checkpointer_module

    checkpointer_module._pool = None
    yield
    if checkpointer_module._pool is not None:
        await checkpointer_module._pool.close()
    checkpointer_module._pool = None
    get_settings.cache_clear()


class _FixedClock:
    def __init__(self, when: datetime) -> None:
        self._when = when

    def now(self) -> datetime:
        return self._when


class _FakeChatModel:
    def __init__(
        self, *, classification: Classification, grade: Grade | None = None, draft: str = "un draft"
    ) -> None:
        self._classification = classification
        self._grade = grade
        self._draft = draft
        self.classify_calls = 0
        self.grade_calls = 0
        self.generate_calls = 0

    async def classify(self, text: str, schema: type) -> Classification:
        self.classify_calls += 1
        return self._classification

    async def grade(self, prompt: str, schema: type) -> Grade:
        self.grade_calls += 1
        assert self._grade is not None
        return self._grade

    async def generate(self, prompt: str) -> str:
        self.generate_calls += 1
        return self._draft


class _FakeRetriever:
    def __init__(self, hits: list[RankedHit] | None = None) -> None:
        self._hits = hits if hits is not None else []
        self.calls = 0

    async def retrieve(self, query: str, *, top_k: int, domain=None, **kwargs) -> list[RankedHit]:
        self.calls += 1
        return self._hits


def _hit(uc_id: str = "CU-BE-05", score: float = 0.9) -> RankedHit:
    hit = Hit(
        uc_id=uc_id,
        chunk_id=uuid.uuid4(),
        section_type="comportamiento",
        title="Título",
        source_url=f"packages/x/docs/aiup/use-cases/{uc_id}.md",
        domain=KbDomain.media_and_dam,
        estado=KbEstado.draft,
        score=score,
        content="contenido",
    )
    return RankedHit(hit=hit, weighted_score=score)


async def _make_tenant(session: AsyncSession, *, auto_approve: bool) -> Tenant:
    tenant = await SqlAlchemyTenantRepository(session).add(
        Tenant(
            id=uuid.uuid4(),
            slug=f"t-{uuid.uuid4()}",
            name="T",
            status=TenantStatus.active,
            auto_approve=auto_approve,
        )
    )
    await session.commit()
    return tenant


async def _make_ticket_with_message(
    session: AsyncSession, tenant_id: uuid.UUID, body: str
) -> Ticket:
    ticket = await SqlAlchemyTicketRepository(session).add(
        Ticket(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            subject="s",
            status=TicketStatus.new,
            priority=TicketPriority.normal,
        )
    )
    await SqlAlchemyMessageRepository(session).add(
        Message(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            ticket_id=ticket.id,
            visibility=MessageVisibility.public,
            body=body,
        )
    )
    await session.commit()
    return ticket


class _SpyMessageRepository:
    """Envuelve el adaptador SQL real, capturando los argumentos de `list_by_ticket` — para verificar
    que `trigger()` pide la ventana de mensajes exacta que documenta (`page=1, page_size=100`), sin
    reimplementar el repo entero."""

    def __init__(self, real: SqlAlchemyMessageRepository) -> None:
        self._real = real
        self.list_by_ticket_calls: list[dict[str, object]] = []

    async def add(self, message: Message) -> Message:
        return await self._real.add(message)

    async def get(self, message_id):  # pragma: no cover - no usado
        return await self._real.get(message_id)

    async def list_by_ticket(self, ticket_id, *, page=1, page_size=20, visibilities=None):
        self.list_by_ticket_calls.append(
            {
                "ticket_id": ticket_id,
                "page": page,
                "page_size": page_size,
                "visibilities": visibilities,
            }
        )
        return await self._real.list_by_ticket(
            ticket_id, page=page, page_size=page_size, visibilities=visibilities
        )


def _make_runner(
    session: AsyncSession,
    *,
    chat_model,
    retriever,
    clock=None,
    confidence_threshold: float = 0.5,
    messages_repo=None,
    langsmith_tracing: bool = False,
    langsmith_api_key: str = "",
) -> LangGraphAgentRunner:
    return LangGraphAgentRunner(
        chat_model=chat_model,
        retriever=retriever,
        messages_repo=messages_repo or SqlAlchemyMessageRepository(session),
        tenants=SqlAlchemyTenantRepository(session),
        agent_runs=SqlAlchemyAgentRunRepository(session),
        approvals=SqlAlchemyApprovalRepository(session),
        clock=clock or _FixedClock(datetime(2026, 8, 27, tzinfo=UTC)),
        top_k=5,
        confidence_threshold=confidence_threshold,
        trim_max_tokens=50,
        langsmith_tracing=langsmith_tracing,
        langsmith_api_key=langsmith_api_key,
    )


async def test_auto_approve_run_with_sufficient_confidence_succeeds_without_an_approval_task(
    session: AsyncSession,
) -> None:
    """Given tenant auto_approve=true + contexto suficiente → AgentRun succeeded, mensaje público
    publicado, SIN ApprovalTask."""
    tenant = await _make_tenant(session, auto_approve=True)
    ticket = await _make_ticket_with_message(session, tenant.id, "¿cómo subo un vídeo?")
    classification = Classification(
        categoria="incidencia",
        dominio=KbDomain.media_and_dam,
        prioridad=TicketPriority.normal,
        resoluble=True,
    )
    grade = Grade(suficiente=True, motivo="basta")
    runner = _make_runner(
        session,
        chat_model=_FakeChatModel(classification=classification, grade=grade, draft="aquí tienes"),
        retriever=_FakeRetriever([_hit()]),
    )

    run = await runner.trigger(tenant.id, ticket.id, 1, f"ticket_{ticket.id}_run_1")

    assert run.status is AgentRunStatus.succeeded
    assert run.escalated is False
    assert run.confidence == 0.9
    approvals_repo = SqlAlchemyApprovalRepository(session)
    page = await approvals_repo.list(tenant.id, page=1, page_size=10)
    assert page.items == []
    messages_page = await SqlAlchemyMessageRepository(session).list_by_ticket(ticket.id)
    assert any(m.is_ai_draft for m in messages_page.items)


async def test_run_reaching_interrupt_creates_a_pending_approval_task(
    session: AsyncSession,
) -> None:
    """Given tenant auto_approve=false → AgentRun running (pendiente), y existe una
    ApprovalTask(status=pending) ligada a ese agent_run_id con el draft_body correcto."""
    tenant = await _make_tenant(session, auto_approve=False)
    ticket = await _make_ticket_with_message(session, tenant.id, "¿cómo subo un vídeo?")
    classification = Classification(
        categoria="incidencia",
        dominio=KbDomain.media_and_dam,
        prioridad=TicketPriority.normal,
        resoluble=True,
    )
    grade = Grade(suficiente=True, motivo="basta")
    runner = _make_runner(
        session,
        chat_model=_FakeChatModel(
            classification=classification, grade=grade, draft="borrador pendiente"
        ),
        retriever=_FakeRetriever([_hit()]),
    )

    run = await runner.trigger(tenant.id, ticket.id, 1, f"ticket_{ticket.id}_run_1")

    assert run.status is AgentRunStatus.running
    assert run.escalated is True
    page = await SqlAlchemyApprovalRepository(session).list(tenant.id, page=1, page_size=10)
    assert len(page.items) == 1
    task = page.items[0]
    assert task.status is ApprovalStatus.pending
    assert task.agent_run_id == run.id
    assert "borrador pendiente" in task.draft_body


async def test_tenant_not_resolving_fails_the_run_with_a_controlled_error(
    session: AsyncSession,
) -> None:
    ticket_owner_tenant = await _make_tenant(session, auto_approve=True)
    ticket = await _make_ticket_with_message(session, ticket_owner_tenant.id, "pregunta")
    missing_tenant_id = uuid.uuid4()
    runner = _make_runner(
        session,
        chat_model=_FakeChatModel(
            classification=Classification(
                categoria="x", dominio=None, prioridad=TicketPriority.low, resoluble=True
            )
        ),
        retriever=_FakeRetriever([]),
    )

    run = await runner.trigger(missing_tenant_id, ticket.id, 1, f"ticket_{ticket.id}_run_1")

    assert run.status is AgentRunStatus.failed
    assert run.error is not None
    assert str(missing_tenant_id) in run.error


async def test_llm_failure_mid_run_fails_the_agent_run_without_creating_an_approval_task(
    session: AsyncSession,
) -> None:
    """CU-BE-06 escenario 6: un fallo del LLM deja el `AgentRun` failed, sin `ApprovalTask` (no se
    llegó a interrupt), y la excepción NUNCA cruza cruda hasta el llamante."""
    tenant = await _make_tenant(session, auto_approve=True)
    ticket = await _make_ticket_with_message(session, tenant.id, "pregunta")

    class _BrokenChatModel:
        async def classify(self, text: str, schema: type) -> Classification:
            raise PortError("fallo simulado del proveedor LLM")

        async def grade(self, prompt: str, schema: type) -> Grade:  # pragma: no cover
            raise NotImplementedError

        async def generate(self, prompt: str) -> str:  # pragma: no cover
            raise NotImplementedError

    runner = _make_runner(session, chat_model=_BrokenChatModel(), retriever=_FakeRetriever([]))

    run = await runner.trigger(tenant.id, ticket.id, 1, f"ticket_{ticket.id}_run_1")

    assert run.status is AgentRunStatus.failed
    assert run.error is not None
    assert "fallo simulado" in run.error
    page = await SqlAlchemyApprovalRepository(session).list(tenant.id, page=1, page_size=10)
    assert page.items == []


async def test_update_result_end_to_end_persists_more_than_just_the_status(
    session: AsyncSession,
) -> None:
    """El `AgentRun` final trae `confidence`/`sources`/`escalated`/`finished_at`, no solo `status`."""
    tenant = await _make_tenant(session, auto_approve=True)
    ticket = await _make_ticket_with_message(session, tenant.id, "¿cómo subo un vídeo?")
    classification = Classification(
        categoria="incidencia",
        dominio=KbDomain.media_and_dam,
        prioridad=TicketPriority.normal,
        resoluble=True,
    )
    grade = Grade(suficiente=True, motivo="basta")
    fixed_time = datetime(2026, 8, 27, 12, 0, 0, tzinfo=UTC)
    runner = _make_runner(
        session,
        chat_model=_FakeChatModel(classification=classification, grade=grade, draft="draft"),
        retriever=_FakeRetriever([_hit()]),
        clock=_FixedClock(fixed_time),
    )

    run = await runner.trigger(tenant.id, ticket.id, 1, f"ticket_{ticket.id}_run_1")

    assert run.confidence == 0.9
    assert run.sources is not None and len(run.sources) >= 1
    assert run.escalated is False
    assert run.finished_at == fixed_time
    fetched = await SqlAlchemyAgentRunRepository(session).get(run.id)
    assert fetched is not None
    assert fetched.confidence == 0.9
    assert fetched.sources == run.sources


async def test_trigger_fetches_the_full_public_message_window(session: AsyncSession) -> None:
    """`trigger()` pide `page=1, page_size=100` de mensajes públicos — la ventana completa que cabe
    en una página del contrato (no una página parcial ni una ventana desalineada)."""
    tenant = await _make_tenant(session, auto_approve=True)
    ticket = await _make_ticket_with_message(session, tenant.id, "¿cómo subo un vídeo?")
    classification = Classification(
        categoria="incidencia",
        dominio=KbDomain.media_and_dam,
        prioridad=TicketPriority.normal,
        resoluble=True,
    )
    grade = Grade(suficiente=True, motivo="basta")
    spy = _SpyMessageRepository(SqlAlchemyMessageRepository(session))
    runner = _make_runner(
        session,
        chat_model=_FakeChatModel(classification=classification, grade=grade, draft="draft"),
        retriever=_FakeRetriever([_hit()]),
        messages_repo=spy,
    )

    await runner.trigger(tenant.id, ticket.id, 1, f"ticket_{ticket.id}_run_1")

    assert len(spy.list_by_ticket_calls) == 1
    call = spy.list_by_ticket_calls[0]
    assert call["page"] == 1
    assert call["page_size"] == 100
    assert call["visibilities"] == [MessageVisibility.public]


# ── resume() (tarea backend-agent-graph-09) ─────────────────────────────────────


class _FailingMessageRepository:
    """`add()` siempre falla — simula un fallo del LLM/infra al publicar, para forzar el camino
    `AgentRun → failed` de `resume()` sin depender de un fallo real del proveedor."""

    async def add(self, message: Message) -> Message:
        raise PortError("fallo simulado al publicar el mensaje")

    async def get(self, message_id):  # pragma: no cover - no usado
        raise NotImplementedError

    async def list_by_ticket(self, ticket_id, **kwargs):  # pragma: no cover - no usado
        raise NotImplementedError


async def _trigger_pending_run(
    session: AsyncSession, *, auto_approve: bool = False, draft: str = "borrador pendiente"
):
    tenant = await _make_tenant(session, auto_approve=auto_approve)
    ticket = await _make_ticket_with_message(session, tenant.id, "¿cómo subo un vídeo?")
    classification = Classification(
        categoria="incidencia",
        dominio=KbDomain.media_and_dam,
        prioridad=TicketPriority.normal,
        resoluble=True,
    )
    grade = Grade(suficiente=True, motivo="basta")
    chat_model = _FakeChatModel(classification=classification, grade=grade, draft=draft)
    retriever = _FakeRetriever([_hit()])
    runner = _make_runner(session, chat_model=chat_model, retriever=retriever)
    run = await runner.trigger(tenant.id, ticket.id, 1, f"ticket_{ticket.id}_run_1")
    return tenant, ticket, run


@pytest.mark.parametrize(
    ("decision", "expected_body_fragment"),
    [
        (
            ApprovalOutcome(status=ApprovalStatus.approved, final_body=None, human_note=None),
            "borrador",
        ),
        (
            ApprovalOutcome(
                status=ApprovalStatus.edited, final_body="texto corregido", human_note=None
            ),
            "texto corregido",
        ),
    ],
    ids=["approved_publishes_the_draft", "edited_publishes_the_final_body"],
)
async def test_resume_with_a_decision_publishes_the_expected_body(
    session: AsyncSession, decision: ApprovalOutcome, expected_body_fragment: str
) -> None:
    _tenant, ticket, run = await _trigger_pending_run(session)
    assert run.status is AgentRunStatus.running
    runner = _make_runner(
        session,
        chat_model=_FakeChatModel(
            classification=Classification(
                categoria="x", dominio=None, prioridad=TicketPriority.low, resoluble=True
            )
        ),
        retriever=_FakeRetriever([]),
    )

    await runner.resume(run.id, decision)

    updated = await SqlAlchemyAgentRunRepository(session).get(run.id)
    assert updated is not None
    assert updated.status is AgentRunStatus.succeeded
    assert updated.escalated is True  # el run pasó por HITL (interrupt) para llegar aquí
    messages = await SqlAlchemyMessageRepository(session).list_by_ticket(ticket.id)
    published = [m for m in messages.items if m.is_ai_draft]
    assert len(published) == 1
    assert expected_body_fragment in published[0].body


async def test_resume_with_a_rejection_publishes_nothing_and_keeps_the_run_terminal(
    session: AsyncSession,
) -> None:
    _tenant, ticket, run = await _trigger_pending_run(session)
    runner = _make_runner(
        session,
        chat_model=_FakeChatModel(
            classification=Classification(
                categoria="x", dominio=None, prioridad=TicketPriority.low, resoluble=True
            )
        ),
        retriever=_FakeRetriever([]),
    )
    decision = ApprovalOutcome(
        status=ApprovalStatus.rejected, final_body=None, human_note="no procede"
    )

    await runner.resume(run.id, decision)

    updated = await SqlAlchemyAgentRunRepository(session).get(run.id)
    assert updated is not None
    assert updated.status is AgentRunStatus.succeeded
    messages = await SqlAlchemyMessageRepository(session).list_by_ticket(ticket.id)
    assert [m for m in messages.items if m.is_ai_draft] == []


async def test_restart_mid_run_resumes_from_checkpoint_without_rerunning_completed_nodes(
    session: AsyncSession,
) -> None:
    """Reinicio a mitad de run: un runner/checkpointer NUEVO (simula un proceso reiniciado) reanuda
    desde el checkpoint SIN re-ejecutar classify/retrieve/grade/generate — el estado vive solo en
    Postgres, verificado con espías de llamadas al ChatModel/Retriever del runner descartado vs. el
    nuevo."""
    tenant, ticket, run = await _trigger_pending_run(session, draft="borrador del primer proceso")

    chat_model_2 = _FakeChatModel(
        classification=Classification(
            categoria="x", dominio=None, prioridad=TicketPriority.low, resoluble=True
        ),
        draft="NO DEBERÍA GENERARSE OTRA VEZ",
    )
    retriever_2 = _FakeRetriever([])
    runner_2 = _make_runner(session, chat_model=chat_model_2, retriever=retriever_2)
    decision = ApprovalOutcome(status=ApprovalStatus.approved, final_body=None, human_note=None)

    await runner_2.resume(run.id, decision)

    assert chat_model_2.classify_calls == 0
    assert chat_model_2.grade_calls == 0
    assert chat_model_2.generate_calls == 0
    assert retriever_2.calls == 0
    messages = await SqlAlchemyMessageRepository(session).list_by_ticket(ticket.id)
    published = [m for m in messages.items if m.is_ai_draft]
    assert len(published) == 1
    assert "borrador del primer proceso" in published[0].body


async def test_llm_failure_during_resume_fails_the_run_without_a_raw_exception(
    session: AsyncSession,
) -> None:
    _tenant, _ticket, run = await _trigger_pending_run(session)
    failing_runner = _make_runner(
        session,
        chat_model=_FakeChatModel(
            classification=Classification(
                categoria="x", dominio=None, prioridad=TicketPriority.low, resoluble=True
            )
        ),
        retriever=_FakeRetriever([]),
        messages_repo=_FailingMessageRepository(),
    )
    decision = ApprovalOutcome(status=ApprovalStatus.approved, final_body=None, human_note=None)

    await failing_runner.resume(run.id, decision)

    updated = await SqlAlchemyAgentRunRepository(session).get(run.id)
    assert updated is not None
    assert updated.status is AgentRunStatus.failed
    assert updated.error is not None
    assert "fallo simulado" in updated.error


async def test_resume_with_a_missing_agent_run_id_fails_controlled(session: AsyncSession) -> None:
    runner = _make_runner(
        session,
        chat_model=_FakeChatModel(
            classification=Classification(
                categoria="x", dominio=None, prioridad=TicketPriority.low, resoluble=True
            )
        ),
        retriever=_FakeRetriever([]),
    )
    decision = ApprovalOutcome(status=ApprovalStatus.approved, final_body=None, human_note=None)

    with pytest.raises(NotFound):
        await runner.resume(uuid.uuid4(), decision)


async def test_resume_on_a_thread_without_a_pending_interrupt_is_a_defensive_no_op(
    session: AsyncSession,
) -> None:
    """Defensa en profundidad (la garantía real de no-doble-reanudación la da el CAS de
    `approval_service`, fuera de alcance aquí): reanudar un run ya terminado (auto-aprobado, nunca
    interrumpió) no revienta y no publica un segundo mensaje — verificado el comportamiento real de
    LangGraph, no asumido."""
    _tenant, ticket, run = await _trigger_pending_run(session, auto_approve=True)
    assert run.status is AgentRunStatus.succeeded
    messages_before = await SqlAlchemyMessageRepository(session).list_by_ticket(ticket.id)
    published_before = [m for m in messages_before.items if m.is_ai_draft]
    assert len(published_before) == 1

    runner = _make_runner(
        session,
        chat_model=_FakeChatModel(
            classification=Classification(
                categoria="x", dominio=None, prioridad=TicketPriority.low, resoluble=True
            )
        ),
        retriever=_FakeRetriever([]),
    )
    decision = ApprovalOutcome(status=ApprovalStatus.approved, final_body=None, human_note=None)

    await runner.resume(run.id, decision)  # no debe lanzar

    messages_after = await SqlAlchemyMessageRepository(session).list_by_ticket(ticket.id)
    published_after = [m for m in messages_after.items if m.is_ai_draft]
    assert len(published_after) == 1
    run_after = await SqlAlchemyAgentRunRepository(session).get(run.id)
    assert run_after is not None
    assert run_after.escalated is False  # no se pisa: nunca fue un run escalado
    assert run_after.finished_at == run.finished_at  # no se toca un run ya terminal


async def test_resuming_a_superseded_run_does_not_affect_the_active_run_of_the_same_ticket(
    session: AsyncSession,
) -> None:
    """Re-draft tras reopen: un `AgentRun` superado (`run_seq=n`) no interfiere con el run activo
    (`run_seq=n+1`, `thread_id` nuevo) — una decisión tardía sobre el thread superado no reanuda ni
    afecta al run activo."""
    tenant = await _make_tenant(session, auto_approve=False)
    ticket = await _make_ticket_with_message(session, tenant.id, "pregunta")
    classification = Classification(
        categoria="incidencia",
        dominio=KbDomain.media_and_dam,
        prioridad=TicketPriority.normal,
        resoluble=True,
    )
    grade = Grade(suficiente=True, motivo="basta")

    runner_1 = _make_runner(
        session,
        chat_model=_FakeChatModel(
            classification=classification, grade=grade, draft="draft del run 1"
        ),
        retriever=_FakeRetriever([_hit()]),
    )
    run_1 = await runner_1.trigger(tenant.id, ticket.id, 1, f"ticket_{ticket.id}_run_1")
    assert run_1.status is AgentRunStatus.running
    await SqlAlchemyAgentRunRepository(session).update_result(
        run_1.id, status=AgentRunStatus.failed, error="superado por reapertura del ticket"
    )

    runner_2 = _make_runner(
        session,
        chat_model=_FakeChatModel(
            classification=classification, grade=grade, draft="draft del run 2"
        ),
        retriever=_FakeRetriever([_hit()]),
    )
    run_2 = await runner_2.trigger(tenant.id, ticket.id, 2, f"ticket_{ticket.id}_run_2")
    assert run_2.status is AgentRunStatus.running

    late_decision_runner = _make_runner(
        session,
        chat_model=_FakeChatModel(
            classification=Classification(
                categoria="x", dominio=None, prioridad=TicketPriority.low, resoluble=True
            )
        ),
        retriever=_FakeRetriever([]),
    )
    decision = ApprovalOutcome(status=ApprovalStatus.rejected, final_body=None, human_note="tardía")

    await late_decision_runner.resume(run_1.id, decision)

    run_2_after = await SqlAlchemyAgentRunRepository(session).get(run_2.id)
    assert run_2_after is not None
    assert run_2_after.status is AgentRunStatus.running
    approvals = await SqlAlchemyApprovalRepository(session).list(tenant.id, page=1, page_size=10)
    run_2_task = next(t for t in approvals.items if t.agent_run_id == run_2.id)
    assert run_2_task.status is ApprovalStatus.pending


# ── LangSmith tracing mínimo (tarea backend-agent-graph-11) ─────────────────────


class _FakeTracer:
    def __init__(self, *, url: str | None, raise_on_get_url: bool) -> None:
        self._url = url
        self._raise_on_get_url = raise_on_get_url

    def get_run_url(self) -> str:
        if self._raise_on_get_url:
            raise ValueError("LangSmith no responde")
        assert self._url is not None
        return self._url


def _stub_tracing_v2_enabled(
    *, url: str | None, raise_on_get_url: bool = False
) -> Callable[..., AbstractContextManager[_FakeTracer]]:
    """Sustituye `app.agents.runner.tracing_v2_enabled` — evita cualquier llamada de red real a
    LangSmith en tests; ejercita SOLO nuestra lógica (`_invoke_traced`), igual que `_FakeChatModel`/
    `_FakeRetriever` sustituyen los puertos LLM/RAG."""

    @contextmanager
    def _fake_tracing_v2_enabled(*, project_name: str, client: object) -> Iterator[_FakeTracer]:
        yield _FakeTracer(url=url, raise_on_get_url=raise_on_get_url)

    return _fake_tracing_v2_enabled


async def test_tracing_enabled_populates_the_trace_url_on_trigger(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: con tracing activo, el run queda trazado."""
    monkeypatch.setattr(
        "app.agents.runner.tracing_v2_enabled",
        _stub_tracing_v2_enabled(url="https://smith.langchain.com/o/x/projects/p/y/r/z"),
    )
    tenant = await _make_tenant(session, auto_approve=True)
    ticket = await _make_ticket_with_message(session, tenant.id, "¿cómo subo un vídeo?")
    classification = Classification(
        categoria="incidencia",
        dominio=KbDomain.media_and_dam,
        prioridad=TicketPriority.normal,
        resoluble=True,
    )
    grade = Grade(suficiente=True, motivo="basta")
    runner = _make_runner(
        session,
        chat_model=_FakeChatModel(classification=classification, grade=grade),
        retriever=_FakeRetriever([_hit()]),
        langsmith_tracing=True,
        langsmith_api_key="fake-key",
    )

    run = await runner.trigger(tenant.id, ticket.id, 1, f"ticket_{ticket.id}_run_1")

    assert run.langsmith_trace_url == "https://smith.langchain.com/o/x/projects/p/y/r/z"


async def test_tracing_disabled_by_default_leaves_the_trace_url_empty(
    session: AsyncSession,
) -> None:
    """Scenario: sin tracing, el campo queda vacío sin romper el run."""
    tenant = await _make_tenant(session, auto_approve=True)
    ticket = await _make_ticket_with_message(session, tenant.id, "¿cómo subo un vídeo?")
    classification = Classification(
        categoria="incidencia",
        dominio=KbDomain.media_and_dam,
        prioridad=TicketPriority.normal,
        resoluble=True,
    )
    grade = Grade(suficiente=True, motivo="basta")
    runner = _make_runner(
        session,
        chat_model=_FakeChatModel(classification=classification, grade=grade),
        retriever=_FakeRetriever([_hit()]),
    )

    run = await runner.trigger(tenant.id, ticket.id, 1, f"ticket_{ticket.id}_run_1")

    assert run.status is AgentRunStatus.succeeded
    assert run.langsmith_trace_url is None


async def test_tracing_enabled_without_an_api_key_stays_disabled(session: AsyncSession) -> None:
    """`langsmith_tracing=True` sin `langsmith_api_key` es tracing desactivado (spec de la tarea)."""
    tenant = await _make_tenant(session, auto_approve=True)
    ticket = await _make_ticket_with_message(session, tenant.id, "¿cómo subo un vídeo?")
    classification = Classification(
        categoria="incidencia",
        dominio=KbDomain.media_and_dam,
        prioridad=TicketPriority.normal,
        resoluble=True,
    )
    grade = Grade(suficiente=True, motivo="basta")
    runner = _make_runner(
        session,
        chat_model=_FakeChatModel(classification=classification, grade=grade),
        retriever=_FakeRetriever([_hit()]),
        langsmith_tracing=True,
        langsmith_api_key="",
    )

    run = await runner.trigger(tenant.id, ticket.id, 1, f"ticket_{ticket.id}_run_1")

    assert run.langsmith_trace_url is None


async def test_a_langsmith_client_failure_does_not_fail_the_run(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: fallo del cliente LangSmith no tumba el run — best-effort, `langsmith_trace_url`
    queda `None` pero el run completa con normalidad."""
    monkeypatch.setattr(
        "app.agents.runner.tracing_v2_enabled",
        _stub_tracing_v2_enabled(url=None, raise_on_get_url=True),
    )
    tenant = await _make_tenant(session, auto_approve=True)
    ticket = await _make_ticket_with_message(session, tenant.id, "¿cómo subo un vídeo?")
    classification = Classification(
        categoria="incidencia",
        dominio=KbDomain.media_and_dam,
        prioridad=TicketPriority.normal,
        resoluble=True,
    )
    grade = Grade(suficiente=True, motivo="basta")
    runner = _make_runner(
        session,
        chat_model=_FakeChatModel(classification=classification, grade=grade, draft="aquí tienes"),
        retriever=_FakeRetriever([_hit()]),
        langsmith_tracing=True,
        langsmith_api_key="fake-key",
    )

    run = await runner.trigger(tenant.id, ticket.id, 1, f"ticket_{ticket.id}_run_1")

    assert run.status is AgentRunStatus.succeeded
    assert run.langsmith_trace_url is None
    messages_page = await SqlAlchemyMessageRepository(session).list_by_ticket(ticket.id)
    assert any(m.is_ai_draft for m in messages_page.items)


async def test_resume_preserves_the_trigger_trace_url_instead_of_overwriting_it(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: la traza sobrevive al ciclo interrupt→resume — `resume()` NO sobrescribe la URL de
    `trigger()` con una traza desconectada de su propia invocación."""
    monkeypatch.setattr(
        "app.agents.runner.tracing_v2_enabled",
        _stub_tracing_v2_enabled(url="https://smith.langchain.com/o/x/projects/p/y/r/trigger"),
    )
    tenant = await _make_tenant(session, auto_approve=False)
    ticket = await _make_ticket_with_message(session, tenant.id, "¿cómo subo un vídeo?")
    classification = Classification(
        categoria="incidencia",
        dominio=KbDomain.media_and_dam,
        prioridad=TicketPriority.normal,
        resoluble=True,
    )
    grade = Grade(suficiente=True, motivo="basta")
    runner = _make_runner(
        session,
        chat_model=_FakeChatModel(
            classification=classification, grade=grade, draft="borrador pendiente"
        ),
        retriever=_FakeRetriever([_hit()]),
        langsmith_tracing=True,
        langsmith_api_key="fake-key",
    )
    run = await runner.trigger(tenant.id, ticket.id, 1, f"ticket_{ticket.id}_run_1")
    assert run.status is AgentRunStatus.running
    assert run.langsmith_trace_url == "https://smith.langchain.com/o/x/projects/p/y/r/trigger"

    monkeypatch.setattr(
        "app.agents.runner.tracing_v2_enabled",
        _stub_tracing_v2_enabled(url="https://smith.langchain.com/o/x/projects/p/y/r/resume"),
    )
    resume_runner = _make_runner(
        session,
        chat_model=_FakeChatModel(
            classification=Classification(
                categoria="x", dominio=None, prioridad=TicketPriority.low, resoluble=True
            )
        ),
        retriever=_FakeRetriever([]),
        langsmith_tracing=True,
        langsmith_api_key="fake-key",
    )
    decision = ApprovalOutcome(status=ApprovalStatus.approved, final_body=None, human_note=None)

    await resume_runner.resume(run.id, decision)

    updated = await SqlAlchemyAgentRunRepository(session).get(run.id)
    assert updated is not None
    assert updated.status is AgentRunStatus.succeeded
    assert updated.langsmith_trace_url == "https://smith.langchain.com/o/x/projects/p/y/r/trigger"


async def test_resume_uses_its_own_trace_url_when_trigger_had_none(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Si `trigger()` no trazó nada (tracing desactivado entonces), `resume()` puebla el campo con
    la URL de su propia traza en vez de dejarlo vacío para siempre."""
    tenant = await _make_tenant(session, auto_approve=False)
    ticket = await _make_ticket_with_message(session, tenant.id, "¿cómo subo un vídeo?")
    classification = Classification(
        categoria="incidencia",
        dominio=KbDomain.media_and_dam,
        prioridad=TicketPriority.normal,
        resoluble=True,
    )
    grade = Grade(suficiente=True, motivo="basta")
    runner = _make_runner(
        session,
        chat_model=_FakeChatModel(
            classification=classification, grade=grade, draft="borrador pendiente"
        ),
        retriever=_FakeRetriever([_hit()]),
    )
    run = await runner.trigger(tenant.id, ticket.id, 1, f"ticket_{ticket.id}_run_1")
    assert run.langsmith_trace_url is None

    monkeypatch.setattr(
        "app.agents.runner.tracing_v2_enabled",
        _stub_tracing_v2_enabled(url="https://smith.langchain.com/o/x/projects/p/y/r/resume-only"),
    )
    resume_runner = _make_runner(
        session,
        chat_model=_FakeChatModel(
            classification=Classification(
                categoria="x", dominio=None, prioridad=TicketPriority.low, resoluble=True
            )
        ),
        retriever=_FakeRetriever([]),
        langsmith_tracing=True,
        langsmith_api_key="fake-key",
    )
    decision = ApprovalOutcome(status=ApprovalStatus.approved, final_body=None, human_note=None)

    await resume_runner.resume(run.id, decision)

    updated = await SqlAlchemyAgentRunRepository(session).get(run.id)
    assert updated is not None
    assert (
        updated.langsmith_trace_url == "https://smith.langchain.com/o/x/projects/p/y/r/resume-only"
    )


async def test_tracing_defaults_to_disabled_when_the_runner_is_constructed_directly(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El default del constructor (`langsmith_tracing=False`), no solo el de `_make_runner`, deja el
    tracing apagado — construye `LangGraphAgentRunner` directamente, sin pasar `langsmith_tracing`,
    pero SÍ con `langsmith_api_key` (para no depender del `and` con un `api_key=""` que ya taparía
    por sí solo un default mutado a `True`). `tracing_v2_enabled` va stubbeado (determinista, sin red)
    para que, si el default fuera `True`, la URL SÍ aparecería — la aserción distingue de verdad."""
    monkeypatch.setattr(
        "app.agents.runner.tracing_v2_enabled",
        _stub_tracing_v2_enabled(
            url="https://smith.langchain.com/o/x/projects/p/y/r/should-not-appear"
        ),
    )
    tenant = await _make_tenant(session, auto_approve=True)
    ticket = await _make_ticket_with_message(session, tenant.id, "¿cómo subo un vídeo?")
    classification = Classification(
        categoria="incidencia",
        dominio=KbDomain.media_and_dam,
        prioridad=TicketPriority.normal,
        resoluble=True,
    )
    grade = Grade(suficiente=True, motivo="basta")
    runner = LangGraphAgentRunner(
        chat_model=_FakeChatModel(classification=classification, grade=grade),
        retriever=_FakeRetriever([_hit()]),  # type: ignore[arg-type]
        messages_repo=SqlAlchemyMessageRepository(session),
        tenants=SqlAlchemyTenantRepository(session),
        agent_runs=SqlAlchemyAgentRunRepository(session),
        approvals=SqlAlchemyApprovalRepository(session),
        clock=_FixedClock(datetime(2026, 8, 27, tzinfo=UTC)),
        top_k=5,
        confidence_threshold=0.5,
        trim_max_tokens=50,
        langsmith_api_key="a-real-looking-key",
    )

    run = await runner.trigger(tenant.id, ticket.id, 1, f"ticket_{ticket.id}_run_1")

    assert run.langsmith_trace_url is None


async def test_tracing_stays_disabled_with_an_api_key_but_the_tracing_flag_off(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`langsmith_api_key` configurada por sí sola NO activa el tracing — hace falta
    `langsmith_tracing=True` también (`and`, no `or`: spec de la tarea). `tracing_v2_enabled` va
    stubbeado (determinista) para que un `or` accidental sí produjera una URL observable."""
    monkeypatch.setattr(
        "app.agents.runner.tracing_v2_enabled",
        _stub_tracing_v2_enabled(
            url="https://smith.langchain.com/o/x/projects/p/y/r/should-not-appear"
        ),
    )
    tenant = await _make_tenant(session, auto_approve=True)
    ticket = await _make_ticket_with_message(session, tenant.id, "¿cómo subo un vídeo?")
    classification = Classification(
        categoria="incidencia",
        dominio=KbDomain.media_and_dam,
        prioridad=TicketPriority.normal,
        resoluble=True,
    )
    grade = Grade(suficiente=True, motivo="basta")
    runner = _make_runner(
        session,
        chat_model=_FakeChatModel(classification=classification, grade=grade),
        retriever=_FakeRetriever([_hit()]),
        langsmith_tracing=False,
        langsmith_api_key="a-real-looking-key",
    )

    run = await runner.trigger(tenant.id, ticket.id, 1, f"ticket_{ticket.id}_run_1")

    assert run.langsmith_trace_url is None
