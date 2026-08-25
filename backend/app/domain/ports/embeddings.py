"""app.domain.ports.embeddings — puerto EmbeddingModel (embeddings de texto para RAG).

Puerto async con las **dos** operaciones del RAG: `embed_documents` (ingestión, plan `kb-ingestion`) y
`embed_query` (retrieval, plan `kb-retriever`). `embed_query` se añadió al aparecer su **consumidor**
—el retriever de CU-BE-12/CU-BE-05—, no antes: el criterio del repo es no fijar una firma sin caller
que la ejercite (el mismo por el que `ports/llm.py` sigue sin `generate`/`grade`).

Son operaciones **distintas y no intercambiables** aunque compartan modelo: el proveedor las expone por
separado (`aembed_documents`/`aembed_query`), y una consulta no es un documento — no se trocea, no se
persiste y su vector no se guarda.

El adaptador real vive en `app.infra.llm.openai_adapter`; el dominio no importa `langchain_openai`.
"""

from typing import Protocol


class EmbeddingModel(Protocol):
    """Puerto de embeddings: `embed_documents` (ingestión) + `embed_query` (retrieval)."""

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Devuelve un vector por texto, en el mismo orden que `texts`.

        :raises app.domain.errors.PortError: si el proveedor falla (timeout, error de API, clave
            ausente) o devuelve un número de vectores distinto al de textos recibidos.
        """
        ...

    async def embed_query(self, text: str) -> list[float]:
        """Devuelve el vector de una consulta de búsqueda.

        El vector se compara contra el corpus (`Embedding.vector`), así que su **dimensión** es parte
        del contrato: una dimensión distinta de la configurada es un fallo del **puerto**, no algo que
        se deje llegar a la comparación pgvector (donde sería un error de driver que no explica nada).

        :raises app.domain.errors.PortError: si el proveedor falla (timeout, error de API, clave
            ausente) o devuelve un vector de dimensión distinta a la configurada.
        """
        ...
