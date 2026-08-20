"""app.domain.ports.vectorstore — puerto de búsqueda/lectura de la KB (recortado a lo que el router
`kb` necesita hoy, tarea 09).

El retriever real (embeddings + pgvector ANN + reranking + citas) es la tarea 14, todavía inexistente
— este puerto ya fija el shape final para que esa tarea solo sustituya el adaptador (`StubVectorStore`
→ el real), sin tocar el router. KB es un recurso GLOBAL (sin `tenant_id`/RLS, `rbac.md`) — el puerto
no recibe `tenant_id` en ninguna firma.
"""

from typing import Protocol

from app.domain.entities.business import KBDocument, KBSearchHit
from app.domain.entities.enums import KbDomain, KbEstado, Package


class VectorStore(Protocol):
    """Puerto de búsqueda/lectura de la KB."""

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
        """Búsqueda semántica, orden `score desc` (contrato). `(items, total)` — no `PageResult`
        porque este puerto no comparte el resto del árbol de repos de negocio/identidad."""
        ...

    async def get_document(self, uc_id: str) -> KBDocument | None:
        """Documento por `uc_id` (clave única de negocio), o `None` si no existe."""
        ...

    async def list_documents(
        self,
        *,
        domain: KbDomain | None = None,
        package: Package | None = None,
        estado: KbEstado | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[KBDocument], int]:
        """Lista de documentos filtrada, `(items, total)`."""
        ...
