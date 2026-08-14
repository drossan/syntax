"""app.rag — retriever RAG (recuperación + confianza + citas).

GUIÓN (→ tarea 14)
------------------
Recupera contexto de la KB desde pgvector para el grafo del agente. Ver `rag-ingestion`
(tarea 04).

Qué implementar:
  - búsqueda semántica en ``app.infra.vector`` con **filtros** (dominio del clasificador,
    package, estado…) + orden determinista.
  - rerank + **confianza híbrida** (similitud + ``grade`` del nodo) → auto vs escalado.
  - **citas** de las fuentes (uc-id/dominio/sección) para el draft.
  - peso de ``estado`` explícito (draft no penalizado a ciegas).

Dependencias: consume el puerto de vector store; lo consume el nodo ``retrieve`` del grafo
(``app.agents``). Anti-patrón: acoplar el retriever a SQL crudo saltándose el puerto.
"""
