"""app.infra.vector — almacén de embeddings sobre pgvector.

GUIÓN (→ tareas 13 ingestión y 14 retriever)
--------------------------------------------
Adaptador del puerto de vector store usando la extensión **pgvector** en el MISMO Postgres
que el negocio. Persiste chunks de la KB con su vector ``vector(EMBEDDING_DIM)`` y metadatos
de categorización (dominio, uc-id, package, estado, tipo-de-sección).

Qué implementar:
  - upsert idempotente por ``uc-id`` (lo consume el pipeline de ingestión, tarea 13).
  - búsqueda por similitud con filtros + orden determinista (lo consume el retriever, tarea 14).

La KB es **compartida** entre tenants → sin RLS de tenant en estas tablas. La dimensión del
vector viene de config (``EMBEDDING_DIM``); cambiarla obliga a re-embed. Ver `rag-ingestion`
(tarea 04).
"""
