"""Tests de app.infra.llm.openai_adapter (tarea backend-kb-ingestion-01).

Suite de contrato del adaptador OpenAI de `EmbeddingModel`. `aembed_documents` del SDK
`langchain_openai.OpenAIEmbeddings` se parchea a nivel de clase (sin red real, sin `OPENAI_API_KEY`
real) — patrón nuevo en este repo (decisión de `grilling`), ejercita código real del adaptador
(construcción del cliente, fail-fast de dimensión, mapeo a `PortError`).
"""

import pytest
from app.core.config import Settings, get_settings
from app.domain.errors import PortError
from app.infra.db.models.kb import EMBEDDING_DIM_LITERAL
from app.infra.llm.openai_adapter import OpenAIEmbeddingModel, get_embedding_model
from langchain_openai import OpenAIEmbeddings


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, jwt_secret="x", openai_api_key="sk-test", **overrides)


async def test_embed_documents_delegates_with_configured_dimension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """embed_documents llama al proveedor con los N textos y dimensions=settings.embedding_dim."""
    captured: dict[str, object] = {}

    async def fake_aembed_documents(self: OpenAIEmbeddings, texts: list[str]) -> list[list[float]]:
        captured["texts"] = texts
        captured["dimensions"] = self.dimensions
        captured["max_retries"] = self.max_retries
        captured["request_timeout"] = self.request_timeout
        return [[0.1, 0.2] for _ in texts]

    monkeypatch.setattr(OpenAIEmbeddings, "aembed_documents", fake_aembed_documents)

    model = OpenAIEmbeddingModel(_settings())
    result = await model.embed_documents(["texto a", "texto b"])

    assert captured["texts"] == ["texto a", "texto b"]
    assert captured["dimensions"] == EMBEDDING_DIM_LITERAL
    assert captured["max_retries"] == 3
    assert captured["request_timeout"] == 30.0
    assert result == [[0.1, 0.2], [0.1, 0.2]]


@pytest.mark.parametrize("embedding_dim", [EMBEDDING_DIM_LITERAL + 1, EMBEDDING_DIM_LITERAL - 1])
async def test_dimension_mismatch_aborts_before_any_network_call(embedding_dim: int) -> None:
    """settings.embedding_dim distinto del literal del ORM (por encima o por debajo) aborta al
    construir, sin llamar a nada."""
    with pytest.raises(PortError):
        OpenAIEmbeddingModel(_settings(embedding_dim=embedding_dim))


async def test_provider_failure_propagates_wrapped_in_port_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un fallo del proveedor (timeout/429/error de API) se propaga envuelto en PortError."""

    async def fake_aembed_documents(self: OpenAIEmbeddings, texts: list[str]) -> list[list[float]]:
        raise TimeoutError("provider timed out")

    monkeypatch.setattr(OpenAIEmbeddings, "aembed_documents", fake_aembed_documents)

    model = OpenAIEmbeddingModel(_settings())
    with pytest.raises(PortError):
        await model.embed_documents(["texto"])


async def test_provider_returns_fewer_vectors_than_texts_raises_port_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El proveedor devuelve menos vectores que textos enviados → error claro, no un resultado desalineado."""

    async def fake_aembed_documents(self: OpenAIEmbeddings, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2]] * (len(texts) - 1)

    monkeypatch.setattr(OpenAIEmbeddings, "aembed_documents", fake_aembed_documents)

    model = OpenAIEmbeddingModel(_settings())
    with pytest.raises(PortError):
        await model.embed_documents(["a", "b", "c"])


async def test_provider_returns_more_vectors_than_texts_raises_port_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El proveedor devuelve MÁS vectores que textos enviados → también es un desajuste, error claro."""

    async def fake_aembed_documents(self: OpenAIEmbeddings, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2]] * (len(texts) + 1)

    monkeypatch.setattr(OpenAIEmbeddings, "aembed_documents", fake_aembed_documents)

    model = OpenAIEmbeddingModel(_settings())
    with pytest.raises(PortError):
        await model.embed_documents(["a", "b", "c"])


async def test_empty_texts_list_returns_empty_without_calling_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lista vacía de textos no llama al proveedor y devuelve una lista vacía."""
    called = False

    async def fake_aembed_documents(self: OpenAIEmbeddings, texts: list[str]) -> list[list[float]]:
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(OpenAIEmbeddings, "aembed_documents", fake_aembed_documents)

    model = OpenAIEmbeddingModel(_settings())
    result = await model.embed_documents([])

    assert result == []
    assert called is False


