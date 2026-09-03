"""Tests unit de `app.rag.retriever` (tarea `backend-kb-retriever-05`).

**Con dobles de los dos puertos** (`EmbeddingModel` y `KBIndexWriter`): sin Postgres, sin red y sin
clave de OpenAI. `retrieve` es composición —embeber, buscar, re-rankear—, así que lo que hay que fijar
es **qué le pide a cada puerto** y **qué hace con lo que le devuelven**, no el SQL (eso es `-04`).
"""

import uuid

import pytest
from app.domain.entities.enums import KbDomain, KbEstado, Package
from app.domain.errors import PortError
from app.domain.ports.vector import Hit
from app.rag.retriever import Retriever


def _hit(uc_id: str, score: float, *, estado: KbEstado = KbEstado.draft) -> Hit:
    return Hit(
        uc_id=uc_id,
        chunk_id=uuid.uuid4(),
        section_type="comportamiento",
        title=f"Título de {uc_id}",
        source_url=f"packages/x/docs/aiup/use-cases/{uc_id}.md",
        domain=KbDomain.media_and_dam,
        estado=estado,
        score=score,
        content="contenido",
    )


class FakeEmbeddingModel:
    """Doble del puerto de embeddings: registra la consulta recibida y devuelve un vector fijo."""

    def __init__(self, vector: list[float] | None = None, error: Exception | None = None) -> None:
        self._vector = vector if vector is not None else [0.1, 0.2, 0.3]
        self._error = error
        self.queries: list[str] = []

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise AssertionError("el retriever no debe embeber documentos, solo la consulta")

    async def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        if self._error is not None:
            raise self._error
        return self._vector


class FakeIndex:
    """Doble del puerto de búsqueda: registra los argumentos y devuelve hits preparados."""

    def __init__(self, hits: list[Hit] | None = None, error: Exception | None = None) -> None:
        self._hits = hits or []
        self._error = error
        self.calls: list[dict[str, object]] = []

    async def search(
        self,
        query_vector: list[float],
        *,
        top_k: int,
        domain: KbDomain | None = None,
        package: Package | None = None,
        estado: KbEstado | None = None,
    ) -> list[Hit]:
        self.calls.append(
            {
                "query_vector": query_vector,
                "top_k": top_k,
                "domain": domain,
                "package": package,
                "estado": estado,
            }
        )
        if self._error is not None:
            raise self._error
        return self._hits


def _retriever(
    embeddings: FakeEmbeddingModel | None = None,
    index: FakeIndex | None = None,
    *,
    estado_weight: float = 0.05,
) -> tuple[Retriever, FakeEmbeddingModel, FakeIndex]:
    embeddings = embeddings or FakeEmbeddingModel()
    index = index or FakeIndex()
    return (
        Retriever(embeddings=embeddings, index=index, estado_weight=estado_weight),
        embeddings,
        index,
    )


async def test_retrieve_embeds_the_query_and_searches_with_that_vector() -> None:
    """El vector que se compara es el de la **consulta** (`embed_query`), no un `embed_documents`."""
    embeddings = FakeEmbeddingModel(vector=[0.9, 0.8])
    retriever, embeddings, index = _retriever(embeddings)

    await retriever.retrieve("cómo subo un vídeo", top_k=10)

    assert embeddings.queries == ["cómo subo un vídeo"]
    assert index.calls[0]["query_vector"] == [0.9, 0.8]


async def test_retrieve_passes_through_the_requested_top_k() -> None:
    """`retrieve` **recibe** el `top_k` y no lo calcula: el over-fetch de la ventana es un concepto del
    camino HTTP (`-06`) y el nodo `retrieve` del agente no pagina."""
    retriever, _, index = _retriever()

    await retriever.retrieve("consulta", top_k=42)

    assert index.calls[0]["top_k"] == 42


