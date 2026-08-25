"""Tests de integración de `SqlAlchemyKBIndexWriter` (tarea `backend-kb-ingestion-02`). Postgres real
vía `superuser_engine` (KB es global, sin RLS — no hay aislamiento de tenant que verificar aquí).
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from app.domain.entities.enums import KbDomain, KbEstado, Package
from app.domain.errors import PortError
from app.domain.ports.vector import ChunkWrite, KBDocumentDraft
from app.infra.db.models.kb import EMBEDDING_DIM_LITERAL
from app.infra.vector import SqlAlchemyKBIndexWriter
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_TRUNCATE_TABLES = "TRUNCATE embedding, kb_chunk, kb_document RESTART IDENTITY CASCADE"


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables(superuser_engine: AsyncEngine) -> AsyncIterator[None]:
    async with superuser_engine.begin() as conn:
        await conn.execute(text(_TRUNCATE_TABLES))
    yield
    async with superuser_engine.begin() as conn:
        await conn.execute(text(_TRUNCATE_TABLES))


@pytest_asyncio.fixture
async def session(superuser_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with async_sessionmaker(superuser_engine, expire_on_commit=False)() as s:
        yield s


def _draft(**overrides: object) -> KBDocumentDraft:
    defaults: dict[str, object] = {
        "uc_id": f"uc-{uuid.uuid4()}",
        "domain": KbDomain.authoring_and_editor,
        "package": Package.syntax_cx,
        "estado": KbEstado.active,
        "title": "Título",
        "source_url": "domains/authoring-and-editor/uc/uc-x.md",
    }
    defaults.update(overrides)
    return KBDocumentDraft(**defaults)  # type: ignore[arg-type]


def _vector(value: float) -> list[float]:
    """Vector de la dimensión REAL de la columna (1536) — un vector corto viola el `Vector(1536)`
    literal de `embedding.vector` con `asyncpg.exceptions.DataError`, no con un fallo de negocio."""
    return [value] * EMBEDDING_DIM_LITERAL


_UNSET = object()
"""Sentinel propio: `vector=None` es un valor EXPLÍCITO válido de `ChunkWrite` ("no lo toques"), así
que no puede confundirse con "no se pasó `vector`" (un default `None` normal sí los confundiría)."""


def _chunk(
    ordinal: int, content: str = "contenido", vector: list[float] | None | object = _UNSET
) -> ChunkWrite:
    resolved_vector = _vector(0.1) if vector is _UNSET else vector
    return ChunkWrite(
        ordinal=ordinal,
        section_type="comportamiento",
        content=content,
        token_count=len(content.split()),
        vector=resolved_vector,  # type: ignore[arg-type]
        model="text-embedding-3-small",
    )


async def _embedding_count(session: AsyncSession, chunk_id: uuid.UUID) -> int:
    result = await session.execute(
        text("SELECT count(*) FROM embedding WHERE chunk_id = :chunk_id"), {"chunk_id": chunk_id}
    )
    return result.scalar_one()


async def _chunk_count(session: AsyncSession, document_id: uuid.UUID) -> int:
    result = await session.execute(
        text("SELECT count(*) FROM kb_chunk WHERE document_id = :document_id"),
        {"document_id": document_id},
    )
    return result.scalar_one()


# ── upsert_document ──


async def test_upsert_document_inserts_a_new_document_with_chunks_and_embeddings(
    session: AsyncSession,
) -> None:
    writer = SqlAlchemyKBIndexWriter(session)
    draft = _draft()
    report = await writer.upsert_document(draft, [_chunk(0), _chunk(1)])
    await session.commit()

    assert report.created is True
    assert report.chunks_deleted == 0
    row = (
        await session.execute(
            text("SELECT id, title FROM kb_document WHERE uc_id = :uc_id"), {"uc_id": draft.uc_id}
        )
    ).one()
    assert row.title == "Título"
    assert await _chunk_count(session, row.id) == 2


async def test_upsert_document_on_an_existing_uc_id_does_not_duplicate_the_document(
    session: AsyncSession,
) -> None:
    writer = SqlAlchemyKBIndexWriter(session)
    draft = _draft()
    await writer.upsert_document(draft, [_chunk(0)])
    await session.commit()

    updated_draft = _draft(uc_id=draft.uc_id, title="Título actualizado")
    report = await writer.upsert_document(updated_draft, [_chunk(0)])
    await session.commit()

    assert report.created is False
    rows = (
        await session.execute(
            text("SELECT title FROM kb_document WHERE uc_id = :uc_id"), {"uc_id": draft.uc_id}
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].title == "Título actualizado"


async def test_upsert_document_deletes_chunks_whose_ordinal_no_longer_arrives(
    session: AsyncSession,
) -> None:
    writer = SqlAlchemyKBIndexWriter(session)
    draft = _draft()
    await writer.upsert_document(draft, [_chunk(0), _chunk(1), _chunk(2)])
    await session.commit()

    report = await writer.upsert_document(draft, [_chunk(0), _chunk(1)])
    await session.commit()

    assert report.chunks_deleted == 1
    doc_id = (
        await session.execute(
            text("SELECT id FROM kb_document WHERE uc_id = :uc_id"), {"uc_id": draft.uc_id}
        )
    ).scalar_one()
    assert await _chunk_count(session, doc_id) == 2


async def test_upsert_document_with_empty_chunks_deletes_all_previous_chunks(
    session: AsyncSession,
) -> None:
    writer = SqlAlchemyKBIndexWriter(session)
    draft = _draft()
    await writer.upsert_document(draft, [_chunk(0), _chunk(1)])
    await session.commit()

    report = await writer.upsert_document(draft, [])
    await session.commit()

    assert report.chunks_deleted == 2
    doc_id = (
        await session.execute(
            text("SELECT id FROM kb_document WHERE uc_id = :uc_id"), {"uc_id": draft.uc_id}
        )
    ).scalar_one()
    assert await _chunk_count(session, doc_id) == 0
    # el documento SIGUE existiendo (chunk retirado de un documento que sigue vivo, no delete_by_uc_ids)
    still_exists = (
        await session.execute(
            text("SELECT count(*) FROM kb_document WHERE uc_id = :uc_id"), {"uc_id": draft.uc_id}
        )
    ).scalar_one()
    assert still_exists == 1


async def test_upsert_document_preserves_the_embedding_of_a_chunk_with_vector_none(
    session: AsyncSession,
) -> None:
    writer = SqlAlchemyKBIndexWriter(session)
    draft = _draft()
    await writer.upsert_document(draft, [_chunk(0, vector=_vector(0.9))])
    await session.commit()
    doc_id = (
        await session.execute(
            text("SELECT id FROM kb_document WHERE uc_id = :uc_id"), {"uc_id": draft.uc_id}
        )
    ).scalar_one()
    chunk_id = (
        await session.execute(
            text("SELECT id FROM kb_chunk WHERE document_id = :d AND ordinal = 0"), {"d": doc_id}
        )
    ).scalar_one()
    original_vector = (
        await session.execute(
            text("SELECT vector FROM embedding WHERE chunk_id = :c"), {"c": chunk_id}
        )
    ).scalar_one()

    await writer.upsert_document(draft, [_chunk(0, content="editado sin re-embeber", vector=None)])
    await session.commit()

    unchanged_vector = (
        await session.execute(
            text("SELECT vector FROM embedding WHERE chunk_id = :c"), {"c": chunk_id}
        )
    ).scalar_one()
    assert unchanged_vector == original_vector
    new_content = (
        await session.execute(text("SELECT content FROM kb_chunk WHERE id = :c"), {"c": chunk_id})
    ).scalar_one()
    assert new_content == "editado sin re-embeber"


async def test_upsert_document_replaces_the_embedding_of_a_chunk_with_a_real_vector(
    session: AsyncSession,
) -> None:
    writer = SqlAlchemyKBIndexWriter(session)
    draft = _draft()
    await writer.upsert_document(draft, [_chunk(0, vector=_vector(0.1))])
    await session.commit()
    doc_id = (
        await session.execute(
            text("SELECT id FROM kb_document WHERE uc_id = :uc_id"), {"uc_id": draft.uc_id}
        )
    ).scalar_one()
    chunk_id = (
        await session.execute(
            text("SELECT id FROM kb_chunk WHERE document_id = :d AND ordinal = 0"), {"d": doc_id}
        )
    ).scalar_one()
    original_vector = (
        await session.execute(
            text("SELECT vector FROM embedding WHERE chunk_id = :c"), {"c": chunk_id}
        )
    ).scalar_one()

    await writer.upsert_document(
        draft, [_chunk(0, content="contenido cambiado", vector=_vector(0.5))]
    )
    await session.commit()

    assert await _embedding_count(session, chunk_id) == 1
    new_vector = (
        await session.execute(
            text("SELECT vector FROM embedding WHERE chunk_id = :c"), {"c": chunk_id}
        )
    ).scalar_one()
    assert new_vector != original_vector


async def test_upsert_document_reconciliation_does_not_touch_chunks_of_other_documents_between_by_id(
    session: AsyncSession,
) -> None:
    """El objetivo del reconciliado tiene `id` determinista ENTRE otros dos documentos con su
    propio chunk — descarta un filtro `document_id` por rango (`<=`/`>=`) o por identidad
    (`is not`) tanto al leer los chunks existentes (línea 91) como al borrar los obsoletos
    (línea 101): cualquiera de esos filtros mal aplicado borraría o mezclaría chunks ajenos."""
    await _seed_raw_document_with_chunk(
        session, doc_id=uuid.UUID(int=10), uc_id="uc-a-low", ordinal=0, content="bajo"
    )
    await _seed_raw_document_with_chunk(
        session, doc_id=uuid.UUID(int=50), uc_id="uc-m-target", ordinal=0, content="objetivo"
    )
    await _seed_raw_document_with_chunk(
        session, doc_id=uuid.UUID(int=90), uc_id="uc-z-high", ordinal=0, content="alto"
    )
    await session.commit()
    writer = SqlAlchemyKBIndexWriter(session)
    target = _draft(uc_id="uc-m-target")

    report = await writer.upsert_document(target, [])  # chunks=[] → reconcilia TODO lo existente
    await session.commit()

    assert report.chunks_deleted == 1
    assert await _chunk_count(session, uuid.UUID(int=50)) == 0
    assert await _chunk_count(session, uuid.UUID(int=10)) == 1
    assert await _chunk_count(session, uuid.UUID(int=90)) == 1


async def test_upsert_document_updates_only_the_targets_embedding_when_others_exist(
    session: AsyncSession,
) -> None:
    """Con el embedding de OTRO documento también presente en la tabla, descarta un filtro
    `Embedding.chunk_id` por identidad (`is not` en vez de `==`, línea 137): emparejaría de más
    (`MultipleResultsFound`) o tocaría el embedding equivocado."""
    writer = SqlAlchemyKBIndexWriter(session)
    target = _draft()
    other = _draft()
    await writer.upsert_document(target, [_chunk(0, vector=_vector(0.1))])
    await writer.upsert_document(other, [_chunk(0, vector=_vector(0.2))])
    await session.commit()
    other_doc_id = (
        await session.execute(
            text("SELECT id FROM kb_document WHERE uc_id = :uc_id"), {"uc_id": other.uc_id}
        )
    ).scalar_one()
    other_chunk_id = (
        await session.execute(
            text("SELECT id FROM kb_chunk WHERE document_id = :d AND ordinal = 0"),
            {"d": other_doc_id},
        )
    ).scalar_one()
    other_original_vector = (
        await session.execute(
            text("SELECT vector FROM embedding WHERE chunk_id = :c"), {"c": other_chunk_id}
        )
    ).scalar_one()

    await writer.upsert_document(
        target, [_chunk(0, content="objetivo cambiado", vector=_vector(0.9))]
    )
    await session.commit()

    other_vector_after = (
        await session.execute(
            text("SELECT vector FROM embedding WHERE chunk_id = :c"), {"c": other_chunk_id}
        )
    ).scalar_one()
    assert other_vector_after == other_original_vector
    assert await _embedding_count(session, other_chunk_id) == 1


async def test_upsert_document_continues_processing_remaining_chunks_after_a_vector_none_chunk(
    session: AsyncSession,
) -> None:
    """Un `ordinal` con `vector=None` (no lo toques) seguido de OTRO con vector real — descarta un
    `continue` mutado a `break` (línea 133): saltaría el resto del batch y el segundo chunk se
    quedaría sin re-embeber."""
    writer = SqlAlchemyKBIndexWriter(session)
    draft = _draft()
    await writer.upsert_document(
        draft, [_chunk(0, vector=_vector(0.1)), _chunk(1, vector=_vector(0.2))]
    )
    await session.commit()
    doc_id = (
        await session.execute(
            text("SELECT id FROM kb_document WHERE uc_id = :uc_id"), {"uc_id": draft.uc_id}
        )
    ).scalar_one()
    chunk_1_id = (
        await session.execute(
            text("SELECT id FROM kb_chunk WHERE document_id = :d AND ordinal = 1"), {"d": doc_id}
        )
    ).scalar_one()
    original_vector_1 = (
        await session.execute(
            text("SELECT vector FROM embedding WHERE chunk_id = :c"), {"c": chunk_1_id}
        )
    ).scalar_one()

    await writer.upsert_document(
        draft,
        [_chunk(0, vector=None), _chunk(1, content="chunk 1 editado", vector=_vector(0.9))],
    )
    await session.commit()

    updated_vector_1 = (
        await session.execute(
            text("SELECT vector FROM embedding WHERE chunk_id = :c"), {"c": chunk_1_id}
        )
    ).scalar_one()
    assert updated_vector_1 != original_vector_1


async def test_upsert_document_with_updated_field_persists_it(session: AsyncSession) -> None:
    writer = SqlAlchemyKBIndexWriter(session)
    draft = _draft(updated=datetime(2026, 1, 1, tzinfo=UTC))
    await writer.upsert_document(draft, [_chunk(0)])
    await session.commit()

    stored_updated = (
        await session.execute(
            text("SELECT updated FROM kb_document WHERE uc_id = :uc_id"), {"uc_id": draft.uc_id}
        )
    ).scalar_one()
    assert stored_updated == datetime(2026, 1, 1, tzinfo=UTC)


# ── delete_by_uc_ids ──


async def test_delete_by_uc_ids_removes_document_chunks_and_embeddings_in_cascade(
    session: AsyncSession,
) -> None:
    writer = SqlAlchemyKBIndexWriter(session)
    draft = _draft()
    await writer.upsert_document(draft, [_chunk(0)])
    await session.commit()

    deleted = await writer.delete_by_uc_ids({draft.uc_id})
    await session.commit()

    assert deleted == 1
    remaining_docs = (
        await session.execute(
            text("SELECT count(*) FROM kb_document WHERE uc_id = :uc_id"), {"uc_id": draft.uc_id}
        )
    ).scalar_one()
    remaining_chunks = (await session.execute(text("SELECT count(*) FROM kb_chunk"))).scalar_one()
    remaining_embeddings = (
        await session.execute(text("SELECT count(*) FROM embedding"))
    ).scalar_one()
    assert remaining_docs == 0
    assert remaining_chunks == 0
    assert remaining_embeddings == 0


async def test_delete_by_uc_ids_with_an_empty_set_does_not_fail_and_deletes_nothing(
    session: AsyncSession,
) -> None:
    writer = SqlAlchemyKBIndexWriter(session)
    draft = _draft()
    await writer.upsert_document(draft, [_chunk(0)])
    await session.commit()

    deleted = await writer.delete_by_uc_ids(set())

    assert deleted == 0
    remaining = (await session.execute(text("SELECT count(*) FROM kb_document"))).scalar_one()
    assert remaining == 1


async def test_delete_by_uc_ids_only_removes_the_requested_documents(
    session: AsyncSession,
) -> None:
    """Un segundo documento (no pedido) SIGUE existiendo — descarta un filtro que borre de más."""
    writer = SqlAlchemyKBIndexWriter(session)
    target = _draft()
    other = _draft()
    await writer.upsert_document(target, [_chunk(0)])
    await writer.upsert_document(other, [_chunk(0)])
    await session.commit()

    deleted = await writer.delete_by_uc_ids({target.uc_id})
    await session.commit()

    assert deleted == 1
    remaining_uc_ids = await writer.existing_uc_ids()
    assert remaining_uc_ids == {other.uc_id}


# ── existing_chunk_contents / existing_uc_ids ──


async def test_existing_chunk_contents_reflects_what_is_persisted(session: AsyncSession) -> None:
    writer = SqlAlchemyKBIndexWriter(session)
    draft = _draft()
    await writer.upsert_document(draft, [_chunk(0, content="uno"), _chunk(1, content="dos")])
    await session.commit()

    contents = await writer.existing_chunk_contents(draft.uc_id)

    assert contents == {0: "uno", 1: "dos"}


async def test_existing_chunk_contents_for_a_nonexistent_uc_id_returns_empty_dict(
    session: AsyncSession,
) -> None:
    writer = SqlAlchemyKBIndexWriter(session)

    assert await writer.existing_chunk_contents("no-existe") == {}


async def _seed_raw_document_with_chunk(
    session: AsyncSession, *, doc_id: uuid.UUID, uc_id: str, ordinal: int, content: str
) -> None:
    """Inserta un `kb_document`+`kb_chunk` con `id` DETERMINISTA (SQL crudo, sin pasar por el
    puerto — `upsert_document` genera sus propios `uuid.uuid4()` y no deja fijar el `id`)."""
    await session.execute(
        text(
            "INSERT INTO kb_document (id, uc_id, domain, package, estado, title, source_url) "
            "VALUES (:id, :uc_id, 'authoring-and-editor', 'syntax-cx', 'active', 'T', 'x')"
        ),
        {"id": doc_id, "uc_id": uc_id},
    )
    await session.execute(
        text(
            "INSERT INTO kb_chunk (id, document_id, section_type, content, token_count, ordinal) "
            "VALUES (:cid, :did, 'comportamiento', :content, 1, :ordinal)"
        ),
        {"cid": uuid.uuid4(), "did": doc_id, "content": content, "ordinal": ordinal},
    )


async def test_existing_chunk_contents_does_not_leak_chunks_from_a_document_between_others_by_id(
    session: AsyncSession,
) -> None:
    """3 documentos con `id` (UUID) y `uc_id` (string) DETERMINISTAS, el objetivo entre los otros
    dos en ambos órdenes — descarta un filtro que compare por rango (`<=`/`>=`) o por identidad
    (`is not`) en vez de por igualdad exacta, tanto en `uc_id` (línea 52) como en `document_id`
    (línea 60)."""
    await _seed_raw_document_with_chunk(
        session, doc_id=uuid.UUID(int=10), uc_id="uc-a-low", ordinal=100, content="contenido bajo"
    )
    await _seed_raw_document_with_chunk(
        session,
        doc_id=uuid.UUID(int=50),
        uc_id="uc-m-target",
        ordinal=0,
        content="contenido objetivo",
    )
    await _seed_raw_document_with_chunk(
        session, doc_id=uuid.UUID(int=90), uc_id="uc-z-high", ordinal=200, content="contenido alto"
    )
    await session.commit()

    writer = SqlAlchemyKBIndexWriter(session)
    contents = await writer.existing_chunk_contents("uc-m-target")

    assert contents == {0: "contenido objetivo"}


async def test_existing_uc_ids_reflects_the_persisted_corpus(session: AsyncSession) -> None:
    writer = SqlAlchemyKBIndexWriter(session)
    a, b = _draft(), _draft()
    await writer.upsert_document(a, [_chunk(0)])
    await writer.upsert_document(b, [_chunk(0)])
    await session.commit()

    assert await writer.existing_uc_ids() == {a.uc_id, b.uc_id}


async def test_existing_uc_ids_with_empty_corpus_returns_empty_set(session: AsyncSession) -> None:
    writer = SqlAlchemyKBIndexWriter(session)

    assert await writer.existing_uc_ids() == set()


# ── errores de infraestructura ──


@pytest_asyncio.fixture
async def broken_session() -> AsyncIterator[AsyncSession]:
    """Sesión sobre un engine apuntando a un puerto sin nadie escuchando: la primera query real
    falla en infra (no en validación de datos) — para probar que cada método envuelve en `PortError`."""
    broken_engine = create_async_engine("postgresql+asyncpg://x:y@localhost:59999/x")
    try:
        async with async_sessionmaker(broken_engine, expire_on_commit=False)() as s:
            yield s
    finally:
        await broken_engine.dispose()


async def test_existing_uc_ids_infrastructure_failure_propagates_wrapped_in_port_error(
    broken_session: AsyncSession,
) -> None:
    writer = SqlAlchemyKBIndexWriter(broken_session)

    with pytest.raises(PortError):
        await writer.existing_uc_ids()


async def test_existing_chunk_contents_infrastructure_failure_propagates_wrapped_in_port_error(
    broken_session: AsyncSession,
) -> None:
    writer = SqlAlchemyKBIndexWriter(broken_session)

    with pytest.raises(PortError):
        await writer.existing_chunk_contents("cualquier-uc-id")


async def test_upsert_document_infrastructure_failure_propagates_wrapped_in_port_error(
    broken_session: AsyncSession,
) -> None:
    writer = SqlAlchemyKBIndexWriter(broken_session)

    with pytest.raises(PortError):
        await writer.upsert_document(_draft(), [_chunk(0)])


async def test_delete_by_uc_ids_infrastructure_failure_propagates_wrapped_in_port_error(
    broken_session: AsyncSession,
) -> None:
    writer = SqlAlchemyKBIndexWriter(broken_session)

    with pytest.raises(PortError):
        await writer.delete_by_uc_ids({"algún-uc-id"})


async def test_try_acquire_ingestion_lock_infrastructure_failure_propagates_wrapped_in_port_error(
    broken_session: AsyncSession,
) -> None:
    writer = SqlAlchemyKBIndexWriter(broken_session)

    with pytest.raises(PortError):
        await writer.try_acquire_ingestion_lock()


# ── try_acquire_ingestion_lock ──


async def test_try_acquire_ingestion_lock_returns_true_when_nobody_else_holds_it(
    session: AsyncSession,
) -> None:
    writer = SqlAlchemyKBIndexWriter(session)

    assert await writer.try_acquire_ingestion_lock() is True


async def test_try_acquire_ingestion_lock_returns_false_when_another_session_holds_it(
    superuser_engine: AsyncEngine,
) -> None:
    maker = async_sessionmaker(superuser_engine, expire_on_commit=False)
    holder = maker()
    contender = maker()
    try:
        holder_writer = SqlAlchemyKBIndexWriter(holder)
        assert await holder_writer.try_acquire_ingestion_lock() is True

        contender_writer = SqlAlchemyKBIndexWriter(contender)
        assert await contender_writer.try_acquire_ingestion_lock() is False
    finally:
        await holder.close()
        await contender.close()


# ── search (tarea backend-kb-retriever-04) ──────────────────────────────────────
#
# Vectores DETERMINISTAS de dimensión real para que el orden por coseno sea predecible: se usan
# vectores "eje" (un 1.0 en una posición, 0.0 en el resto), cuya similitud coseno se conoce de
# antemano — e0·e0 = 1, e0·e1 = 0, e0·(-e0) = -1. Un `[v] * 1536` no serviría: todos esos vectores son
# proporcionales entre sí, así que su coseno es SIEMPRE 1 y cualquier orden pasaría el test.

_EMBEDDING_MODEL = "text-embedding-3-small"


def _axis(index: int, sign: float = 1.0) -> list[float]:
    """Vector unitario sobre el eje `index` (opcionalmente invertido con `sign=-1.0`)."""
    vector = [0.0] * EMBEDDING_DIM_LITERAL
    vector[index] = sign
    return vector


async def _seed(
    session: AsyncSession,
    writer: SqlAlchemyKBIndexWriter,
    uc_id: str,
    vector: list[float] | None,
    *,
    domain: KbDomain = KbDomain.authoring_and_editor,
    package: Package = Package.syntax_cx,
    estado: KbEstado = KbEstado.active,
    content: str = "contenido del chunk",
    section_type: str = "comportamiento",
    model: str = _EMBEDDING_MODEL,
) -> None:
    """Persiste un documento de un solo chunk. `vector=None` deja el chunk SIN fila de `embedding`."""
    await writer.upsert_document(
        _draft(uc_id=uc_id, domain=domain, package=package, estado=estado),
        [
            ChunkWrite(
                ordinal=0,
                section_type=section_type,
                content=content,
                token_count=3,
                vector=vector,
                model=model,
            )
        ],
    )
    await session.commit()


def _searcher(session: AsyncSession) -> SqlAlchemyKBIndexWriter:
    """Adaptador construido para el camino de LECTURA (necesita saber qué modelo compara)."""
    return SqlAlchemyKBIndexWriter(session, embedding_model=_EMBEDDING_MODEL)


async def test_search_orders_results_by_cosine_relevance(session: AsyncSession) -> None:
    """CU-BE-12 · *La búsqueda devuelve documentos ordenados por relevancia* — orden por coseno.

    Similitudes conocidas frente a la consulta `e0`: `UC-EXACTO` = 1, `UC-MEDIO` ≈ 0.707,
    `UC-ORTOGONAL` = 0.
    """
    writer = SqlAlchemyKBIndexWriter(session)
    medio = _axis(0)
    medio[1] = 1.0
    await _seed(session, writer, "UC-ORTOGONAL", _axis(1))
    await _seed(session, writer, "UC-EXACTO", _axis(0))
    await _seed(session, writer, "UC-MEDIO", medio)

    hits = await _searcher(session).search(_axis(0), top_k=10)

    assert [h.uc_id for h in hits] == ["UC-EXACTO", "UC-MEDIO", "UC-ORTOGONAL"]
    assert hits[0].score > hits[1].score > hits[2].score


async def test_search_returns_the_chunk_text_and_document_metadata(session: AsyncSession) -> None:
    """Cada `Hit` trae el texto COMPLETO del chunk (`content`, para el snippet de `-06` y el prompt de
    `generate`) más los metadatos de su documento."""
    writer = SqlAlchemyKBIndexWriter(session)
    await _seed(
        session,
        writer,
        "UC-1",
        _axis(0),
        domain=KbDomain.media_and_dam,
        package=Package.syntax_api,
        estado=KbEstado.draft,
        content="El editor permite subir vídeos de hasta 2 GB.",
        section_type="reglas",
    )

    hit = (await _searcher(session).search(_axis(0), top_k=5))[0]

    assert hit.uc_id == "UC-1"
    assert hit.content == "El editor permite subir vídeos de hasta 2 GB."
    assert hit.section_type == "reglas"
    assert hit.title == "Título"
    assert hit.domain is KbDomain.media_and_dam
    assert hit.estado is KbEstado.draft
    assert hit.chunk_id is not None


async def test_search_clamps_a_negative_similarity_to_zero(session: AsyncSession) -> None:
    """CU-BE-12 · *Una similitud negativa no invierte el orden de los resultados* (hallazgo C1).

    `1 - cosine_distance` ∈ `[-1, 1]`. Sin el clamp, un score negativo haría que el boost
    multiplicativo de `-05` (`score * (1 + w)`) **penalizara** al documento en vez de premiarlo,
    invirtiendo su orden frente a un `draft`. Un coseno negativo es "menos relacionado que el azar":
    no hay ranking que preservar por debajo de 0.
    """
    writer = SqlAlchemyKBIndexWriter(session)
    await _seed(session, writer, "UC-OPUESTO", _axis(0, sign=-1.0))

    hits = await _searcher(session).search(_axis(0), top_k=5)

    assert hits[0].uc_id == "UC-OPUESTO"
    assert hits[0].score == 0.0


async def test_search_scores_stay_within_the_raw_zero_one_range(session: AsyncSession) -> None:
    """`Hit.score` es la similitud CRUDA acotada a `[0, 1]`: sin el peso de `estado`, que solo se
    aplica al producir el `KBSearchHit` (hallazgo C2 — si viajara aquí, el futuro `confidence.py`
    contaría `estado` dos veces)."""
    writer = SqlAlchemyKBIndexWriter(session)
    await _seed(session, writer, "UC-ACTIVE", _axis(0), estado=KbEstado.active)
    await _seed(session, writer, "UC-DRAFT", _axis(0), estado=KbEstado.draft)

    hits = await _searcher(session).search(_axis(0), top_k=5)

    assert all(0.0 <= h.score <= 1.0 for h in hits)
    assert {h.score for h in hits} == {1.0}


async def test_search_filters_by_domain(session: AsyncSession) -> None:
    """CU-BE-12 · *Los filtros acotan la búsqueda*."""
    writer = SqlAlchemyKBIndexWriter(session)
    await _seed(session, writer, "UC-MEDIA", _axis(0), domain=KbDomain.media_and_dam)
    await _seed(session, writer, "UC-FORMS", _axis(0), domain=KbDomain.forms_and_submissions)
    await _seed(session, writer, "UC-SEO", _axis(0), domain=KbDomain.seo_sitemaps_and_edge)

    hits = await _searcher(session).search(_axis(0), top_k=10, domain=KbDomain.media_and_dam)

    assert [h.uc_id for h in hits] == ["UC-MEDIA"]


async def test_search_without_domain_filter_searches_the_whole_corpus(
    session: AsyncSession,
) -> None:
    """CU-BE-05 · *Ticket no clasificable usa fallback sin filtro de dominio* — `domain=None` NO
    filtra: el fallback recupera del corpus entero en vez de devolver vacío."""
    writer = SqlAlchemyKBIndexWriter(session)
    await _seed(session, writer, "UC-MEDIA", _axis(0), domain=KbDomain.media_and_dam)
    await _seed(session, writer, "UC-FORMS", _axis(0), domain=KbDomain.forms_and_submissions)

    hits = await _searcher(session).search(_axis(0), top_k=10, domain=None)

    assert {h.uc_id for h in hits} == {"UC-MEDIA", "UC-FORMS"}


async def test_search_filters_by_package(session: AsyncSession) -> None:
    """El package filtrado tiene vecinos a AMBOS lados en orden alfabético (`syntax-api` antes,
    `syntax-render` después): con un solo vecino por un lado, una comparación de desigualdad daría el
    mismo resultado que la de igualdad y el filtro parecería correcto estando roto."""
    writer = SqlAlchemyKBIndexWriter(session)
    await _seed(session, writer, "UC-API", _axis(0), package=Package.syntax_api)
    await _seed(session, writer, "UC-CX", _axis(0), package=Package.syntax_cx)
    await _seed(session, writer, "UC-RENDER", _axis(0), package=Package.syntax_render)

    hits = await _searcher(session).search(_axis(0), top_k=10, package=Package.syntax_cx)

    assert [h.uc_id for h in hits] == ["UC-CX"]


async def test_search_with_an_explicit_estado_filters_it_hard(session: AsyncSession) -> None:
    """CU-BE-12 · *Pedir un estado concreto sí lo filtra* — RN-2 describe DOS comportamientos (peso
    por defecto, filtro duro opt-in) y solo el peso tenía Gherkin. Aquí se fija el filtro duro."""
    writer = SqlAlchemyKBIndexWriter(session)
    await _seed(session, writer, "UC-DRAFT", _axis(0), estado=KbEstado.draft)
    await _seed(session, writer, "UC-ACTIVE", _axis(0), estado=KbEstado.active)

    hits = await _searcher(session).search(_axis(0), top_k=10, estado=KbEstado.active)

    assert [h.uc_id for h in hits] == ["UC-ACTIVE"]


async def test_search_without_estado_filter_keeps_drafts(session: AsyncSession) -> None:
    """`estado` es **opt-in** (ADR-0010): sin pedirlo, los `draft` participan — son el 81% del corpus
    real y filtrarlos por defecto vaciaría el retrieval."""
    writer = SqlAlchemyKBIndexWriter(session)
    await _seed(session, writer, "UC-DRAFT", _axis(0), estado=KbEstado.draft)
    await _seed(session, writer, "UC-ACTIVE", _axis(0), estado=KbEstado.active)

    hits = await _searcher(session).search(_axis(0), top_k=10)

    assert {h.uc_id for h in hits} == {"UC-DRAFT", "UC-ACTIVE"}


async def test_search_combines_filters_by_conjunction(session: AsyncSession) -> None:
    """CU-BE-12 · *Los filtros combinados acotan por conjunción* — los tres a la vez: un documento que
    cumple dos de tres NO entra."""
    writer = SqlAlchemyKBIndexWriter(session)
    await _seed(
        session,
        writer,
        "UC-MATCH",
        _axis(0),
        domain=KbDomain.media_and_dam,
        package=Package.syntax_api,
        estado=KbEstado.draft,
    )
    await _seed(
        session,
        writer,
        "UC-OTRO-DOMINIO",
        _axis(0),
        domain=KbDomain.forms_and_submissions,
        package=Package.syntax_api,
        estado=KbEstado.draft,
    )
    await _seed(
        session,
        writer,
        "UC-OTRO-PACKAGE",
        _axis(0),
        domain=KbDomain.media_and_dam,
        package=Package.syntax_render,
        estado=KbEstado.draft,
    )
    await _seed(
        session,
        writer,
        "UC-OTRO-ESTADO",
        _axis(0),
        domain=KbDomain.media_and_dam,
        package=Package.syntax_api,
        estado=KbEstado.active,
    )

    hits = await _searcher(session).search(
        _axis(0),
        top_k=10,
        domain=KbDomain.media_and_dam,
        package=Package.syntax_api,
        estado=KbEstado.draft,
    )

    assert [h.uc_id for h in hits] == ["UC-MATCH"]


async def test_search_honours_top_k(session: AsyncSession) -> None:
    writer = SqlAlchemyKBIndexWriter(session)
    for i in range(5):
        await _seed(session, writer, f"UC-{i}", _axis(0))

    hits = await _searcher(session).search(_axis(0), top_k=2)

    assert len(hits) == 2


async def test_search_asking_for_more_results_than_exist_returns_only_those(
    session: AsyncSession,
) -> None:
    """CU-BE-12 · *Pedir más resultados de los que existen devuelve solo los que hay* — el resultado
    no se rellena con documentos irrelevantes."""
    writer = SqlAlchemyKBIndexWriter(session)
    await _seed(session, writer, "UC-1", _axis(0))
    await _seed(session, writer, "UC-2", _axis(0))

    hits = await _searcher(session).search(_axis(0), top_k=50)

    assert len(hits) == 2


async def test_search_on_an_empty_corpus_returns_no_hits(session: AsyncSession) -> None:
    """CU-BE-12 · *Una búsqueda sin coincidencias devuelve vacío, no un error* (a nivel de adaptador)."""
    assert await _searcher(session).search(_axis(0), top_k=10) == []


async def test_search_only_considers_vectors_of_the_configured_model(
    session: AsyncSession,
) -> None:
    """CU-BE-12 · *Solo participan los vectores del modelo de embeddings configurado* (hallazgo A3).

    Comparar vectores generados por dos modelos distintos cruza espacios vectoriales distintos: el
    resultado es **basura perfectamente ordenada**, sin ninguna señal de error. El del otro modelo se
    siembran con el vector MÁS parecido a la consulta para que, de colarse, salieran los primeros, y
    uno ordena ANTES del modelo configurado y otro DESPUÉS: así el filtro no puede confundirse con una
    comparación de orden.
    """
    writer = SqlAlchemyKBIndexWriter(session)
    await _seed(session, writer, "UC-MODELO-POSTERIOR", _axis(0), model="text-embedding-ada-002")
    await _seed(session, writer, "UC-MODELO-ANTERIOR", _axis(0), model="a-modelo-legacy")
    lejano = _axis(0)
    lejano[1] = 1.0
    await _seed(session, writer, "UC-MODELO-BUENO", lejano, model=_EMBEDDING_MODEL)

    hits = await _searcher(session).search(_axis(0), top_k=10)

    assert [h.uc_id for h in hits] == ["UC-MODELO-BUENO"]


async def test_search_ignores_chunks_without_an_embedding(session: AsyncSession) -> None:
    """CU-BE-12 · *Un chunk sin embedding no participa ni rompe la búsqueda* (hallazgo A4).

    Caso real: `ChunkWrite.vector=None` sobre un chunk **nuevo** no crea fila de `embedding`. El
    `JOIN` lo excluye — comportamiento **decidido**, no accidental, y por eso tiene test.
    """
    writer = SqlAlchemyKBIndexWriter(session)
    await _seed(session, writer, "UC-SIN-VECTOR", None)
    await _seed(session, writer, "UC-CON-VECTOR", _axis(0))

    hits = await _searcher(session).search(_axis(0), top_k=10)

    assert [h.uc_id for h in hits] == ["UC-CON-VECTOR"]


async def test_search_without_a_configured_embedding_model_fails_explicitly(
    session: AsyncSession,
) -> None:
    """Un adaptador construido solo con `session` (el camino de INGESTIÓN) no sabe qué modelo comparar:
    `search` falla explícito en vez de comparar contra todo el corpus mezclando espacios vectoriales."""
    writer = SqlAlchemyKBIndexWriter(session)

    with pytest.raises(PortError):
        await writer.search(_axis(0), top_k=5)


async def test_search_infrastructure_failure_propagates_wrapped_in_port_error(
    broken_session: AsyncSession,
) -> None:
    """CU-BE-12 · *Un fallo de la base de datos no se disfraza de KB vacía* — sobre el `JOIN` de
    `search`: `PortError` (→ 502), nunca una lista vacía."""
    writer = SqlAlchemyKBIndexWriter(broken_session, embedding_model=_EMBEDDING_MODEL)

    with pytest.raises(PortError):
        await writer.search(_axis(0), top_k=5)
