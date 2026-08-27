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
from app.infra.llm.openai_adapter import (
    OpenAIChatModel,
    OpenAIEmbeddingModel,
    get_chat_model,
    get_embedding_model,
)
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import BaseModel


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


# ── OpenAIChatModel (tarea backend-agent-graph-04) ───────────────────────────────


class _Verdict(BaseModel):
    ok: bool


class _FakeStructuredRunnable:
    """Doble de la `Runnable` que devuelve `ChatOpenAI.with_structured_output`."""

    def __init__(self, *, result: BaseModel | None = None, exc: Exception | None = None) -> None:
        self._result = result
        self._exc = exc
        self.captured_prompt: str | None = None

    async def ainvoke(self, prompt: str) -> BaseModel:
        self.captured_prompt = prompt
        if self._exc is not None:
            raise self._exc
        assert self._result is not None
        return self._result


class _FakeChatResponse:
    def __init__(self, content: str) -> None:
        self.content = content


async def test_classify_delegates_to_structured_output_json_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CU-BE-05 §4: `classify` pide `with_structured_output(schema, method="json_schema")` y devuelve
    la instancia validada, sin parsear texto libre."""
    captured: dict[str, object] = {}
    fake_result = _Verdict(ok=True)

    def fake_with_structured_output(
        self: ChatOpenAI, schema: type[BaseModel], *, method: str = "json_schema", **kwargs: object
    ) -> _FakeStructuredRunnable:
        captured["schema"] = schema
        captured["method"] = method
        return _FakeStructuredRunnable(result=fake_result)

    monkeypatch.setattr(ChatOpenAI, "with_structured_output", fake_with_structured_output)

    model = OpenAIChatModel(_settings())
    result = await model.classify("texto del ticket", _Verdict)

    assert captured["schema"] is _Verdict
    assert captured["method"] == "json_schema"
    assert result is fake_result


async def test_grade_delegates_to_structured_output_json_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`grade` sigue el mismo patrón que `classify` — reutiliza el mismo helper `structured_output`."""
    captured: dict[str, object] = {}
    fake_result = _Verdict(ok=False)

    def fake_with_structured_output(
        self: ChatOpenAI, schema: type[BaseModel], *, method: str = "json_schema", **kwargs: object
    ) -> _FakeStructuredRunnable:
        captured["schema"] = schema
        captured["method"] = method
        return _FakeStructuredRunnable(result=fake_result)

    monkeypatch.setattr(ChatOpenAI, "with_structured_output", fake_with_structured_output)

    model = OpenAIChatModel(_settings())
    result = await model.grade("¿basta el contexto?", _Verdict)

    assert captured["schema"] is _Verdict
    assert captured["method"] == "json_schema"
    assert result is fake_result


async def test_generate_returns_the_free_text_content(monkeypatch: pytest.MonkeyPatch) -> None:
    """`generate` devuelve `.content` de la respuesta del modelo, sin schema."""

    async def fake_ainvoke(self: ChatOpenAI, prompt: str) -> _FakeChatResponse:
        return _FakeChatResponse(content="draft de la respuesta")

    monkeypatch.setattr(ChatOpenAI, "ainvoke", fake_ainvoke)

    model = OpenAIChatModel(_settings())
    result = await model.generate("redacta una respuesta")

    assert result == "draft de la respuesta"


