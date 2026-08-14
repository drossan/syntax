"""app.infra.langsmith.tracing — activación de tracing y captura de trace_url.

GUIÓN (→ tarea 09)
------------------
Cablea el tracing de LangSmith de los runs del grafo (observabilidad que ninguna demo tenía).

Qué implementar:
  - ``configure_tracing(settings)``: activa el tracing según config — exporta el entorno que LangSmith/
    LangChain esperan (p.ej. ``LANGCHAIN_TRACING_V2=true``/``LANGSMITH_TRACING``, ``LANGSMITH_API_KEY``,
    ``LANGSMITH_PROJECT``, ``LANGSMITH_ENDPOINT`` de ``.env.example``). Sin efectos en import; se llama
    desde el factory (07). Con tracing OFF el backend funciona igual (**degradación limpia**).
  - **``langsmith_trace_url``** (03 ``AgentRun``): tras ejecutar un run, obtener la URL de su traza (del
    run/callback de LangSmith) y persistirla en ``agent_run.langsmith_trace_url`` para saltar de un log/
    ticket a su traza. ``tags``/``metadata`` por run: ``tenant_id``, ``ticket_id``, ``run_seq``.

⚠️ Nota de conformidad: los nombres exactos de env/API de LangSmith se **pinan/verifican al implementar**
(deps sin compilar). El negocio **no** depende de que LangSmith esté disponible (anti-patrón).
"""
