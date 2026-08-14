"""app.agents.checkpointer — checkpointer Postgres del grafo.

GUIÓN (→ tarea 16; spec 05 — núcleo de riesgo)
----------------------------------------------
Qué implementar:
  - ``PostgresSaver`` (``langgraph-checkpoint-postgres``) como checkpointer del grafo: persiste el estado
    de cada run para poder **reanudar tras interrupción/reinicio**.
  - **``thread_id`` = ``agent_run.langgraph_thread_id`` = ``ticket_{id}_run_{n}``** (03 §4.2). Un run por
    (ticket, ``run_seq``); reabrir un ticket → run nuevo con ``n+1`` (no reutilizar checkpoint obsoleto, A1.2).
  - **Comparte el pool/engine async de 08** (mismo Postgres del negocio); tablas de checkpoint que crea
    LangGraph conviven con el schema (migración/inicialización documentada).

⚠️ Conformidad (05): ``PostgresSaver`` = API objetivo; nombre/firma exactos a pinar/verificar al
implementar (deps sin compilar). Anti-patrón: ``SqliteSaver``/``MemorySaver`` (no durables); un engine
propio desconectado del pool de 08.
"""
