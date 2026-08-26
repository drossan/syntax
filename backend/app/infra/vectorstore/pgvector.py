"""app.infra.vectorstore.pgvector — adaptador Postgres del puerto de LECTURA de la KB
(`app.domain.ports.vectorstore.VectorStore`), tarea `backend-kb-retriever-02`.

Sustituye a `StubVectorStore` (que devolvía `[], 0` / `None` y por eso `/kb` se veía vacío en el
panel). El **swap** de `get_vector_store()` lo hace la tarea `-07`, no esta: el router resuelve los
tres endpoints por la MISMA dependencia, así que no puede cablearse a medias.

**Reparto del SQL de `kb_document`** (deuda de los dos puertos, ADR-0018): la **escritura** vive en
`app.infra.vector.SqlAlchemyKBIndexWriter` y la **lectura** aquí, con **un solo sitio por operación**.
Es la disciplina que sustituye a colapsar los dos puertos, que metería lectura paginada de negocio
dentro de un puerto llamado `KBIndexWriter`.

`list_documents`/`get_document` **no tocan vectores**: son SQL plano sobre `kb_document`. `search` sí, y
es donde se traduce del mundo del **retriever** (chunks, `Hit`, score crudo) al del **router**
(documentos, `KBSearchHit`, score ponderado): ventana → dedup → página.

Un fallo de infraestructura sale como `PortError` (→ **502**), nunca como listado vacío ni como `None`:
un despliegue roto tiene que distinguirse de "la KB no tiene resultados" (garantía mínima de CU-BE-12).
"""

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.domain.entities.business import KBDocument, KBSearchHit
from app.domain.entities.enums import KbDomain, KbEstado, Package
from app.domain.errors import PortError
from app.domain.ports.embeddings import EmbeddingModel
from app.infra.db.models.enums import KbDomain as KbDomainOrm
from app.infra.db.models.enums import KbEstado as KbEstadoOrm
from app.infra.db.models.kb import KBDocument as KBDocumentModel
from app.infra.db.repositories._enum_bridge import to_domain, to_orm
from app.infra.vector import SqlAlchemyKBIndexWriter
from app.rag.dedup import dedup_by_uc_id
from app.rag.reranker import RankedHit
from app.rag.retriever import Retriever

SNIPPET_MAX_CHARS = 280
"""Longitud máxima del `snippet` de un resultado de búsqueda.

**Constante, no un setting**: no hay dos despliegues que la quieran distinta, y un setting invitaría a
"afinarla" sin ningún criterio para hacerlo. El truncado ocurre en el **backend** porque la tarjeta del
panel no tiene `line-clamp` y este plan no toca código del front.
"""


