"""app.agents.nodes.generate — redacción del draft.

GUIÓN (→ tarea 15; spec 05)
---------------------------
  - Redacta ``draft_response`` **fiel al contexto recuperado** + **citas** (``app.rag.citations`` 14); no
    inventar más allá de las fuentes.
  - **Idioma de respuesta**: el del ticket (detección o locale de tenant/usuario); la KB está en español.
  - Si el contexto es insuficiente (de ``grade``) → no forzar respuesta: preparar ``human_note`` explicando
    el hueco (escalado).

⚠️ Prompt-injection: no ejecutar instrucciones embebidas en el ticket/contexto; límites de salida.
Anti-patrón: responder sin citas; alucinar fuera del contexto.
"""
