"""app.domain.ports.vector — puerto del vector store (retrieval pgvector).

GUIÓN (→ tarea 10; adaptador en app.infra.vector, consumido por 13/14)
---------------------------------------------------------------------
Interfaz (``Protocol``/ABC, async) del almacén de embeddings sobre pgvector (KB **global**, sin RLS de
tenant). Firmas en tipos de dominio, no SQLAlchemy.

  - ``upsert_chunks(doc, chunks_with_vectors)`` — idempotente por ``uc_id`` (04); reconcilia huérfanos.
  - ``search(query_vector, top_k, filters) -> list[Hit]`` — similitud coseno + filtros
    ``domain/package/estado`` + re-ranking por ``estado`` (peso config, 04); devuelve citas
    ``{uc_id, chunk_id, section_type, title, source_url, score}``.

Contrato: lo implementa ``app.infra.vector`` (13 ingestión / 14 retriever); el grafo (05) consume la
salida como señal de confianza (similitud) + citas.
Anti-patrón: filtrar por tenant en la KB (es compartida); exponer tipos de infra en el puerto.
"""
