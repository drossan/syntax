"""Test de regresión de superficie LangGraph/LangChain (tarea backend-agent-graph-01).

Blinda el surface verificado por introspección real en la sesión de planificación del plan
`agent-graph`: si un futuro `pip-compile` cambia estas firmas, este test rompe aquí — antes de que
el resto del plan (grafo, checkpointer, HITL) construya sobre un supuesto obsoleto.
"""

import inspect

from langchain_openai import ChatOpenAI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import StateGraph
from langgraph.types import Command, interrupt


def test_psycopg_binary_wrapper_is_importable() -> None:
    """`psycopg[binary]` instalado: importar el checkpointer de Postgres no lanza `ImportError` por
    falta de wrapper `pq` (síntoma verificado: `psycopg` sin extras rompe con "no pq wrapper
    available")."""
    assert AsyncPostgresSaver is not None


def test_interrupt_is_dynamic_not_a_static_interrupt_before() -> None:
    """`interrupt(value)` es una llamada de función dinámica dentro de un nodo — la spec asume esta
    forma, no `interrupt_before` estático en `compile()`."""
    signature = inspect.signature(interrupt)
    assert list(signature.parameters) == ["value"]


def test_command_supports_resume_kwarg() -> None:
    """`Command(resume=...)` es el mecanismo de reanudación que usa `runner.py::resume` (tarea 09)."""
    signature = inspect.signature(Command)
    assert "resume" in signature.parameters
    assert signature.parameters["resume"].kind == inspect.Parameter.KEYWORD_ONLY


def test_stategraph_compile_accepts_a_checkpointer() -> None:
    """`StateGraph.compile(checkpointer=...)` es lo que da durabilidad al `interrupt()` de un nodo
    (tarea 07/08) — el nodo en sí no necesita saber que existe un checkpointer."""
    signature = inspect.signature(StateGraph.compile)
    assert "checkpointer" in signature.parameters


def test_with_structured_output_defaults_to_json_schema_method() -> None:
    """`ChatOpenAI.with_structured_output(schema, method='json_schema')` es el método asumido por
    `app/infra/llm/structured.py` (tarea 04) para `classify`/`grade`/`generate`."""
    signature = inspect.signature(ChatOpenAI.with_structured_output)
    assert signature.parameters["method"].default == "json_schema"
