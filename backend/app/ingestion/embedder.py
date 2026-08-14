"""app.ingestion.embedder — genera embeddings de los chunks.

GUIÓN (→ tarea 13; spec 04/09)
------------------------------
Qué implementar:
  - Usa el **puerto de embeddings** (``app.domain.ports.llm.EmbeddingModel``, adaptador OpenAI de 09):
    ``EMBEDDING_MODEL`` → ``vector(settings.EMBEDDING_DIM)`` (dimensión de config, no literal).
  - Solo **re-embebe si el contenido del chunk cambió** (hash del contenido) → evita coste innecesario.
  - Batching de llamadas al proveedor; respeta timeout/retry del adaptador (09).

Anti-patrón: hardcodear la dimensión; re-embeber todo el corpus en cada ingesta sin comprobar cambios.
"""
