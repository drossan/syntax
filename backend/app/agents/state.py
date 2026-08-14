"""app.agents.state — estado del grafo (HelpdeskState).

GUIÓN (→ tarea 15; spec 05)
---------------------------
Qué implementar:
  - ``HelpdeskState`` (TypedDict/Pydantic) con reducer ``add_messages`` en ``messages`` + campos de dominio:
    ``tenant_id``, ``ticket_id``, ``classification`` (``{categoria, dominio 1-de-17, prioridad, resoluble}``),
    ``retrieved`` (hits/citas del retriever 14), ``confidence`` (float), ``requires_approval`` (bool),
    ``draft_response`` (str), ``human_note`` (str|None).
  - Los campos mapean 1:1 a ``AgentRun``/``Ticket``/``ApprovalTask`` (03) al persistir (16).

⚠️ Nota de conformidad (05): ``add_messages`` es API de LangGraph objetivo; surface exacto a pinar al
implementar (deps sin compilar). Anti-patrón: guardar el histórico real en el estado (vive en 03; el
estado es de ejecución del run).
"""
