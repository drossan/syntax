"""Tests unit de `app.core.deps._LazyEmbeddingModel` (tarea `backend-kb-retriever-07`).

`_LazyEmbeddingModel` está **fuera del alcance de `test_router_kb.py`**: sus tests sobrescriben
`get_embeddings_port` con un doble para no depender del proveedor real, así que la clase perezosa en
sí —lo que realmente evita que `/kb/documents` se tumbe por una config de embeddings rota— nunca se
ejercitaba. Estos tests la prueban en aislamiento, monkeypatcheando el factory que envuelve.
"""

import pytest
from app.core.config import Settings
from app.core.deps import _LazyEmbeddingModel
from app.domain.errors import PortError


class _CountingModel:
    """Doble mínimo del `EmbeddingModel` real que devolvería `get_embedding_model`."""

    def __init__(self) -> None:
        self.embed_query_calls = 0

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] for _ in texts]

    async def embed_query(self, text: str) -> list[float]:
        self.embed_query_calls += 1
        return [0.1]


def _settings() -> Settings:
    return Settings(_env_file=None, jwt_secret="x" * 32)


def test_constructing_it_does_not_call_the_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Construir `_LazyEmbeddingModel` NO construye el adaptador real: es justo lo que evita que
    `/kb/documents` se tumbe por una `embedding_dim` mal configurada (`OpenAIEmbeddingModel.__init__`
    valida esa dimensión y lanza `PortError` al construir, no al usar)."""
    calls: list[Settings] = []

    def fake_factory(settings: Settings) -> _CountingModel:
        calls.append(settings)
        return _CountingModel()

    monkeypatch.setattr("app.core.deps.get_embedding_model", fake_factory)

    _LazyEmbeddingModel(_settings())

    assert calls == []


async def test_first_embed_query_call_constructs_the_real_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = _CountingModel()
    monkeypatch.setattr("app.core.deps.get_embedding_model", lambda settings: real)
    lazy = _LazyEmbeddingModel(_settings())

    await lazy.embed_query("consulta")

    assert real.embed_query_calls == 1


async def test_the_real_model_is_constructed_only_once_and_reused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El caso que el gate de mutation destapó: sin el `if self._model is None`, cada llamada
    reconstruiría el adaptador (coste de red/validación repetido) o, con el mutante que invierte la
    condición, la primera llamada devolvería `None` y reventaría en `AttributeError`."""
    construction_count = 0

    def fake_factory(settings: Settings) -> _CountingModel:
        nonlocal construction_count
        construction_count += 1
        return _CountingModel()

    monkeypatch.setattr("app.core.deps.get_embedding_model", fake_factory)
    lazy = _LazyEmbeddingModel(_settings())

    await lazy.embed_query("primera")
    await lazy.embed_query("segunda")

    assert construction_count == 1


async def test_a_construction_failure_propagates_as_port_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si el factory falla (p.ej. `embedding_dim` mal configurado), el `PortError` sube tal cual en
    la primera llamada real — que es exactamente lo que dispara `/kb/search`, no `/kb/documents`."""

    def failing_factory(settings: Settings) -> _CountingModel:
        raise PortError("embedding_dim no coincide")

    monkeypatch.setattr("app.core.deps.get_embedding_model", failing_factory)
    lazy = _LazyEmbeddingModel(_settings())

    with pytest.raises(PortError):
        await lazy.embed_query("consulta")


async def test_embed_documents_also_resolves_lazily(monkeypatch: pytest.MonkeyPatch) -> None:
    """El puerto tiene dos operaciones (`embed_documents`/`embed_query`); las dos pasan por la misma
    resolución perezosa — no solo `embed_query`."""
    real = _CountingModel()
    monkeypatch.setattr("app.core.deps.get_embedding_model", lambda settings: real)
    lazy = _LazyEmbeddingModel(_settings())

    result = await lazy.embed_documents(["a", "b"])

    assert result == [[0.1], [0.1]]
