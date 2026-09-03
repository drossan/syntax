"""Tests unit del nodo `decide` (tarea `backend-agent-graph-05`) — puerta HITL, puro (sin puertos).

`interrupt()` real solo funciona dentro de un grafo compilado en ejecución (`RuntimeError: Called
get_config outside of a runnable context` si se llama a pelo) — el ciclo interrupt→checkpoint→resume real
es integración obligatoria (tareas 07/08/09). Aquí se mockea `langgraph.types.interrupt` a nivel de
módulo para testear la lógica de `requires_approval` y que el nodo LLAMA a `interrupt()` con el payload
correcto cuando escala, sin necesitar un grafo real.
"""

import uuid

import app.agents.nodes.decide as decide_module
from app.agents.nodes.decide import make_decide_node
from app.agents.nodes.grade import Grade
from app.domain.entities.enums import TicketPriority
from app.domain.services.classification import Classification
from langchain_core.messages import HumanMessage


def _state(
    *,
    auto_approve: bool,
    confidence: float | None,
    grade: Grade | None,
    draft_response: str | None = None,
    classification: Classification | None = None,
) -> dict:
    return {
        "messages": [HumanMessage(content="pregunta")],
        "tenant_id": uuid.uuid4(),
        "ticket_id": uuid.uuid4(),
        "auto_approve": auto_approve,
        "classification": classification,
        "retrieved": [],
        "grade": grade,
        "confidence": confidence,
        "requires_approval": False,
        "draft_response": draft_response,
        "human_note": None,
        "human_decision": None,
    }


def _patch_interrupt(monkeypatch, return_value: object = "resumed") -> dict:
    captured: dict[str, object] = {}

    def fake_interrupt(payload: object) -> object:
        captured["payload"] = payload
        return return_value

    monkeypatch.setattr(decide_module, "interrupt", fake_interrupt)
    return captured


async def test_auto_approve_false_always_requires_approval(monkeypatch) -> None:
    """auto_approve=false, confianza por encima del umbral → requires_approval=true igualmente."""
    _patch_interrupt(monkeypatch)
    grade = Grade(suficiente=True, motivo="ok")
    node = make_decide_node(confidence_threshold=0.5)

    result = await node(_state(auto_approve=False, confidence=0.9, grade=grade))

    assert result["requires_approval"] is True


async def test_low_confidence_requires_approval_even_with_auto_approve(monkeypatch) -> None:
    """auto_approve=true pero confianza por debajo del umbral → requires_approval=true."""
    _patch_interrupt(monkeypatch)
    grade = Grade(suficiente=True, motivo="ok")
    node = make_decide_node(confidence_threshold=0.5)

    result = await node(_state(auto_approve=True, confidence=0.3, grade=grade))

    assert result["requires_approval"] is True


async def test_sufficient_confidence_and_auto_approve_does_not_require_approval(
    monkeypatch,
) -> None:
    """auto_approve=true, grade.suficiente=true y confianza por encima del umbral → requires_approval=false."""
    captured = _patch_interrupt(monkeypatch)
    grade = Grade(suficiente=True, motivo="ok")
    node = make_decide_node(confidence_threshold=0.5)

    result = await node(_state(auto_approve=True, confidence=0.8, grade=grade))

    assert result["requires_approval"] is False
    assert "payload" not in captured  # interrupt() nunca se llama en la ruta auto


async def test_confidence_exactly_equal_to_threshold_counts_as_sufficient(monkeypatch) -> None:
    """Frontera: `confidence == confidence_threshold` exactamente → requires_approval=false (`<`, no `<=`)."""
    captured = _patch_interrupt(monkeypatch)
    grade = Grade(suficiente=True, motivo="ok")
    node = make_decide_node(confidence_threshold=0.6)

    result = await node(_state(auto_approve=True, confidence=0.6, grade=grade))

    assert result["requires_approval"] is False
    assert "payload" not in captured


