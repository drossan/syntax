"""Tests de integración de `PgVectorStore.search` (tarea `backend-kb-retriever-06`).

Postgres real (KB es global, sin RLS) + **doble del puerto de embeddings**: sin red y sin clave de
OpenAI. Aquí se cierra la traducción entre los dos mundos — del retriever (chunks con `Hit`) al del
router (documentos con `KBSearchHit`) — aplicando ventana, dedup y paginación.

Escenarios de `CU-BE-12` que materializa: *La búsqueda devuelve documentos ordenados por relevancia*,
*Un documento con varias secciones relevantes aparece una sola vez*, *El resultado incluye un fragmento
de la sección que lo justifica*, *Una búsqueda sin coincidencias devuelve vacío, no un error*, *Página
solicitada según su posición respecto a la ventana* y *Un fallo del proveedor de embeddings no se
disfraza de KB vacía* (en la capa del adaptador: que `search` no se trague el `PortError`).
"""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from app.core.config import Settings
from app.domain.entities.enums import KbDomain, KbEstado, Package
from app.domain.errors import PortError
from app.domain.ports.vector import ChunkWrite, KBDocumentDraft
from app.infra.db.models.kb import EMBEDDING_DIM_LITERAL
from app.infra.vector import SqlAlchemyKBIndexWriter
from app.infra.vectorstore.pgvector import SNIPPET_MAX_CHARS, PgVectorStore
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_TRUNCATE_TABLES = "TRUNCATE embedding, kb_chunk, kb_document RESTART IDENTITY CASCADE"
_EMBEDDING_MODEL = "text-embedding-3-small"


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


@pytest_asyncio.fixture
async def broken_session() -> AsyncIterator[AsyncSession]:
    broken_engine = create_async_engine("postgresql+asyncpg://x:y@localhost:59999/x")
    try:
        async with async_sessionmaker(broken_engine, expire_on_commit=False)() as s:
            yield s
    finally:
        await broken_engine.dispose()


def _axis(index: int, sign: float = 1.0) -> list[float]:
    """Vector unitario sobre un eje: similitudes coseno conocidas de antemano."""
    vector = [0.0] * EMBEDDING_DIM_LITERAL
    vector[index] = sign
    return vector


class FakeEmbeddingModel:
    """Doble del puerto de embeddings: devuelve un vector fijo o levanta el error configurado."""

    def __init__(self, vector: list[float] | None = None, error: Exception | None = None) -> None:
        self._vector = vector if vector is not None else _axis(0)
        self._error = error
        self.queries: list[str] = []

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise AssertionError("la búsqueda no embebe documentos, solo la consulta")

    async def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        if self._error is not None:
            raise self._error
        return self._vector


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, jwt_secret="x", **overrides)


def _store(
    session: AsyncSession,
    embeddings: FakeEmbeddingModel | None = None,
    **setting_overrides: object,
) -> PgVectorStore:
    return PgVectorStore(
        session,
        embeddings=embeddings or FakeEmbeddingModel(),
        settings=_settings(**setting_overrides),
    )


async def _seed(
    session: AsyncSession,
    uc_id: str,
    chunks: list[tuple[str, str, list[float]]],
    *,
    domain: KbDomain = KbDomain.authoring_and_editor,
    package: Package = Package.syntax_cx,
    estado: KbEstado = KbEstado.draft,
    title: str = "Título",
) -> None:
    """Persiste un documento con sus chunks: cada uno es `(section_type, content, vector)`."""
    writer = SqlAlchemyKBIndexWriter(session)
    await writer.upsert_document(
        KBDocumentDraft(
            uc_id=uc_id,
            domain=domain,
            package=package,
            estado=estado,
            title=title,
            source_url=f"packages/x/docs/aiup/use-cases/{uc_id}.md",
        ),
        [
            ChunkWrite(
                ordinal=i,
                section_type=section_type,
                content=content,
                token_count=len(content.split()),
                vector=vector,
                model=_EMBEDDING_MODEL,
            )
            for i, (section_type, content, vector) in enumerate(chunks)
        ],
    )
    await session.commit()


# ── camino feliz y orden ──


