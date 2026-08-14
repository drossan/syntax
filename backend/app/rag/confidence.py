"""app.rag.confidence — confianza híbrida (similitud + grade).

GUIÓN (→ tarea 14; spec 04/05)
------------------------------
Qué implementar:
  - Combina **(a)** la **similitud** de los chunks recuperados (score coseno normalizado + re-ranking de
    ``estado``, este módulo/retriever) con **(b)** el **``grade``** del LLM (relevancia/suficiencia, nodo
    del grafo 05).
  - Expone la señal y el **umbral** (``AGENT_CONFIDENCE_THRESHOLD``, config); el grafo (05/`decide`) usa el
    resultado para **auto vs escalado**; contexto insuficiente (0/1 hits o grade bajo) → ruta a
    ``human_note`` (no inventar respuesta).
  - Este módulo fija (a) y la forma de combinación; el ``grade`` (b) lo produce el nodo del grafo (15).

Anti-patrón: confianza basada solo en similitud sin grade; umbral hardcodeado.
"""
