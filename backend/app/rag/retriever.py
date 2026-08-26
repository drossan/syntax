"""app.rag.retriever — recuperación semántica: embeber la consulta, buscar y re-rankear.

Capa de **aplicación**: compone los dos puertos (`EmbeddingModel` y `KBIndexWriter`) y les añade la
política de `reranker.py`. No importa infra ni escribe SQL — los adaptadores llegan **inyectados**, así
que estos tests corren sin Postgres y sin red.

Lo consumen **dos** llamantes con formas distintas (ADR-0018):

- el **adaptador HTTP** (`app.infra.vectorstore.pgvector`), que además calcula la ventana, deduplica por
  `uc_id` y pagina;
- el nodo **`retrieve`** del grafo (plan del agent-graph), que consume los chunks tal cual.

De ahí dos límites deliberados: `retrieve` **recibe** un `top_k` y **no lo calcula** (el over-fetch de
la ventana es un concepto de paginación que el nodo del agente no usa, así que vive en un solo sitio: el
camino HTTP), y **no deduplica** (D3a).

KB es un recurso **global**: ninguna firma recibe `tenant_id` ni filtra por él.

Anti-patrón: SQL crudo saltándose el puerto; filtrar por tenant; calcular aquí la ventana; deduplicar.
"""

from app.domain.entities.enums import KbDomain, KbEstado, Package
from app.domain.ports.embeddings import EmbeddingModel
from app.domain.ports.vector import KBIndexWriter
from app.rag.reranker import RankedHit, rerank


class Retriever:
    """Recuperación semántica sobre la KB, con el peso de `estado` ya aplicado.

    :param embeddings: puerto de embeddings; solo se le pide `embed_query`.
    :param index: puerto de búsqueda ANN (`search`).
    :param estado_weight: `settings.rag_estado_weight`; se inyecta el **valor**, no `Settings`, para que
        esta capa no dependa de la configuración global.
    """

    def __init__(
        self,
        *,
        embeddings: EmbeddingModel,
        index: KBIndexWriter,
        estado_weight: float,
    ) -> None:
        self._embeddings = embeddings
        self._index = index
        self._estado_weight = estado_weight

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int,
        domain: KbDomain | None = None,
        package: Package | None = None,
        estado: KbEstado | None = None,
    ) -> list[RankedHit]:
        """Los `top_k` chunks más relevantes para `query`, re-rankeados y **sin deduplicar**.

        Los filtros van tal cual al puerto: si no se piden, **no se inventan** — `domain=None` recupera
        del corpus entero, que es el fallback de CU-BE-05 cuando el clasificador no fija dominio con
        confianza, y `estado=None` deja participar a los `draft` (opt-in, ADR-0010).

        :raises app.domain.errors.PortError: si falla el proveedor de embeddings o la búsqueda. **Se
            propaga**, no se convierte en lista vacía: un fallo de dependencia nunca puede presentarse
            como "la KB no tiene resultados" (garantía mínima de CU-BE-12).
        """
        query_vector = await self._embeddings.embed_query(query)
        hits = await self._index.search(
            query_vector,
            top_k=top_k,
            domain=domain,
            package=package,
            estado=estado,
        )
        return rerank(hits, weight=self._estado_weight)