async def test_search_returns_documents_ordered_by_relevance(session: AsyncSession) -> None:
    """CU-BE-12 · *La búsqueda devuelve documentos ordenados por relevancia* (end-to-end del adaptador)."""
    medio = _axis(0)
    medio[1] = 1.0
    await _seed(session, "UC-LEJOS", [("comportamiento", "texto", _axis(1))])
    await _seed(session, "UC-CERCA", [("comportamiento", "texto", _axis(0))])
    await _seed(session, "UC-MEDIO", [("comportamiento", "texto", medio)])

    items, total = await _store(session).search("consulta")

    assert [h.uc_id for h in items] == ["UC-CERCA", "UC-MEDIO", "UC-LEJOS"]
    assert items[0].score > items[1].score > items[2].score
    assert total == 3


async def test_search_embeds_the_query_text(session: AsyncSession) -> None:
    """La consulta del usuario es lo que se embebe (una sola vez por búsqueda)."""
    embeddings = FakeEmbeddingModel()
    await _seed(session, "UC-1", [("comportamiento", "texto", _axis(0))])

    await _store(session, embeddings).search("cómo subo un vídeo")

    assert embeddings.queries == ["cómo subo un vídeo"]


async def test_search_returns_the_document_metadata(session: AsyncSession) -> None:
    await _seed(
        session,
        "UC-1",
        [("reglas", "texto del chunk", _axis(0))],
        domain=KbDomain.media_and_dam,
        estado=KbEstado.active,
        title="Subida de activos",
    )

    items, _ = await _store(session).search("consulta")

    assert items[0].uc_id == "UC-1"
    assert items[0].title == "Subida de activos"
    assert items[0].section_type == "reglas"
    assert items[0].domain is KbDomain.media_and_dam
    assert items[0].estado is KbEstado.active
    assert items[0].source_url == "packages/x/docs/aiup/use-cases/UC-1.md"


async def test_search_score_is_the_weighted_relevance_not_the_raw_cosine(
    session: AsyncSession,
) -> None:
    """RN-4 · el `score` que sale por la API es la **relevancia re-rankeada**: incorpora el peso de
    `estado` y por tanto **puede superar `1.0`**. No es una similitud coseno."""
    await _seed(session, "UC-ACTIVE", [("c", "t", _axis(0))], estado=KbEstado.active)

    items, _ = await _store(session, rag_estado_weight=0.05).search("consulta")

    assert items[0].score == pytest.approx(1.05)


async def test_search_ranks_an_active_over_an_equally_relevant_draft(
    session: AsyncSession,
) -> None:
    """El peso de `estado` se aplica de verdad en el camino HTTP (no solo en las funciones puras)."""
    await _seed(session, "UC-DRAFT", [("c", "t", _axis(0))], estado=KbEstado.draft)
    await _seed(session, "UC-ACTIVE", [("c", "t", _axis(0))], estado=KbEstado.active)

    items, _ = await _store(session, rag_estado_weight=0.05).search("consulta")

    assert [h.uc_id for h in items] == ["UC-ACTIVE", "UC-DRAFT"]


# ── dedup ──


async def test_search_returns_a_document_only_once(session: AsyncSession) -> None:
    """CU-BE-12 · *Un documento con varias secciones relevantes aparece una sola vez*, representado
    por su sección de mayor score."""
    peor = _axis(0)
    peor[1] = 1.0
    await _seed(
        session,
        "UC-1",
        [("peor", "sección peor", peor), ("mejor", "sección mejor", _axis(0))],
    )

    items, total = await _store(session).search("consulta")

    assert len(items) == 1
    assert items[0].section_type == "mejor"
    assert total == 1


async def test_search_total_counts_documents_not_chunks(session: AsyncSession) -> None:
    """RN-3 · `total` cuenta **documentos distintos**, no chunks: si contara chunks, el front pintaría
    páginas que no existen."""
    await _seed(session, "UC-1", [("a", "t", _axis(0)), ("b", "t", _axis(0)), ("c", "t", _axis(0))])
    await _seed(session, "UC-2", [("a", "t", _axis(0)), ("b", "t", _axis(0))])

    items, total = await _store(session).search("consulta")

    assert len(items) == 2
    assert total == 2