async def test_large_batch_with_matching_vector_count_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un batch grande (> 256 elementos, fuera del rango de enteros cacheados de CPython) con el
    mismo número de vectores que de textos no falla — un mutante `!=`→`is not` en la comprobación
    de longitudes sí fallaría aquí, porque dos `int` iguales pero de objetos distintos por encima de
    ese rango no son el mismo objeto."""
    texts = [f"texto {i}" for i in range(300)]

    async def fake_aembed_documents(self: OpenAIEmbeddings, texts: list[str]) -> list[list[float]]:
        return [[0.1] for _ in texts]

    monkeypatch.setattr(OpenAIEmbeddings, "aembed_documents", fake_aembed_documents)

    model = OpenAIEmbeddingModel(_settings())
    result = await model.embed_documents(texts)

    assert len(result) == 300


async def test_single_text_makes_one_call_with_one_vector(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un solo texto hace una llamada con un solo vector devuelto."""

    async def fake_aembed_documents(self: OpenAIEmbeddings, texts: list[str]) -> list[list[float]]:
        return [[0.5] for _ in texts]

    monkeypatch.setattr(OpenAIEmbeddings, "aembed_documents", fake_aembed_documents)

    model = OpenAIEmbeddingModel(_settings())
    result = await model.embed_documents(["único texto"])

    assert result == [[0.5]]


async def test_missing_api_key_fails_at_first_use_not_at_construction() -> None:
    """openai_api_key vacía no falla al construir Settings ni el adaptador, sí al primer uso real."""
    settings = Settings(_env_file=None, jwt_secret="x", openai_api_key="")
    model = OpenAIEmbeddingModel(settings)  # no lanza
    with pytest.raises(PortError):
        await model.embed_documents(["texto"])


def test_importing_module_does_not_instantiate_any_client() -> None:
    """Importar el módulo no crea ningún cliente OpenAI ni lanza ninguna excepción."""
    import app.infra.llm.openai_adapter as adapter_module

    clients = [v for v in vars(adapter_module).values() if isinstance(v, OpenAIEmbeddings)]
    assert clients == []


async def test_get_embedding_model_with_openai_returns_operative_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_embedding_model("openai") devuelve un adaptador que delega en el proveedor configurado.

    `llm_provider` llega vía variable de entorno (objeto `str` construido en tiempo de ejecución por
    el parser de pydantic-settings) en vez del literal `_settings(llm_provider="openai")` — así un
    mutante que cambie `==` por `is` no sobrevive por coincidencia de interning de CPython (dos
    literales `"openai"` compilados por separado sí pueden acabar siendo el mismo objeto interno).
    """
    monkeypatch.setenv("JWT_SECRET", "x")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    get_settings.cache_clear()

    async def fake_aembed_documents(self: OpenAIEmbeddings, texts: list[str]) -> list[list[float]]:
        return [[0.9] for _ in texts]

    monkeypatch.setattr(OpenAIEmbeddings, "aembed_documents", fake_aembed_documents)

    try:
        model = get_embedding_model(get_settings())
        result = await model.embed_documents(["x"])
    finally:
        get_settings.cache_clear()

    assert result == [[0.9]]


@pytest.mark.parametrize("provider", ["anthropic", "zzz-unsupported"])
def test_get_embedding_model_with_unsupported_provider_fails_clear(provider: str) -> None:
    """settings.llm_provider distinto de "openai" falla explícito, no un adaptador incorrecto en
    silencio. Se prueba con un valor alfabéticamente ANTERIOR ("anthropic") y otro POSTERIOR
    ("zzz-unsupported") a "openai": un mutante que cambie `==` por `<=`/`>=` solo se distingue con
    un valor en la dirección donde `==` y esa comparación de orden difieren."""
    with pytest.raises(PortError):
        get_embedding_model(_settings(llm_provider=provider))


# ── embed_query (tarea backend-kb-retriever-03) ─────────────────────────────────


async def test_embed_query_delegates_with_configured_dimension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CU-BE-12 · camino feliz del puerto: `embed_query` devuelve el vector de la consulta, con la
    dimensión configurada y los mismos parámetros de cliente que `embed_documents`."""
    captured: dict[str, object] = {}

    async def fake_aembed_query(self: OpenAIEmbeddings, text: str) -> list[float]:
        captured["text"] = text
        captured["dimensions"] = self.dimensions
        captured["max_retries"] = self.max_retries
        captured["request_timeout"] = self.request_timeout
        return [0.5] * EMBEDDING_DIM_LITERAL

    monkeypatch.setattr(OpenAIEmbeddings, "aembed_query", fake_aembed_query)

    model = OpenAIEmbeddingModel(_settings())
    result = await model.embed_query("cómo subo un vídeo")

    assert captured["text"] == "cómo subo un vídeo"
    assert captured["dimensions"] == EMBEDDING_DIM_LITERAL
    assert captured["max_retries"] == 3
    assert captured["request_timeout"] == 30.0
    assert len(result) == EMBEDDING_DIM_LITERAL


