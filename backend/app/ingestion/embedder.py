"""app.ingestion.embedder — genera el vector de cada chunk (tarea backend-kb-ingestion-05).

El embedder es **"tonto"**: siempre embebe lo que recibe, sin conocer BD ni decidir si un chunk
cambió — esa decisión ("¿hace falta re-embeber este chunk?") vive en el pipeline (`-06`), que conoce
tanto `KBIndexWriter.existing_chunk_contents` como este módulo, y solo le pasa los chunks nuevos o con
contenido cambiado. Mantiene el embedder testeable con un `EmbeddingModel` fake puro, sin mocks de BD
(mismo patrón que `_FakeChatModel` en `tests/test_classification.py`).

`embed()` no importa `app.core.config`: `batch_size` lo resuelve el llamante (el pipeline, desde
`settings.embedding_batch_size`) — mismo criterio que `token_budget`/`encoding` en `app.ingestion.chunker`.
"""

from dataclasses import dataclass

from app.domain.errors import PortError
from app.domain.ports.embeddings import EmbeddingModel
from app.ingestion.chunker import Chunk


@dataclass(frozen=True)
class ChunkWithVector:
    """Un `Chunk` ya embebido."""

    chunk: Chunk
    vector: list[float]


async def embed(
    chunks: list[Chunk], model: EmbeddingModel, *, batch_size: int
) -> list[ChunkWithVector]:
    """Embebe `chunks` con `model`, troceando en sub-lotes de `batch_size` si hace falta.

    Preserva el orden de entrada en la salida, sea una o varias llamadas a `embed_documents`.

    :raises app.domain.errors.PortError: si `model` falla, o si devuelve para algún sub-lote un
        número de vectores distinto al de textos enviados.
    """
    results: list[ChunkWithVector] = []
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        vectors = await model.embed_documents([c.content for c in batch])
        if len(vectors) != len(batch):
            raise PortError(
                f"el proveedor devolvió {len(vectors)} vectores para {len(batch)} textos"
            )
        results.extend(
            ChunkWithVector(chunk=chunk, vector=vector)
            for chunk, vector in zip(batch, vectors, strict=True)
        )
    return results
