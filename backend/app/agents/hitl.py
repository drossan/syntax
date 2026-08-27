"""app.agents.hitl — traduce `ApprovalOutcome` al payload de `Command(resume=...)` (ADR-0007).

`decide` (tarea 05) guarda en `state["human_decision"]` exactamente lo que `interrupt()` devuelve — que
es, verbatim, el valor de `Command(resume=...)`. `respond` (tarea 05) lee `decision.status`/
`.final_body`/`.human_note` por atributo, así que el payload de resume debe ser un `ApprovalOutcome`
real (no un dict) — este módulo solo envuelve, no transforma.
"""

from typing import Any

from langgraph.types import Command

from app.domain.ports.agent_runner import ApprovalOutcome


def to_resume_command(outcome: ApprovalOutcome) -> Command[Any]:
    """`Command(resume=outcome)` — el `outcome` viaja tal cual hasta `state["human_decision"]`."""
    return Command(resume=outcome)