# ── snippet ──


async def test_search_includes_a_snippet_from_the_winning_section(session: AsyncSession) -> None:
    """CU-BE-12 · *El resultado incluye un fragmento de la sección que lo justifica*."""
    await _seed(session, "UC-1", [("reglas", "El editor permite subir vídeos.", _axis(0))])

    items, _ = await _store(session).search("consulta")

    assert items[0].snippet == "El editor permite subir vídeos."


async def test_search_snippet_shows_the_beginning_of_the_section(session: AsyncSession) -> None:
    """RN-5 · el snippet es el **principio** de la sección, NO un extracto centrado en el término: la
    búsqueda es semántica y el chunk puede casar sin contener la palabra buscada."""
    content = "Primero lo primero. " + "relleno " * 200 + "término"
    await _seed(session, "UC-1", [("reglas", content, _axis(0))])

    items, _ = await _store(session).search("término")

    assert items[0].snippet.startswith("Primero lo primero.")
    assert "término" not in items[0].snippet


async def test_search_snippet_is_truncated_at_a_word_boundary_with_ellipsis(
    session: AsyncSession,
) -> None:
    """Cortado en un **límite de palabra**, no a mitad de una, y con elipsis para que se vea que hay
    más texto."""
    content = "palabra " * 200
    await _seed(session, "UC-1", [("reglas", content, _axis(0))])

    items, _ = await _store(session).search("consulta")

    snippet = items[0].snippet
    assert snippet.endswith("…")
    assert len(snippet) <= SNIPPET_MAX_CHARS + 1
    assert snippet.removesuffix("…").rstrip().endswith("palabra")


async def test_search_snippet_of_a_short_section_has_no_ellipsis(session: AsyncSession) -> None:
    """Un chunk más corto que el tope se sirve **entero**, sin elipsis: la elipsis promete texto que
    no existe."""
    await _seed(session, "UC-1", [("reglas", "Sección corta.", _axis(0))])

    items, _ = await _store(session).search("consulta")

    assert items[0].snippet == "Sección corta."
    assert "…" not in items[0].snippet


async def test_search_snippet_of_a_single_very_long_word_is_cut_hard(
    session: AsyncSession,
) -> None:
    """Frontera: una sola palabra larguísima **sin ningún espacio** antes del tope. No hay límite de
    palabra donde cortar, así que se corta en seco — preferible a devolver el chunk entero y romper la
    tarjeta del front, que no tiene `line-clamp`."""
    await _seed(session, "UC-1", [("reglas", "x" * 600, _axis(0))])

    items, _ = await _store(session).search("consulta")

    assert len(items[0].snippet) <= SNIPPET_MAX_CHARS + 1
    assert items[0].snippet.endswith("…")


async def test_search_snippet_of_an_empty_section_is_empty(session: AsyncSession) -> None:
    """Frontera: chunk vacío. `rag-ingestion.md` §2.1 declara **válido** un glosario vacío, así que no
    es un caso imposible: el snippet queda vacío, sin elipsis y sin reventar."""
    await _seed(session, "UC-1", [("reglas", "", _axis(0))])

    items, _ = await _store(session).search("consulta")

    assert items[0].snippet == ""


# ── filtros, vacío legítimo y paginación ──


async def test_search_filters_are_forwarded(session: AsyncSession) -> None:
    await _seed(session, "UC-MEDIA", [("c", "t", _axis(0))], domain=KbDomain.media_and_dam)
    await _seed(session, "UC-FORMS", [("c", "t", _axis(0))], domain=KbDomain.forms_and_submissions)

    items, total = await _store(session).search("consulta", domain=KbDomain.media_and_dam)

    assert [h.uc_id for h in items] == ["UC-MEDIA"]
    assert total == 1


async def test_search_without_matches_returns_empty_and_no_error(session: AsyncSession) -> None:
    """CU-BE-12 · *Una búsqueda sin coincidencias devuelve vacío, no un error* — el vacío
    **legítimo**, que es justo lo que hay que poder distinguir de un 502."""
    await _seed(session, "UC-1", [("c", "t", _axis(0))], domain=KbDomain.media_and_dam)

    items, total = await _store(session).search("consulta", domain=KbDomain.forms_and_submissions)

    assert items == []
    assert total == 0