async def test_retrieve_forwards_the_filters() -> None:
    retriever, _, index = _retriever()

    await retriever.retrieve(
        "consulta",
        top_k=10,
        domain=KbDomain.forms_and_submissions,
        package=Package.syntax_api,
        estado=KbEstado.active,
    )

    assert index.calls[0]["domain"] is KbDomain.forms_and_submissions
    assert index.calls[0]["package"] is Package.syntax_api
    assert index.calls[0]["estado"] is KbEstado.active


async def test_retrieve_without_filters_does_not_invent_any() -> None:
    """CU-BE-05 · *Ticket no clasificable usa fallback sin filtro de dominio* — sin dominio, se busca
    en el corpus entero: el retriever no rellena filtros por su cuenta."""
    retriever, _, index = _retriever()

    await retriever.retrieve("consulta", top_k=10)

    assert index.calls[0]["domain"] is None
    assert index.calls[0]["package"] is None
    assert index.calls[0]["estado"] is None


async def test_retrieve_applies_the_estado_weight() -> None:
    """El re-ranking se aplica **aquí**, no en el adaptador: la salida trae el `weighted_score`."""
    index = FakeIndex([_hit("UC-DRAFT", 0.5), _hit("UC-ACTIVE", 0.5, estado=KbEstado.active)])
    retriever, _, _ = _retriever(index=index, estado_weight=0.2)

    ranked = await retriever.retrieve("consulta", top_k=10)

    assert [r.hit.uc_id for r in ranked] == ["UC-ACTIVE", "UC-DRAFT"]
    assert ranked[0].weighted_score == 0.6
    assert ranked[0].hit.score == 0.5


async def test_retrieve_with_zero_weight_keeps_the_pure_similarity_order() -> None:
    index = FakeIndex([_hit("UC-ACTIVE", 0.4, estado=KbEstado.active), _hit("UC-DRAFT", 0.7)])
    retriever, _, _ = _retriever(index=index, estado_weight=0.0)

    ranked = await retriever.retrieve("consulta", top_k=10)

    assert [r.hit.uc_id for r in ranked] == ["UC-DRAFT", "UC-ACTIVE"]


async def test_retrieve_does_not_deduplicate() -> None:
    """El camino del **agente** consume chunks **sin deduplicar** (D3a): varias secciones del mismo UC
    son varias piezas de contexto legítimas para el prompt. El dedup lo llama solo el adaptador HTTP."""
    index = FakeIndex([_hit("UC-1", 0.9), _hit("UC-1", 0.7), _hit("UC-2", 0.5)])
    retriever, _, _ = _retriever(index=index)

    ranked = await retriever.retrieve("consulta", top_k=10)

    assert [r.hit.uc_id for r in ranked] == ["UC-1", "UC-1", "UC-2"]


async def test_retrieve_on_an_empty_corpus_returns_empty() -> None:
    """CU-BE-12 · *Una búsqueda sin coincidencias devuelve vacío, no un error*."""
    retriever, _, _ = _retriever(index=FakeIndex([]))

    assert await retriever.retrieve("consulta", top_k=10) == []


async def test_retrieve_propagates_an_embedding_provider_failure() -> None:
    """CU-BE-12 · *Un fallo del proveedor de embeddings no se disfraza de KB vacía* — el `PortError`
    sube, no se convierte en una lista vacía."""
    embeddings = FakeEmbeddingModel(error=PortError("proveedor caído"))
    retriever, _, index = _retriever(embeddings)

    with pytest.raises(PortError):
        await retriever.retrieve("consulta", top_k=10)

    assert index.calls == []


async def test_retrieve_propagates_a_search_failure() -> None:
    """CU-BE-12 · *Un fallo de la base de datos no se disfraza de KB vacía*."""
    retriever, _, _ = _retriever(index=FakeIndex(error=PortError("BD caída")))

    with pytest.raises(PortError):
        await retriever.retrieve("consulta", top_k=10)