async def test_embed_query_provider_failure_propagates_wrapped_in_port_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CU-BE-12 · *Un fallo del proveedor de embeddings no se disfraza de KB vacía* — en la capa del
    adaptador: cualquier fallo del proveedor sale como `PortError` (el router lo traduce a 502)."""

    async def fake_aembed_query(self: OpenAIEmbeddings, text: str) -> list[float]:
        raise TimeoutError("provider timed out")

    monkeypatch.setattr(OpenAIEmbeddings, "aembed_query", fake_aembed_query)

    model = OpenAIEmbeddingModel(_settings())
    with pytest.raises(PortError):
        await model.embed_query("consulta")


async def test_embed_query_does_not_rewrap_an_existing_port_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un `PortError` que ya venga de dentro se propaga TAL CUAL, sin re-envolverse: re-envolver
    perdería el mensaje original dentro de otro genérico."""

    async def fake_aembed_query(self: OpenAIEmbeddings, text: str) -> list[float]:
        raise PortError("mensaje original del puerto")

    monkeypatch.setattr(OpenAIEmbeddings, "aembed_query", fake_aembed_query)

    model = OpenAIEmbeddingModel(_settings())
    with pytest.raises(PortError, match="mensaje original del puerto"):
        await model.embed_query("consulta")


@pytest.mark.parametrize("returned_dim", [EMBEDDING_DIM_LITERAL - 1, EMBEDDING_DIM_LITERAL + 1, 0])
async def test_embed_query_with_unexpected_vector_dimension_fails_as_a_port_error(
    monkeypatch: pytest.MonkeyPatch, returned_dim: int
) -> None:
    """CU-BE-12 · *Un vector de dimensión inesperada se rechaza como fallo del proveedor*.

    Modo de fallo DISTINTO de "proveedor caído": la respuesta está bien formada, pero los datos son
    incompatibles. Sin este assert el vector llegaría a la comparación pgvector y reventaría como
    error de driver, sin decir qué pasó realmente.
    """

    async def fake_aembed_query(self: OpenAIEmbeddings, text: str) -> list[float]:
        return [0.1] * returned_dim

    monkeypatch.setattr(OpenAIEmbeddings, "aembed_query", fake_aembed_query)

    model = OpenAIEmbeddingModel(_settings())
    with pytest.raises(PortError):
        await model.embed_query("consulta")


async def test_embed_query_without_api_key_fails_before_any_network_call() -> None:
    """Sin `openai_api_key` el adaptador falla al construir el cliente (validación perezosa), no con
    una llamada de red sin credenciales."""
    model = OpenAIEmbeddingModel(Settings(_env_file=None, jwt_secret="x", openai_api_key=""))

    with pytest.raises(PortError):
        await model.embed_query("consulta")
