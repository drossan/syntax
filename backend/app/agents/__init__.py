"""app.agents — grafo LangGraph del agente (RAG + HITL).

Grafo **plano con edges condicionales tipados** (NO supervisor por prompt, ADR-0008). Ver
`.claude/specs/backend/agent-graph.md`.

- **Estado** (`state.py`): `HelpdeskState` (TypedDict) — `messages` (`add_messages`) + campos de
  dominio (`classification`, `retrieved`, `grade`, `confidence`, `requires_approval`,
  `draft_response`, `human_note`, `human_decision`, `auto_approve`).
- **Nodos** (`nodes/`, factory-closure `make_<nombre>_node(puerto...)`): `trim → classify → retrieve →
  grade → generate → decide → respond`. `classify` con structured output `{categoría, dominio
  1-de-17, prioridad, resoluble}` filtra `retrieve`; único edge condicional tipado del grafo:
  `classification.resoluble=False` salta `retrieve`/`grade`/`generate` directo a `decide` (CU-BE-05
  extensión 1b) — `decide` ya escala siempre que `grade is None`.
- **Grafo** (`graph.py::build_graph()`): ensambla los 7 nodos en un `StateGraph[HelpdeskState]` SIN
  compilar — lo compila `runner.py` (checkpointer real, GUIÓN aún: tareas 07/08).

Checkpointer + HITL (GUIÓN → tareas 07/08/09, núcleo de riesgo):
  - `PostgresSaver` con `thread_id = ticket_{id}_run_{n}` → persiste el estado del run.
  - `decide` llama a `interrupt()` inline cuando escala; `runner.py::resume` reanuda con
    `Command(resume=ApprovalOutcome)`, contemplando reinicio a mitad de run.
  - Seam `astream` diseñado (Fase 1 entrega por request/polling, no token-a-token).

Dependencias: habla con el puerto LLM (`app.infra.llm`), el retriever (`app.rag`) y
`MessageRepository` (`app.domain.ports.repositories`) por interfaz — el dominio no importa infra.
"""
