"""app.rag.retriever — recuperación semántica sobre pgvector.

GUIÓN (→ tarea 14; spec 04)
---------------------------
Qué implementar (sobre el puerto ``app.domain.ports.vector.VectorStore``):
  - ``retrieve(query, top_k, filters) -> list[Hit]``: similitud **coseno** pgvector top-k con **filtros**
    ``domain`` (lo fija el clasificador 05), ``package``, ``estado``; orden determinista por score.
  - Aplica el re-ranking de ``reranker.py`` (peso de ``estado``) antes de devolver.
  - Salida por hit: ``{uc_id, chunk_id, section_type, title, source_url, domain, estado, score}``.

KB **global** (sin filtro de tenant). Anti-patrón: SQL crudo saltándose el puerto; filtrar por tenant.
"""
