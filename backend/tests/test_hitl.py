"""Tests unit de `app.agents.hitl` (tarea `backend-agent-graph-09`) — sin infra, función pura."""

from app.agents.hitl import to_resume_command
from app.domain.entities.enums import ApprovalStatus
from app.domain.ports.agent_runner import ApprovalOutcome
from langgraph.types import Command


def test_to_resume_command_wraps_the_outcome_verbatim() -> None:
    """`decide` (tarea 05) guarda en `state["human_decision"]` exactamente lo que devuelve
    `interrupt()` — que es el valor de `resume=`, así que el `Command` debe envolver el `ApprovalOutcome`
    tal cual, sin transformarlo (`respond`, tarea 05, lee `decision.status`/`.final_body`/`.human_note`
    por atributo)."""
    outcome = ApprovalOutcome(status=ApprovalStatus.approved, final_body=None, human_note=None)

    command = to_resume_command(outcome)

    assert isinstance(command, Command)
    assert command.resume is outcome


def test_to_resume_command_preserves_edited_and_rejected_outcomes() -> None:
    edited = ApprovalOutcome(
        status=ApprovalStatus.edited, final_body="texto corregido", human_note=None
    )
    rejected = ApprovalOutcome(
        status=ApprovalStatus.rejected, final_body=None, human_note="no procede"
    )

    assert to_resume_command(edited).resume is edited
    assert to_resume_command(rejected).resume is rejected