async def test_retrieve_does_not_call_the_provider_more_than_once() -> None:
    """Una búsqueda = una llamada al proveedor: cada llamada cuesta dinero (por eso también la caché
    de vectores quedó como follow-up documentado, no como algo que se optimice a ciegas)."""
    retriever, embeddings, _ = _retriever()

    await retriever.retrieve("consulta", top_k=10)

    assert len(embeddings.queries) == 1


# --- embed_query() / search() (backend-rag-domain-fallback-01, ADR-0019) ---
#
# `retrieve()` se parte en dos métodos públicos para que el nodo `retrieve` del agente pueda reutilizar
# el mismo vector en dos búsquedas (filtrada + sin filtro) sin pagar dos veces la llamada al proveedor de
# embeddings. Los tests de arriba (sobre `retrieve()`) siguen pasando sin cambios: verifican que el
# envoltorio no rompe nada.


async def test_embed_query_returns_the_vector_from_the_port() -> None:
    embeddings = FakeEmbeddingModel(vector=[0.4, 0.5])
    retriever, embeddings, _ = _retriever(embeddings)

    vector = await retriever.embed_query("cómo subo un vídeo")

    assert vector == [0.4, 0.5]
    assert embeddings.queries == ["cómo subo un vídeo"]


async def test_embed_query_propagates_a_provider_failure() -> None:
    embeddings = FakeEmbeddingModel(error=PortError("proveedor caído"))
    retriever, _, _ = _retriever(embeddings)

    with pytest.raises(PortError):
        await retriever.embed_query("consulta")


async def test_search_uses_a_precomputed_vector_without_embedding_again() -> None:
    """`search` no toca el puerto de embeddings — recibe el vector ya calculado. Es la garantía central
    del refactor (ADR-0019): reutilizar el vector entre la búsqueda filtrada y la sin filtro."""
    retriever, embeddings, index = _retriever()

    await retriever.search([0.9, 0.8], top_k=10)

    assert embeddings.queries == []
    assert index.calls[0]["query_vector"] == [0.9, 0.8]


async def test_search_forwards_top_k_and_filters() -> None:
    retriever, _, index = _retriever()

    await retriever.search(
        [0.1],
        top_k=42,
        domain=KbDomain.forms_and_submissions,
        package=Package.syntax_api,
        estado=KbEstado.active,
    )

    assert index.calls[0]["top_k"] == 42
    assert index.calls[0]["domain"] is KbDomain.forms_and_submissions
    assert index.calls[0]["package"] is Package.syntax_api
    assert index.calls[0]["estado"] is KbEstado.active


async def test_search_applies_the_estado_weight_same_as_retrieve() -> None:
    index = FakeIndex([_hit("UC-DRAFT", 0.5), _hit("UC-ACTIVE", 0.5, estado=KbEstado.active)])
    retriever, _, _ = _retriever(index=index, estado_weight=0.2)

    ranked = await retriever.search([0.1], top_k=10)

    assert [r.hit.uc_id for r in ranked] == ["UC-ACTIVE", "UC-DRAFT"]
    assert ranked[0].weighted_score == 0.6


async def test_search_propagates_a_search_failure() -> None:
    retriever, _, _ = _retriever(index=FakeIndex(error=PortError("BD caída")))

    with pytest.raises(PortError):
        await retriever.search([0.1], top_k=10)


async def test_retrieve_is_embed_query_then_search() -> None:
    """`retrieve()` es un envoltorio fino: mismo resultado que llamar a los dos métodos por separado."""
    index = FakeIndex([_hit("UC-1", 0.6)])
    retriever, embeddings, _ = _retriever(FakeEmbeddingModel(vector=[0.7]), index)

    ranked = await retriever.retrieve("consulta", top_k=5, domain=KbDomain.media_and_dam)

    assert embeddings.queries == ["consulta"]
    assert index.calls[0]["query_vector"] == [0.7]
    assert index.calls[0]["top_k"] == 5
    assert index.calls[0]["domain"] is KbDomain.media_and_dam
    assert [r.hit.uc_id for r in ranked] == ["UC-1"]
