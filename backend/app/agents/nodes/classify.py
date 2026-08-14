"""app.agents.nodes.classify — clasificación tipada del ticket.

GUIÓN (→ tarea 15; spec 05)
---------------------------
  - Usa ``with_structured_output`` (helper 09) → ``Classification{categoria, dominio 1-de-17, prioridad,
    resoluble}``; **no parsear strings**. Fija ``classification`` en el estado (→ Ticket.domain/priority 03).
  - El ``dominio`` **filtra el retrieval** del nodo siguiente.
  - **Fallback no-clasificable** (dominio incierto/baja confianza) → marcar para retrieval **sin filtro de
    dominio** (no forzar uno equivocado).

⚠️ Prompt-injection (refuerzo): el texto del ticket es **input no confiable** → pasarlo en turno de
usuario delimitado, aislado del system-prompt; no ejecutar instrucciones embebidas.

⚠️ Conformidad (05): ``with_structured_output`` = API objetivo de LangChain; surface exacto a pinar/
verificar al implementar (deps sin compilar).
"""
