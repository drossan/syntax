"""app.agents.nodes.grade — evaluación de relevancia/suficiencia.

GUIÓN (→ tarea 15; spec 05/04)
------------------------------
  - El LLM juzga si el contexto recuperado es **relevante** y **suficiente** para responder
    (``grade.suficiente``). Alimenta la **confianza híbrida** (``app.rag.confidence`` 14): similitud + grade.
  - Contexto insuficiente → ruta a escalado / ``human_note`` (no inventar respuesta).

Anti-patrón: confiar solo en la similitud sin grade; grade en prosa no estructurada.
"""