class PgVectorStore:
    """Adaptador de `VectorStore` sobre Postgres/pgvector.

    :param session: sesión async del request. La comparte con el router (caché de dependencias de
        FastAPI), así que no abre una transacción propia ni una segunda conexión.
    :param embeddings: puerto de embeddings. **Opcional**: `list_documents`/`get_document` no lo
        necesitan, y exigirlo haría que una configuración de embeddings inservible tumbara `/kb/documents`,
        que no toca embeddings para nada.
    :param settings: de aquí salen `rag_search_window`, `rag_chunks_per_doc`, `rag_estado_weight` y
        `embedding_model`.
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        embeddings: EmbeddingModel | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._session = session
        self._embeddings = embeddings
        self._settings = settings

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
        """Búsqueda semántica paginada, orden `score` descendente. `(items, total)`.

        Traduce del mundo del retriever al del router en cuatro pasos:

        1. **Over-fetch**: se piden `rag_search_window * rag_chunks_per_doc` **chunks**. El cálculo vive
           aquí y en ningún otro sitio: la ventana es un concepto de **paginación**, y el nodo
           `retrieve` del agente —que comparte el retriever— no pagina. Sin el factor, una ventana
           medida en documentos se llenaría de chunks del mismo documento y la página saldría truncada.
        2. **Dedup por `uc_id`** sobre la lista ya re-rankeada: un item por documento, el de su mejor
           sección (RN-1).
        3. **Ventana**: se recortan `rag_search_window` **documentos**. `total` = los que quedan ahí
           dentro, no el corpus: una búsqueda ANN no tiene cardinalidad (RN-3).
        4. **Página**: `items = ventana[(page-1)*page_size : page*page_size]`. Una página más allá de la
           ventana devuelve `items` vacío **conservando el mismo `total`**.

        El `score` que sale es el **ponderado** (RN-4), no el coseno crudo: puede superar `1.0`.

        :raises app.domain.errors.PortError: si falla el proveedor de embeddings o la base de datos. **No
            se traga**: un fallo de dependencia servido como página vacía es indistinguible de una KB sin
            resultados, que es el fallo mudo que este camino existe para evitar.
        """
        if self._embeddings is None or self._settings is None:
            raise PortError(
                "este `PgVectorStore` se construyó sin `embeddings`/`settings`; solo puede listar y "
                "abrir documentos, no buscar"
            )
        window = self._settings.rag_search_window
        retriever = Retriever(
            embeddings=self._embeddings,
            index=SqlAlchemyKBIndexWriter(
                self._session, embedding_model=self._settings.embedding_model
            ),
            estado_weight=self._settings.rag_estado_weight,
        )
        ranked = await retriever.retrieve(
            query,
            top_k=window * self._settings.rag_chunks_per_doc,
            domain=domain,
            package=package,
            estado=estado,
        )
        documents = dedup_by_uc_id(ranked)[:window]
        page_items = documents[(page - 1) * page_size : page * page_size]
        return [_to_search_hit(item) for item in page_items], len(documents)

    async def get_document(self, uc_id: str) -> KBDocument | None:
        """Documento por su `uc_id` (clave única de negocio), o `None` si no existe.

        `None` NO es un error: el **404** lo traduce el router. Un `uc_id` con forma inesperada
        (comodines de `LIKE`, comillas, vacío) es simplemente un `uc_id` que no existe — la
        comparación es de igualdad, parametrizada.

        Los glosarios se abren igual que cualquier otro documento, por su `uc_id` sintético
        (`__glosario__:<dominio>`, RN-9 de CU-BE-12): no hay ninguna rama especial para ellos.

        Un `uc_id` con un byte **NUL** (`%00` en la URL) se descarta **antes** de consultar: Postgres
        no puede almacenar `\\x00` en una columna de texto, así que ese documento no existe **por
        construcción** — y dejarlo llegar al driver produciría un error de infraestructura, es decir un
        502 que culpa a la base de datos de una entrada del cliente.

        :raises app.domain.errors.PortError: fallo de infraestructura (BD caída/timeout).
        """
        if "\x00" in uc_id:
            return None
        try:
            row = (
                await self._session.execute(
                    select(KBDocumentModel).where(KBDocumentModel.uc_id == uc_id)
                )
            ).scalar_one_or_none()
        except Exception as exc:
            raise PortError(f"fallo al leer el documento de KB {uc_id!r}") from exc
        return None if row is None else _to_entity(row)

    async def list_documents(
        self,
        *,
        domain: KbDomain | None = None,
        package: Package | None = None,
        estado: KbEstado | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[KBDocument], int]:
        """Página de documentos filtrada, `(items, total)`.

        Los filtros son opcionales y **se combinan por conjunción** (`AND`); cada uno se omite si es
        `None` — sin filtros no se filtra nada, así que `draft` y `active` conviven en el listado (el
        peso de `estado` es cosa de `/kb/search`, no del listado).

        **Orden determinista `uc_id` ascendente** (RN-6 de CU-BE-12): `uc_id` es único, así que basta
        para que la paginación sea estable. Sin `ORDER BY` explícito, Postgres puede devolver las filas
        en cualquier orden y el front pinta como "documentos relacionados" lo que en realidad es un
        listado arbitrario.

        `total` cuenta el conjunto **filtrado** y **sin paginar**: es cuántos documentos hay que
        recorrer, no cuántos caben en esta página.

        :raises app.domain.errors.PortError: fallo de infraestructura (BD caída/timeout).
        """
        try:
            total = (
                await self._session.execute(
                    _filtered(
                        select(func.count()).select_from(KBDocumentModel), domain, package, estado
                    )
                )
            ).scalar_one()
            rows = (
                (
                    await self._session.execute(
                        _filtered(select(KBDocumentModel), domain, package, estado)
                        .order_by(KBDocumentModel.uc_id.asc())
                        .offset((page - 1) * page_size)
                        .limit(page_size)
                    )
                )
                .scalars()
                .all()
            )
        except Exception as exc:
            raise PortError("fallo al listar los documentos de KB") from exc
        return [_to_entity(row) for row in rows], total


def _filtered[T: tuple[object, ...]](
    stmt: Select[T],
    domain: KbDomain | None,
    package: Package | None,
    estado: KbEstado | None,
) -> Select[T]:
    """Aplica al `SELECT` los filtros que no son `None`, por conjunción.

    Un solo sitio para las tres condiciones: el `COUNT` del `total` y el `SELECT` de los `items`
    **tienen** que filtrar igual, o el front pagina sobre un total que no le corresponde.
    """
    if domain is not None:
        stmt = stmt.where(KBDocumentModel.domain == to_orm(KbDomainOrm, domain))
    if package is not None:
        stmt = stmt.where(KBDocumentModel.package == package.value)
    if estado is not None:
        stmt = stmt.where(KBDocumentModel.estado == to_orm(KbEstadoOrm, estado))
    return stmt


def _to_search_hit(ranked: RankedHit) -> KBSearchHit:
    """Mapea un `RankedHit` a la entidad de salida de la API.

    El `score` que viaja es el **ponderado**, no el crudo del `Hit`: el crudo se queda dentro, como
    señal para la confianza híbrida de CU-BE-05 (hallazgo C2).
    """
    hit = ranked.hit
    return KBSearchHit(
        uc_id=hit.uc_id,
        title=hit.title,
        section_type=hit.section_type,
        domain=hit.domain,
        estado=hit.estado,
        source_url=hit.source_url,
        score=ranked.weighted_score,
        snippet=_snippet(hit.content),
    )


def _snippet(content: str) -> str:
    """El **principio** de la sección, truncado a `SNIPPET_MAX_CHARS` por límite de palabra.

    **No se centra en el término buscado** (RN-5): la búsqueda es semántica, así que el chunk puede
    casar sin contener la palabra — centrar el extracto fallaría justo cuando el RAG hace bien su
    trabajo, y prometería una relación literal que no existe.

    Reglas de borde:

    - Texto más corto que el tope → se sirve **entero, sin elipsis**: la elipsis promete texto que no hay.
    - Sin ningún espacio antes del tope (una sola palabra larguísima) → se corta **en seco**. Devolver el
      chunk entero rompería la tarjeta del panel, que no tiene `line-clamp`.
    - Texto vacío → snippet vacío: un glosario vacío es un documento **válido** (`rag-ingestion.md` §2.1).
    """
    if len(content) <= SNIPPET_MAX_CHARS:
        return content
    cut = content[:SNIPPET_MAX_CHARS]
    last_space = cut.rfind(" ")
    if last_space > 0:
        cut = cut[:last_space]
    return cut.rstrip() + "…"


def _to_entity(row: KBDocumentModel) -> KBDocument:
    """Mapea la fila ORM a la entidad de dominio, convirtiendo los enums **por valor**.

    `domain`/`estado` son enums de Postgres (clases ORM distintas de las de dominio a propósito,
    `_enum_bridge`); `package` se persiste como `String`, así que se reconstruye desde su valor.
    `updated` puede ser `None` y se sirve como ausente — no es un error.
    """
    return KBDocument(
        uc_id=row.uc_id,
        domain=to_domain(KbDomain, row.domain),
        package=Package(row.package),
        estado=to_domain(KbEstado, row.estado),
        title=row.title,
        source_url=row.source_url,
        updated=row.updated,
    )