async def test_search_on_an_empty_corpus_returns_empty(session: AsyncSession) -> None:
    items, total = await _store(session).search("consulta")

    assert items == []
    assert total == 0


async def test_search_first_page_returns_the_best_of_the_window(session: AsyncSession) -> None:
    """CU-BE-12 · *Página solicitada según su posición respecto a la ventana* — primera página."""
    for i in range(5):
        vector = _axis(0)
        vector[i + 1] = 1.0 - i * 0.1
        await _seed(session, f"UC-{i}", [("c", "t", vector)])

    items, total = await _store(session).search("consulta", page=1, page_size=2)

    assert len(items) == 2
    assert total == 5


async def test_search_last_page_with_data_returns_the_rest(session: AsyncSession) -> None:
    """*Página solicitada según su posición respecto a la ventana* — última con datos."""
    for i in range(5):
        await _seed(session, f"UC-{i}", [("c", "t", _axis(0))])

    items, total = await _store(session).search("consulta", page=3, page_size=2)

    assert len(items) == 1
    assert total == 5


async def test_search_page_beyond_the_window_is_empty_keeping_the_total(
    session: AsyncSession,
) -> None:
    """*Página solicitada según su posición respecto a la ventana* — más allá del rango: página vacía
    **conservando el `total`** (RN-3), no un total recalculado ni un error."""
    for i in range(3):
        await _seed(session, f"UC-{i}", [("c", "t", _axis(0))])

    items, total = await _store(session).search("consulta", page=9, page_size=10)

    assert items == []
    assert total == 3


async def test_search_paginates_without_repeating_or_losing_documents(
    session: AsyncSession,
) -> None:
    """Recorrer las páginas devuelve cada documento exactamente una vez."""
    for i in range(5):
        await _seed(session, f"UC-{i}", [("c", "t", _axis(0))])

    store = _store(session)
    seen: list[str] = []
    for page in (1, 2, 3):
        items, _ = await store.search("consulta", page=page, page_size=2)
        seen.extend(h.uc_id for h in items)

    assert sorted(seen) == ["UC-0", "UC-1", "UC-2", "UC-3", "UC-4"]


async def test_search_window_caps_the_number_of_documents(session: AsyncSession) -> None:
    """La **ventana** acota cuántos documentos entran en el resultado, y `total` cuenta los de la
    ventana — no el corpus (RN-3: una búsqueda ANN no tiene cardinalidad)."""
    for i in range(5):
        await _seed(session, f"UC-{i}", [("c", "t", _axis(0))])

    items, total = await _store(session, rag_search_window=2).search("consulta", page_size=100)

    assert len(items) == 2
    assert total == 2


async def test_search_overfetches_chunks_to_fill_the_window_with_documents(
    session: AsyncSession,
) -> None:
    """La ventana se mide en **DOCUMENTOS**, no en chunks: con `window=2` y documentos de 3 chunks
    cada uno, un `top_k` igual a la ventana traería chunks de un solo documento. El over-fetch
    (`window * chunks_per_doc`) es lo que evita que la página salga truncada.
    """
    for i in range(2):
        await _seed(
            session, f"UC-{i}", [("a", "t", _axis(0)), ("b", "t", _axis(0)), ("c", "t", _axis(0))]
        )

    items, total = await _store(session, rag_search_window=2, rag_chunks_per_doc=6).search(
        "consulta", page_size=100
    )

    assert {h.uc_id for h in items} == {"UC-0", "UC-1"}
    assert total == 2


# ── fallos de dependencias ──


async def test_search_does_not_swallow_an_embedding_provider_failure(
    session: AsyncSession,
) -> None:
    """CU-BE-12 · *Un fallo del proveedor de embeddings no se disfraza de KB vacía* — **en la capa del
    adaptador**: `search` no puede convertir el `PortError` en `([], 0)`, que el router serviría como
    una KB legítimamente vacía."""
    embeddings = FakeEmbeddingModel(error=PortError("proveedor caído"))

    with pytest.raises(PortError):
        await _store(session, embeddings).search("consulta")


