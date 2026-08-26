"""app.infra.vector — adaptador SQLAlchemy+pgvector de `KBIndexWriter` (tarea backend-kb-ingestion-02;
`search` real en backend-kb-retriever-04).

Sirve a **dos caminos** con la misma tabla: la **escritura** de la ingestión (`upsert_document` y
compañía) y la **búsqueda ANN** (`search`), que es la única puerta de entrada al retrieval — la usan
tanto el camino HTTP del panel como el nodo `retrieve` del grafo. De ahí que `embedding_model` sea un
parámetro **opcional** del constructor: solo `search` lo necesita. Ver el docstring de
`app.domain.ports.vector` para la resolución del doble contrato con
`app.domain.ports.vectorstore.VectorStore`.

`search` devuelve **coseno crudo, sin política de negocio**: el peso de `estado` y el dedup viven en
`app.rag` (ADR-0018). Meterlos en el `ORDER BY` dejaría inservible cualquier índice ANN futuro y haría
la política intestable sin Postgres.

Reconciliación en `upsert_document`: los `kb_chunk` (y su `embedding`, cascada a nivel de BD) cuyo
`ordinal` ya no llega en `chunks` se borran con un `DELETE` real — necesario para que el
`ondelete="CASCADE"` de la FK `embedding.chunk_id` se dispare (un simple "quitar de la sesión" no lo
haría). Un `ChunkWrite.vector=None` sobre un chunk YA persistido conserva su `embedding` existente
(edición parcial); sobre un chunk nuevo, simplemente no crea ninguna fila de `embedding` para él.
"""

import uuid

from sqlalchemy import delete as sql_delete
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.enums import KbDomain, KbEstado, Package
from app.domain.errors import PortError
from app.domain.ports.vector import ChunkWrite, Hit, KBDocumentDraft, UpsertReport
from app.infra.db.models.enums import KbDomain as KbDomainOrm
from app.infra.db.models.enums import KbEstado as KbEstadoOrm
from app.infra.db.models.kb import Embedding
from app.infra.db.models.kb import KBChunk as KBChunkModel
from app.infra.db.models.kb import KBDocument as KBDocumentModel
from app.infra.db.repositories._enum_bridge import to_domain, to_orm

_INGESTION_LOCK_KEY = 8199251
"""Clave arbitraria del advisory lock de ingestión (`pg_try_advisory_lock`) — una sola ejecución de
`make ingest` a la vez, en todo el cluster, sin importar el `uc_id` que procese."""


