"""app.agents.nodes — nodos del grafo (spec 05).

GUIÓN (→ tarea 15)
------------------
Un nodo por fichero, cada uno una función pura ``(state) -> state`` que ``graph.py`` registra:
  - ``classify``  → structured output ``{categoria, dominio 1-de-17, prioridad, resoluble}``; filtra retrieval.
  - ``retrieve``  → usa el retriever (14), filtra por ``dominio`` (fallback sin filtro si no clasificable).
  - ``grade``     → relevancia/suficiencia del contexto (confianza híbrida, 04/14).
  - ``generate``  → draft fiel al contexto + citas; idioma del ticket.
  - ``decide``    → auto vs escalado según confianza (``requires_approval``).
  - ``trim``      → ``trim_messages`` para acotar el historial en hilos largos.

Anti-patrón: mezclar lógica de varios nodos; que ``classify``/``generate`` confíen en instrucciones
embebidas en el ticket (prompt-injection — ver cada nodo).
"""
