"""Tests unit del nodo `trim` (tarea `backend-agent-graph-05`) — recorte del hilo antes del LLM."""

import uuid

from app.agents.nodes.trim import make_trim_node
from langchain_core.messages import AIMessage, HumanMessage


def _state(messages: list) -> dict:
    return {
        "messages": messages,
        "tenant_id": uuid.uuid4(),
        "ticket_id": uuid.uuid4(),
        "auto_approve": False,
        "classification": None,
        "retrieved": [],
        "grade": None,
        "confidence": None,
        "requires_approval": False,
        "draft_response": None,
        "human_note": None,
        "human_decision": None,
    }


async def test_a_long_thread_is_trimmed_keeping_the_most_recent_messages() -> None:
    messages = [
        HumanMessage(content="m1"),
        AIMessage(content="m2"),
        HumanMessage(content="m3"),
        AIMessage(content="m4"),
        HumanMessage(content="m5"),
    ]
    node = make_trim_node(max_tokens=2)

    result = await node(_state(messages))

    assert len(result["messages"]) == 2
    assert [m.content for m in result["messages"]] == ["m4", "m5"]


async def test_an_empty_thread_does_not_fail() -> None:
    node = make_trim_node(max_tokens=10)

    result = await node(_state([]))

    assert result["messages"] == []


async def test_a_single_message_thread_does_not_fail() -> None:
    messages = [HumanMessage(content="único mensaje")]
    node = make_trim_node(max_tokens=10)

    result = await node(_state(messages))

    assert len(result["messages"]) == 1


async def test_a_thread_within_the_limit_is_left_unchanged() -> None:
    messages = [HumanMessage(content="m1"), AIMessage(content="m2")]
    node = make_trim_node(max_tokens=10)

    result = await node(_state(messages))

    assert [m.content for m in result["messages"]] == ["m1", "m2"]
