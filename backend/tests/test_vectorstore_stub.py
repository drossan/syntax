"""Tests de `app.infra.vectorstore.stub.StubVectorStore` (tarea `backend-routers-core-09`).

Sin Postgres — el stub no toca ninguna base de datos.
"""

from app.domain.entities.enums import KbDomain, KbEstado, Package
from app.infra.vectorstore.stub import StubVectorStore


async def test_search_returns_an_empty_deterministic_result() -> None:
    store = StubVectorStore()

    hits, total = await store.search("cualquier cosa")

    assert hits == []
    assert total == 0


async def test_search_ignores_filters_and_still_returns_empty() -> None:
    store = StubVectorStore()

    hits, total = await store.search(
        "q",
        domain=KbDomain.media_and_dam,
        package=Package.syntax_api,
        estado=KbEstado.active,
        page=2,
        page_size=50,
    )

    assert hits == []
    assert total == 0


async def test_get_document_always_returns_none() -> None:
    store = StubVectorStore()

    assert await store.get_document("UC-API-001") is None


async def test_list_documents_returns_an_empty_deterministic_result() -> None:
    store = StubVectorStore()

    documents, total = await store.list_documents()

    assert documents == []
    assert total == 0
