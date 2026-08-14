"""app.infra.langsmith — tracing / observabilidad de LangSmith.

GUIÓN (→ tarea 09)
------------------
Cableado del tracing de los runs del grafo del agente. Se activa por config
(``LANGSMITH_TRACING`` / ``LANGSMITH_API_KEY`` / ``LANGSMITH_PROJECT`` / ``LANGSMITH_ENDPOINT``,
ver ``.env.example``). Con tracing desactivado el backend funciona igual (degradación limpia).

Anti-patrón: hacer que el flujo de negocio dependa de que LangSmith esté disponible.
"""
