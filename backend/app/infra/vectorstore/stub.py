"""app.infra.vectorstore.stub — adaptador STUB del puerto `VectorStore` (tarea 09).

Sin implementación real hasta la tarea 14 (retriever: embeddings + pgvector ANN + reranking + citas,
sobre `app.infra.vector`, hoy también doc-only). Esto NO es un placeholder silencioso: el shape de la
respuesta (`(items, total)`, `KBSearchHit`/`KBDocument`) ya es el final — la tarea 14 solo sustituye
este adaptador por uno real, sin tocar el router `kb` ni el puerto.
"""

from app.domain.entities.business import KBDocument, KBSearchHit
from app.domain.entities.enums import KbDomain, KbEstado, Package


class StubVectorStore:
    """Adaptador STUB de `VectorStore`: siempre vacío/`None` — retriever real, tarea 14."""

    async def search(
        self,
        query: str,
        *,
        domain: KbDomain | None = None,
        package: Package | None = None,
        estado: KbEstado | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[KBSearchHit], int]:
        return [], 0

    async def get_document(self, uc_id: str) -> KBDocument | None:
        return None

    async def list_documents(
        self,
        *,
        domain: KbDomain | None = None,
        package: Package | None = None,
        estado: KbEstado | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[KBDocument], int]:
        return [], 0