async def test_client_is_built_with_the_configured_model_and_retry_params(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El cliente `ChatOpenAI` se construye con `settings.chat_model` y los mismos `max_retries`/
    `request_timeout` que `OpenAIEmbeddingModel` (consistencia entre adaptadores del mismo proveedor)."""
    captured: dict[str, object] = {}

    async def fake_ainvoke(self: ChatOpenAI, prompt: str) -> _FakeChatResponse:
        captured["model_name"] = self.model_name
        captured["max_retries"] = self.max_retries
        captured["request_timeout"] = self.request_timeout
        captured["temperature"] = self.temperature
        return _FakeChatResponse(content="ok")

    monkeypatch.setattr(ChatOpenAI, "ainvoke", fake_ainvoke)

    model = OpenAIChatModel(_settings(chat_model="gpt-4o-mini", llm_temperature=0.0))
    await model.generate("prompt")

    assert captured["model_name"] == "gpt-4o-mini"
    assert captured["max_retries"] == 3
    assert captured["request_timeout"] == 30.0
    assert captured["temperature"] == 0.0


async def test_client_is_built_with_the_configured_temperature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`settings.llm_temperature` (no un `0.0` fijo en el código) llega al cliente — verificado con un
    valor DISTINTO del default para no coincidir por casualidad con el propio default de `Settings`."""
    captured: dict[str, object] = {}

    async def fake_ainvoke(self: ChatOpenAI, prompt: str) -> _FakeChatResponse:
        captured["temperature"] = self.temperature
        return _FakeChatResponse(content="ok")

    monkeypatch.setattr(ChatOpenAI, "ainvoke", fake_ainvoke)

    model = OpenAIChatModel(_settings(llm_temperature=0.7))
    await model.generate("prompt")

    assert captured["temperature"] == 0.7


@pytest.mark.parametrize("method_name", ["classify", "grade"])
async def test_structured_methods_wrap_provider_failure_in_port_error(
    monkeypatch: pytest.MonkeyPatch, method_name: str
) -> None:
    """Timeout/error de API del proveedor → `PortError`, nunca la excepción cruda del SDK."""

    def fake_with_structured_output(
        self: ChatOpenAI, schema: type[BaseModel], *, method: str = "json_schema", **kwargs: object
    ) -> _FakeStructuredRunnable:
        return _FakeStructuredRunnable(exc=TimeoutError("provider timed out"))

    monkeypatch.setattr(ChatOpenAI, "with_structured_output", fake_with_structured_output)

    model = OpenAIChatModel(_settings())
    method = getattr(model, method_name)
    with pytest.raises(PortError):
        await method("prompt", _Verdict)


async def test_generate_wraps_provider_failure_in_port_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_ainvoke(self: ChatOpenAI, prompt: str) -> _FakeChatResponse:
        raise TimeoutError("provider timed out")

    monkeypatch.setattr(ChatOpenAI, "ainvoke", fake_ainvoke)

    model = OpenAIChatModel(_settings())
    with pytest.raises(PortError):
        await model.generate("prompt")


@pytest.mark.parametrize("method_name", ["classify", "grade"])
async def test_output_that_does_not_validate_against_schema_is_also_a_port_error(
    monkeypatch: pytest.MonkeyPatch, method_name: str
) -> None:
    """Una salida que `with_structured_output` no puede mapear al schema también es `PortError`,
    distinguible en el mensaje de un fallo de red (el texto de la excepción original se conserva)."""
    from pydantic import ValidationError

    validation_exc = ValidationError.from_exception_data("_Verdict", [])

    def fake_with_structured_output(
        self: ChatOpenAI, schema: type[BaseModel], *, method: str = "json_schema", **kwargs: object
    ) -> _FakeStructuredRunnable:
        return _FakeStructuredRunnable(exc=validation_exc)

    monkeypatch.setattr(ChatOpenAI, "with_structured_output", fake_with_structured_output)

    model = OpenAIChatModel(_settings())
    method = getattr(model, method_name)
    with pytest.raises(PortError, match="_Verdict"):
        await method("prompt", _Verdict)


async def test_chat_model_lazy_initialization_without_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sin `openai_api_key`, construir `OpenAIChatModel` no falla; el fallo llega solo al primer uso."""
    settings = Settings(_env_file=None, jwt_secret="x", openai_api_key="")
    model = OpenAIChatModel(settings)  # no lanza

    with pytest.raises(PortError):
        await model.generate("prompt")


def test_importing_module_does_not_instantiate_any_chat_client() -> None:
    import app.infra.llm.openai_adapter as adapter_module

    clients = [v for v in vars(adapter_module).values() if isinstance(v, ChatOpenAI)]
    assert clients == []


async def test_get_chat_model_with_openai_returns_operative_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JWT_SECRET", "x")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    get_settings.cache_clear()

    async def fake_ainvoke(self: ChatOpenAI, prompt: str) -> _FakeChatResponse:
        return _FakeChatResponse(content="ok")

    monkeypatch.setattr(ChatOpenAI, "ainvoke", fake_ainvoke)

    try:
        model = get_chat_model(get_settings())
        result = await model.generate("prompt")
    finally:
        get_settings.cache_clear()

    assert result == "ok"


@pytest.mark.parametrize("provider", ["anthropic", "zzz-unsupported"])
def test_get_chat_model_with_unsupported_provider_fails_clear(provider: str) -> None:
    with pytest.raises(PortError):
        get_chat_model(_settings(llm_provider=provider))