async def test_search_does_not_swallow_a_database_failure(broken_session: AsyncSession) -> None:
    """CU-BE-12 · *Un fallo de la base de datos no se disfraza de KB vacía*."""
    with pytest.raises(PortError):
        await _store(broken_session).search("consulta")


# ── fronteras que destapó el gate de mutation ──


async def test_search_overfetch_is_large_enough_to_reach_the_last_document(
    session: AsyncSession,
) -> None:
    """El over-fetch es un **producto** (`window * chunks_per_doc`), y tiene que serlo.

    Tres documentos de 6 chunks cada uno, con similitud decreciente **por documento**: los del primero
    son los más cercanos, luego los del segundo, luego los del tercero. Con `window=3` y
    `chunks_per_doc=6` se piden 18 chunks y entran los 3 documentos. Cualquier `top_k` menor (una suma
    en vez de un producto daría 9) se queda sin llegar al tercero, y la ventana saldría **truncada**
    aunque hubiera sitio de sobra en ella.
    """
    for doc_index in range(3):
        chunks = []
        for chunk_index in range(6):
            vector = _axis(0)
            vector[1 + doc_index] = 0.2 * (doc_index + 1) + 0.01 * chunk_index
            chunks.append((f"s{chunk_index}", "texto", vector))
        await _seed(session, f"UC-{doc_index}", chunks)

    items, total = await _store(session, rag_search_window=3, rag_chunks_per_doc=6).search(
        "consulta", page_size=100
    )

    assert {h.uc_id for h in items} == {"UC-0", "UC-1", "UC-2"}
    assert total == 3


async def test_search_snippet_of_exactly_the_maximum_length_is_not_truncated(
    session: AsyncSession,
) -> None:
    """Frontera exacta: un contenido de **exactamente** `SNIPPET_MAX_CHARS` se sirve entero y **sin**
    elipsis — el tope es inclusivo. Un off-by-one aquí añadiría una elipsis que promete texto que no
    existe."""
    content = "a" * SNIPPET_MAX_CHARS
    await _seed(session, "UC-1", [("reglas", content, _axis(0))])

    items, _ = await _store(session).search("consulta")

    assert items[0].snippet == content
    assert "…" not in items[0].snippet


async def test_search_snippet_with_only_a_leading_space_is_not_emptied(
    session: AsyncSession,
) -> None:
    """Frontera: el único espacio del texto está en la **posición 0**.

    Cortar por ese "límite de palabra" dejaría el snippet **vacío** (solo la elipsis), tirando todo el
    contenido útil. Se prefiere el corte en seco: hay texto que mostrar.
    """
    await _seed(session, "UC-1", [("reglas", " " + "x" * 600, _axis(0))])

    items, _ = await _store(session).search("consulta")

    assert items[0].snippet != "…"
    assert "x" in items[0].snippet


async def test_search_raises_when_only_settings_is_missing(session: AsyncSession) -> None:
    """`embeddings` y `settings` son DOS requisitos independientes: falta cualquiera de los dos y
    `search` falla, no solo cuando faltan ambos a la vez."""
    store = PgVectorStore(session, embeddings=FakeEmbeddingModel())

    with pytest.raises(PortError):
        await store.search("consulta")


async def test_search_raises_when_only_embeddings_is_missing(session: AsyncSession) -> None:
    store = PgVectorStore(session, settings=_settings())

    with pytest.raises(PortError):
        await store.search("consulta")


async def test_search_defaults_to_the_contract_page_size(session: AsyncSession) -> None:
    """El tamaño de página por defecto es **20**, el del contrato compartido — sin cubrir hasta ahora
    en `search` (solo en `list_documents`, `-02`)."""
    for i in range(23):
        vector = _axis(0)
        vector[i + 1] = 0.5
        await _seed(session, f"UC-{i:02d}", [("c", "t", vector)])

    items, total = await _store(session, rag_search_window=100).search("consulta")

    assert len(items) == 20
    assert total == 23
