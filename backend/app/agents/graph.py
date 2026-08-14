"""app.agents.graph — construcción del StateGraph (plano, edges tipados).

GUIÓN (→ tarea 15; spec 05)
---------------------------
Qué implementar:
  - ``build_graph()`` → ``StateGraph(HelpdeskState)`` **plano con edges condicionales TIPADOS** (NO
    supervisor por prompt): ``classify → retrieve → grade → generate → decide → [auto | HITL] → respond``.
  - El routing lee **campos tipados** del estado (``classification.resoluble``, ``grade.suficiente``,
    ``decide.requires_approval``), nunca texto libre del LLM.
  - Registra los nodos de ``app.agents.nodes`` + ``trim`` (``trim_messages``) antes de invocar el LLM.
  - **NO compila con checkpointer todavía** (eso es 16); expone el grafo sin persistencia.

⚠️ Conformidad (05): `StateGraph`/edges condicionales = API objetivo de LangGraph; pinar al implementar.
Anti-patrón: routing por prompt; nodo supervisor que decide en prosa.
"""
