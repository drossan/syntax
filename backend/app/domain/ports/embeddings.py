"""app.domain.ports.embeddings — puerto EmbeddingModel (embeddings de texto para RAG).

Puerto async, recortado a `embed_documents` (13, ingestión): sin `embed_query` todavía — lo fijará
el retriever (14), sin caller en este plan (mismo criterio que `ports/llm.py` con `generate`/`grade`:
no se fija una firma sin consumidor). El adaptador real vive en `app.infra.llm.openai_adapter`; el
dominio no importa `langchain_openai`.
"""

from typing import Protocol


class EmbeddingModel(Protocol):
    """Puerto de embeddings, recortado a `embed_documents`."""

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Devuelve un vector por texto, en el mismo orden que `texts`.

        :raises app.domain.errors.PortError: si el proveedor falla (timeout, error de API, clave
            ausente) o devuelve un número de vectores distinto al de textos recibidos.
        """
        ...
