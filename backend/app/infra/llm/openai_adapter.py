"""app.infra.llm.openai_adapter — adaptador OpenAI de los puertos LLM/embeddings.

`OpenAIEmbeddingModel` + `get_embedding_model` (tarea backend-kb-ingestion-01) y `OpenAIChatModel` +
`get_chat_model` (tarea backend-agent-graph-04, agent-graph.md §4/§9) son ambos reales: los nodos
`classify`/`grade`/`generate` del grafo del agente (tarea 05) consumen `OpenAIChatModel`.

Instanciación perezosa (embeddings y chat): el cliente (`OpenAIEmbeddings`/`ChatOpenAI`) se crea al
primer uso real, nunca en import — `settings.openai_api_key` no se valida hasta esa primera llamada.
"""

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import BaseModel

from app.core.config import Settings
from app.domain.errors import PortError
from app.domain.ports.embeddings import EmbeddingModel
from app.domain.ports.llm import ChatModel
from app.infra.db.models.kb import EMBEDDING_DIM_LITERAL
from app.infra.llm.structured import structured_output


class OpenAIEmbeddingModel:
    """Adaptador real de `EmbeddingModel` sobre `langchain_openai.OpenAIEmbeddings`.

    Fail-fast de dimensión: `embedding.vector` es `Vector(EMBEDDING_DIM_LITERAL)` **literal** en el
    ORM (deliberadamente no gobernado por `settings.embedding_dim` — ver `app.infra.db.models.kb`).
    Si `settings.embedding_dim` no coincide, se aborta aquí (al construir, sin red) en vez de dejar
    que el `INSERT` falle a media ingesta.
    """

    def __init__(self, settings: Settings) -> None:
        if settings.embedding_dim != EMBEDDING_DIM_LITERAL:
            raise PortError(
                f"settings.embedding_dim ({settings.embedding_dim}) no coincide con la dimensión "
                f"literal de embedding.vector ({EMBEDDING_DIM_LITERAL}); cambiarla de verdad exige "
                "una migración de columna + re-embeber todo el corpus."
            )
        self._settings = settings
        self._client: OpenAIEmbeddings | None = None

    def _get_client(self) -> OpenAIEmbeddings:
        if self._client is None:
            if not self._settings.openai_api_key:
                raise PortError("openai_api_key no configurada")
            self._client = OpenAIEmbeddings(
                model=self._settings.embedding_model,
                dimensions=self._settings.embedding_dim,
                openai_api_key=self._settings.openai_api_key,
                max_retries=3,
                request_timeout=30.0,
            )
        return self._client

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        client = self._get_client()
        try:
            vectors = await client.aembed_documents(texts)
        except PortError:
            raise
        except Exception as exc:
            raise PortError(f"fallo al embeber documentos: {exc}") from exc
        if len(vectors) != len(texts):
            raise PortError(
                f"el proveedor devolvió {len(vectors)} vectores para {len(texts)} textos"
            )
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        """Vector de una consulta de búsqueda (`aembed_query` del SDK).

        **Se valida la dimensión del vector devuelto**, en el mismo espíritu con el que
        `embed_documents` valida el *número* de vectores: una respuesta bien formada con datos
        incompatibles es un modo de fallo distinto de "el proveedor está caído", y sin este control
        reventaría más tarde, en la comparación pgvector, como un error de driver que no dice qué pasó.

        :raises app.domain.errors.PortError: fallo del proveedor, clave ausente, o vector de dimensión
            distinta a `settings.embedding_dim`.
        """
        client = self._get_client()
        try:
            vector = await client.aembed_query(text)
        except PortError:
            raise
        except Exception as exc:
            raise PortError(f"fallo al embeber la consulta: {exc}") from exc
        if len(vector) != self._settings.embedding_dim:
            raise PortError(
                f"el proveedor devolvió un vector de dimensión {len(vector)}; la configurada es "
                f"{self._settings.embedding_dim}"
            )
        return vector


def get_embedding_model(settings: Settings) -> EmbeddingModel:
    """Factory de `EmbeddingModel`, conmutable por `settings.llm_provider`."""
    if settings.llm_provider == "openai":
        return OpenAIEmbeddingModel(settings)
    raise PortError(f"llm_provider no soportado: {settings.llm_provider!r}")


class OpenAIChatModel:
    """Adaptador real de `ChatModel` sobre `langchain_openai.ChatOpenAI`, modelo `settings.chat_model`.

    `classify`/`grade` delegan en `structured_output` (mismo helper, mismo mapeo a `PortError`);
    `generate` invoca el modelo sin schema y devuelve el texto libre de la respuesta.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: ChatOpenAI | None = None

    def _get_client(self) -> ChatOpenAI:
        if self._client is None:
            if not self._settings.openai_api_key:
                raise PortError("openai_api_key no configurada")
            self._client = ChatOpenAI(
                model=self._settings.chat_model,
                openai_api_key=self._settings.openai_api_key,
                max_retries=3,
                request_timeout=30.0,
            )
        return self._client

    async def classify(self, text: str, schema: type[BaseModel]) -> BaseModel:
        return await structured_output(self._get_client(), text, schema)

    async def grade(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
        return await structured_output(self._get_client(), prompt, schema)

    async def generate(self, prompt: str) -> str:
        client = self._get_client()
        try:
            response = await client.ainvoke(prompt)
        except PortError:
            raise
        except Exception as exc:
            raise PortError(f"fallo al generar la respuesta: {exc}") from exc
        return str(response.content)


def get_chat_model(settings: Settings) -> ChatModel:
    """Factory de `ChatModel`, conmutable por `settings.llm_provider`."""
    if settings.llm_provider == "openai":
        return OpenAIChatModel(settings)
    raise PortError(f"llm_provider no soportado: {settings.llm_provider!r}")
