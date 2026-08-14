"""app.agents.nodes.trim — recorte de la ventana de contexto.

GUIÓN (→ tarea 15; spec 05)
---------------------------
  - Aplica ``trim_messages`` para acotar el historial (hilos largos por reaperturas) antes de invocar el
    LLM; no altera la persistencia del histórico real (``Message`` vive en 03, no en el estado).

⚠️ Conformidad (05): ``trim_messages`` = API objetivo de LangChain; pinar al implementar.
Anti-patrón: enviar todo el historial sin recortar (coste/límite de contexto).
"""