async def test_none_grade_requires_approval(monkeypatch) -> None:
    """`grade is None` (nodo testeado aislado, no debería ocurrir por el routing normal) → escala,
    nunca un AttributeError por acceder a `grade.suficiente` sobre None."""
    _patch_interrupt(monkeypatch)
    node = make_decide_node(confidence_threshold=0.5)

    result = await node(_state(auto_approve=True, confidence=0.9, grade=None))

    assert result["requires_approval"] is True


async def test_missing_confidence_defaults_to_zero_above_threshold(monkeypatch) -> None:
    """`state["confidence"] is None` (nodo testeado aislado) usa `0.0` como valor por defecto — con un
    umbral positivo, `0.0 < threshold` es cierto → requires_approval=True."""
    _patch_interrupt(monkeypatch)
    grade = Grade(suficiente=True, motivo="ok")
    node = make_decide_node(confidence_threshold=0.5)

    result = await node(_state(auto_approve=True, confidence=None, grade=grade))

    assert result["requires_approval"] is True


async def test_missing_confidence_defaults_to_zero_below_threshold() -> None:
    """Mismo default `0.0`, pero con un umbral negativo `0.0 < threshold` es falso — distingue el
    default `0.0` de un valor negativo inventado."""
    grade = Grade(suficiente=True, motivo="ok")
    node = make_decide_node(confidence_threshold=-0.5)

    result = await node(_state(auto_approve=True, confidence=None, grade=grade))

    assert result["requires_approval"] is False


async def test_insufficient_grade_requires_approval_even_with_high_confidence(monkeypatch) -> None:
    _patch_interrupt(monkeypatch)
    grade = Grade(suficiente=False, motivo="falta contexto")
    node = make_decide_node(confidence_threshold=0.5)

    result = await node(_state(auto_approve=True, confidence=0.99, grade=grade))

    assert result["requires_approval"] is True


async def test_escalating_calls_interrupt_with_the_review_payload(monkeypatch) -> None:
    """Cuando escala, `interrupt()` se llama con el payload de revisión (draft/citas/motivo) y el valor
    de retorno (la decisión humana tras `Command(resume=)`) queda en `state["human_decision"]`."""
    captured = _patch_interrupt(monkeypatch, return_value="decisión-humana")
    grade = Grade(suficiente=False, motivo="falta la sección de precios")
    node = make_decide_node(confidence_threshold=0.5)

    result = await node(_state(auto_approve=True, confidence=0.1, grade=grade, draft_response=None))

    assert captured["payload"] is not None
    assert result["human_decision"] == "decisión-humana"


async def test_escalating_with_a_grade_persists_its_motivo_into_human_note(monkeypatch) -> None:
    """El motivo que ya viaja en el payload de revisión (`grade.motivo`) también queda en
    `state["human_note"]` -- es lo que termina en `ApprovalTask.human_note` (`runner.py`), no solo en
    el payload de `interrupt()` que ve el checkpointer."""
    _patch_interrupt(monkeypatch)
    grade = Grade(suficiente=False, motivo="falta la sección de precios")
    node = make_decide_node(confidence_threshold=0.5)

    result = await node(_state(auto_approve=True, confidence=0.1, grade=grade))

    assert result["human_note"] == "falta la sección de precios"


async def test_classification_not_resoluble_sets_a_human_note_explaining_the_skip(monkeypatch) -> None:
    """Camino `classification.resoluble=False` (CU-BE-05 extensión 1b): el grafo salta
    retrieve/grade/generate, así que ni `grade` ni `human_note` se han fijado nunca antes de llegar
    aquí. Sin este fix, `human_note` quedaba `None` -- el humano revisor no veía ningún motivo, solo
    "sin borrador"."""
    _patch_interrupt(monkeypatch)
    classification = Classification(
        categoria="consulta general",
        dominio=None,
        prioridad=TicketPriority.normal,
        resoluble=False,
    )
    node = make_decide_node(confidence_threshold=0.5)

    result = await node(
        _state(auto_approve=True, confidence=None, grade=None, classification=classification)
    )

    assert result["human_note"]
    assert result["human_note"] != "None"