class SqlAlchemyKBIndexWriter:
    """Adaptador de `KBIndexWriter` (`app.domain.ports.vector`)."""

    def __init__(self, session: AsyncSession, *, embedding_model: str | None = None) -> None:
        """
        :param session: sesión async; el llamante gobierna la transacción.
        :param embedding_model: modelo contra el que compara `search` (`settings.embedding_model`).
            **Solo lo necesita el camino de LECTURA**: la ingestión construye este adaptador con la
            sesión a secas, y para ella exigirlo sería pedir un dato que no usa (hay ~60 callers así).
            Sin él, `search` falla explícito en vez de comparar contra vectores de cualquier modelo.
        """
        self._session = session
        self._embedding_model = embedding_model

    async def existing_uc_ids(self) -> set[str]:
        try:
            rows = (await self._session.execute(select(KBDocumentModel.uc_id))).scalars().all()
        except Exception as exc:
            raise PortError("fallo al leer los uc_id existentes") from exc
        return set(rows)

    async def existing_chunk_contents(self, uc_id: str) -> dict[int, str]:
        try:
            doc = (
                await self._session.execute(
                    select(KBDocumentModel).where(KBDocumentModel.uc_id == uc_id)
                )
            ).scalar_one_or_none()
            if doc is None:
                return {}
            rows = (
                await self._session.execute(
                    select(KBChunkModel.ordinal, KBChunkModel.content).where(
                        KBChunkModel.document_id == doc.id
                    )
                )
            ).all()
        except Exception as exc:
            raise PortError("fallo al leer los chunks existentes") from exc
        return {ordinal: content for ordinal, content in rows}

    async def upsert_document(self, doc: KBDocumentDraft, chunks: list[ChunkWrite]) -> UpsertReport:
        try:
            existing = (
                await self._session.execute(
                    select(KBDocumentModel).where(KBDocumentModel.uc_id == doc.uc_id)
                )
            ).scalar_one_or_none()
            created = existing is None
            if existing is None:
                existing = KBDocumentModel(id=uuid.uuid4(), uc_id=doc.uc_id)
                self._session.add(existing)
            existing.domain = to_orm(KbDomainOrm, doc.domain)
            existing.package = doc.package.value
            existing.estado = to_orm(KbEstadoOrm, doc.estado)
            existing.title = doc.title
            existing.source_url = doc.source_url
            existing.traza = doc.traza
            existing.updated = doc.updated

            existing_chunks = {
                row.ordinal: row
                for row in (
                    await self._session.execute(
                        select(KBChunkModel).where(KBChunkModel.document_id == existing.id)
                    )
                ).scalars()
            }
            new_ordinals = {chunk.ordinal for chunk in chunks}
            stale_ordinals = set(existing_chunks) - new_ordinals
            chunks_deleted = 0
            if stale_ordinals:
                await self._session.execute(
                    sql_delete(KBChunkModel).where(
                        KBChunkModel.document_id == existing.id,
                        KBChunkModel.ordinal.in_(stale_ordinals),
                    )
                )
                chunks_deleted = len(stale_ordinals)

            # Dos pasadas: primero se persisten TODOS los `kb_chunk` (flush) y solo DESPUÉS se crean/
            # actualizan sus `embedding` — sin `relationship()` entre `KBChunk`/`Embedding` (solo FK de
            # columna), el unit-of-work no conoce la dependencia entre objetos recién añadidos y podría
            # intentar el INSERT de `embedding` antes que el de su `kb_chunk` (viola la FK).
            chunk_rows: dict[int, KBChunkModel] = {}
            for chunk in chunks:
                row = existing_chunks.get(chunk.ordinal)
                if row is None:
                    row = KBChunkModel(
                        id=uuid.uuid4(),
                        document_id=existing.id,
                        ordinal=chunk.ordinal,
                        section_type=chunk.section_type,
                        content=chunk.content,
                        token_count=chunk.token_count,
                    )
                    self._session.add(row)
                else:
                    row.section_type = chunk.section_type
                    row.content = chunk.content
                    row.token_count = chunk.token_count
                chunk_rows[chunk.ordinal] = row
            await self._session.flush()

            for chunk in chunks:
                if chunk.vector is None:
                    continue
                row = chunk_rows[chunk.ordinal]
                embedding = (
                    await self._session.execute(
                        select(Embedding).where(Embedding.chunk_id == row.id)
                    )
                ).scalar_one_or_none()
                if embedding is None:
                    self._session.add(
                        Embedding(
                            id=uuid.uuid4(), chunk_id=row.id, model=chunk.model, vector=chunk.vector
                        )
                    )
                else:
                    embedding.vector = chunk.vector
                    embedding.model = chunk.model
            await self._session.flush()
        except Exception as exc:
            raise PortError("fallo al hacer upsert del documento KB") from exc
        return UpsertReport(created=created, chunks_deleted=chunks_deleted)

    async def delete_by_uc_ids(self, uc_ids: set[str]) -> int:
        if not uc_ids:
            return 0
        try:
            result = await self._session.execute(
                sql_delete(KBDocumentModel)
                .where(KBDocumentModel.uc_id.in_(uc_ids))
                .returning(KBDocumentModel.id)
            )
            deleted = result.scalars().all()
        except Exception as exc:
            raise PortError("fallo al borrar documentos KB") from exc
        return len(deleted)

    async def search(
        self,
        query_vector: list[float],
        *,
        top_k: int,
        domain: KbDomain | None = None,
        package: Package | None = None,
        estado: KbEstado | None = None,
    ) -> list[Hit]:
        """Los `top_k` chunks más parecidos a `query_vector` por **similitud coseno**, sin política.

        Devuelve el **coseno crudo acotado**: `score = max(0, 1 - distance)`. El clamp no es cosmético
        — `1 - cosine_distance` ∈ `[-1, 1]`, y un score negativo haría que el boost multiplicativo de
        `app.rag.reranker` **penalizara** al documento e invirtiera su orden frente a un `draft`. Un
        coseno negativo es "menos relacionado que el azar": no hay ranking que preservar bajo 0.

        Solo participan los vectores del **modelo configurado**: comparar dos espacios vectoriales
        distintos devuelve basura perfectamente ordenada, sin ninguna señal de error. Por eso `search`
        exige un adaptador construido con `embedding_model` y falla explícito si no lo tiene.

        Los chunks **sin fila `embedding`** (ingesta parcial) quedan fuera por el `JOIN`: no participan
        y no rompen la consulta.

        Los filtros `domain`/`package`/`estado` son opcionales y se combinan por conjunción; `estado`
        es **opt-in** (ADR-0010): sin pedirlo, los `draft` participan — son el 81% del corpus y
        filtrarlos por defecto vaciaría el retrieval. El **peso** de `estado` y el dedup NO viven aquí,
        sino en `app.rag` (ADR-0018): mantener la infra sin política es lo que deja utilizable un
        futuro índice ANN, porque el `ORDER BY` no lleva expresiones ponderadas.

        :raises app.domain.errors.PortError: si el adaptador se construyó sin `embedding_model`, o ante
            un fallo de infraestructura (BD caída/timeout).
        """
        if self._embedding_model is None:
            raise PortError(
                "este adaptador se construyó sin `embedding_model` (camino de ingestión); `search` "
                "necesita saber contra qué modelo comparar para no cruzar espacios vectoriales"
            )
        distance = Embedding.vector.cosine_distance(query_vector)
        stmt = (
            select(
                KBDocumentModel.uc_id,
                KBChunkModel.id,
                KBChunkModel.section_type,
                KBChunkModel.content,
                KBDocumentModel.title,
                KBDocumentModel.source_url,
                KBDocumentModel.domain,
                KBDocumentModel.estado,
                distance.label("distance"),
            )
            .join(KBChunkModel, KBChunkModel.id == Embedding.chunk_id)
            .join(KBDocumentModel, KBDocumentModel.id == KBChunkModel.document_id)
            .where(Embedding.model == self._embedding_model)
            .order_by(distance.asc())
            .limit(top_k)
        )
        if domain is not None:
            stmt = stmt.where(KBDocumentModel.domain == to_orm(KbDomainOrm, domain))
        if package is not None:
            stmt = stmt.where(KBDocumentModel.package == package.value)
        if estado is not None:
            stmt = stmt.where(KBDocumentModel.estado == to_orm(KbEstadoOrm, estado))
        try:
            rows = (await self._session.execute(stmt)).all()
        except Exception as exc:
            raise PortError("fallo al buscar en la KB") from exc
        return [
            Hit(
                uc_id=row.uc_id,
                chunk_id=row.id,
                section_type=row.section_type,
                title=row.title,
                source_url=row.source_url,
                domain=to_domain(KbDomain, row.domain),
                estado=to_domain(KbEstado, row.estado),
                score=max(0.0, 1.0 - row.distance),
                content=row.content,
            )
            for row in rows
        ]

    async def try_acquire_ingestion_lock(self) -> bool:
        try:
            result = await self._session.execute(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": _INGESTION_LOCK_KEY}
            )
            acquired = result.scalar_one()
        except Exception as exc:
            raise PortError("fallo al intentar el advisory lock de ingestión") from exc
        return bool(acquired)
