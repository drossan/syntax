"""app.agents.nodes.retrieve — recuperación de contexto RAG.

GUIÓN (→ tarea 15; spec 05/04)
------------------------------
  - Invoca el retriever (``app.rag.retriever`` 14) con el ``dominio`` de ``classification`` como filtro
    (+ package/estado si aplica); si no-clasificable → **sin filtro de dominio** (fallback).
  - Escribe ``retrieved`` (hits + citas) en el estado; **0/1 resultados** → señal para la ruta
    "insuficiente → nota al humano" (decide/grade).

Anti-patrón: recuperar sin filtro cuando sí hay dominio fiable; acoplar a SQL crudo (usar el puerto/retriever).
"""
