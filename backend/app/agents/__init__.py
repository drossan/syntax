"""app.agents — grafo LangGraph del agente (RAG + HITL).

GUIÓN (→ tarea 15 definición y tarea 16 checkpointer/HITL — el núcleo de riesgo)
-------------------------------------------------------------------------------
Grafo **plano con edges condicionales tipados** (NO supervisor por prompt). Ver
`.claude/specs/backend/agent-graph.md` (tarea 05).

Definición (tarea 15):
  - Estado: ``add_messages`` + campos de dominio (dominio, prioridad, resoluble, confianza…).
  - Nodos: ``classify → retrieve → grade → generate`` (+ inyección de contexto RAG).
  - ``classify`` con ``with_structured_output`` ``{categoría, dominio 1-de-17, prioridad,
    resoluble}`` que **filtra el retrieval**; ``trim_messages`` para acotar el historial.

Checkpointer + HITL (tarea 16):
  - ``PostgresSaver`` con ``thread_id = ticket`` → persiste el estado del run.
  - Nodo/borde de ``interrupt`` → **endpoint de aprobación** → ``resume`` desde el checkpoint,
    contemplando reinicio a mitad de run y ediciones concurrentes.
  - Seam ``astream`` diseñado (Fase 1 entrega por request/polling, no token-a-token).

Dependencias: habla con el puerto LLM (``app.infra.llm``) y el retriever (``app.rag``) por
interfaz; se integra con el approval service de ``app.domain``.
"""
