"""app.core.config — configuración por entorno (pydantic-settings).

Inyectable y SIN efectos en import: `Settings` no se instancia a nivel de módulo,
"""

from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración de la app, cargada del entorno / `.env`."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    jwt_access_ttl: int = 900
    jwt_secret: str
    login_max_attempts: int = 5
    login_window_seconds: int = 300
    ai_draft_rate_limit_per_minute: int = 10
    """Límite de `POST /tickets/{id}/ai-draft` por tenant, ventana fija de 1 minuto, in-memory por
    proceso (`InMemoryRateLimiter`, tarea 12) — sustituye a `ai_draft_max_per_ticket` (B.1, nunca
    implementado, semántica por-ticket/de-por-vida redundante con el CAS del índice único parcial de
    `agent_run`)."""
    cors_origins: Annotated[list[str], NoDecode] = []

    database_url: str = "postgresql+asyncpg://syntax_app:syntax_app@localhost:5432/syntax"
    """DSN asyncpg del rol runtime `syntax_app` (no-superuser → RLS aplica).

    Default de desarrollo para que `Settings()` sea construible sin `.env`. La URL de
    migraciones (superuser) NO vive aquí: la lee `alembic/env.py` del entorno
    (least-privilege — el proceso API nunca arranca con credenciales superuser).
    """

    embedding_dim: int = Field(default=1536, gt=0)
    """Dimensión del vector de embeddings (`> 0`).

    La consume `/health/ready` para asertar que la dimensión viva de la columna
    `embedding.vector` coincide con la config. El modelo ORM usa `Vector(1536)` literal.
    """

    llm_provider: str = "openai"
    """Selector del adaptador de puerto LLM/embeddings (`app.infra.llm.openai_adapter`). Hoy solo
    `"openai"` es un valor soportado por la factory `get_embedding_model`."""

    openai_api_key: str = ""
    """Clave de API de OpenAI. Vacía por defecto para que `Settings()` sea construible sin ella
    (validación perezosa: el adaptador falla al primer uso real, no aquí)."""

    chat_model: str = "gpt-4o-mini"
    """Modelo de chat/clasificación (structured output). Sin adaptador real todavía en este plan
    (`OpenAIChatModel` sigue GUIÓN) — se declara aquí junto al resto de config LLM/embeddings."""

    embedding_model: str = "text-embedding-3-small"
    """Modelo de embeddings usado por `OpenAIEmbeddingModel`."""

    chunk_token_budget: int = Field(default=800, gt=0)
    """Presupuesto de tokens por chunk del chunker de ingestión (`app.ingestion.chunker`), contados
    con `tiktoken` sobre el encoding de `embedding_model`. `800` es un default sensato (~el tamaño
    típico de una sección H2 de la KB) — sin este campo no había ningún valor fijado (hallazgo de
    `scenario-coverage`, plan `kb-ingestion`)."""

    embedding_batch_size: int = Field(default=100, gt=0)
    """Nº máximo de textos por llamada a `EmbeddingModel.embed_documents` desde
    `app.ingestion.embedder`. `100` es conservador, por debajo del límite real de items por request
    de OpenAI — evita que un batch grande de la ingestión real supere ese límite (hallazgo de
    `scenario-coverage`, plan `kb-ingestion`)."""

    kb_source_path: str = ""
    """Ruta raíz de la KB para `python -m app.ingestion` (`app.ingestion.cli`) cuando no se pasa como
    argumento posicional. Vacía por defecto — no hay fuente real en esta máquina; la CLI falla con un
    error de uso claro (no un `None` silencioso) si ni el argumento ni este campo están fijados."""

    kb_source_type: str = "packages-uc"
    """Tipo de fuente de la KB (`app.ingestion.sources`): `packages-uc` (formato real verificado, el
    default) o `vitepress-domains` (hipotético, nunca verificado).

    **`str`, no `Literal`**, a propósito: la validación es **perezosa**, en `resolve_source()`/CLI. Un
    `Literal` estricto haría que un typo en esta env var —que solo usa la ingestión— tumbase el
    arranque de **toda** la app (auth, tickets…). Mismo criterio que `llm_provider`/`kb_source_path`."""

    kb_package_aliases: str = ""
    """Traducción `subdirectorio de package` → valor de `Package`, como **JSON crudo**
    (`KB_PACKAGE_ALIASES='{"vendor-render": "syntax-render"}'`). Es vocabulario del deployment, no de
    la estructura del formato (RN-5 de CU-BE-07).

    **`str`, no `dict[str, str]`**, por el mismo motivo que `kb_source_type` no es `Literal`: un
    `dict` tipado lo validaría pydantic-settings de forma **eager** al construir `Settings()`, así que
    un JSON malformado tumbaría el arranque de toda la app en vez de fallar acotado a `make ingest`
    (extensión 1m). Se parsea y valida donde se usa. Vacío por defecto → sin configurarlo, el tipo
    `packages-uc` no ingiere ningún UC (extensión 1l; la CLI avisa por stderr)."""

    storage_root: str = "./var/storage"
    """Directorio raíz de `LocalFilesystemStorage` (tarea 08) — relativo al cwd del proceso en dev."""

    max_upload_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    """Tamaño máximo de un adjunto (10 MiB por defecto) — por encima, `POST .../attachments` → 413."""

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        """'a, b, a' → ['a', 'b']: separa por comas, quita espacios y vacíos, deduplica."""
        if isinstance(value, str):
            origins = [item.strip() for item in value.split(",")]
            return list(dict.fromkeys(o for o in origins if o))
        return value

    @field_validator("database_url", mode="after")
    @classmethod
    def _reject_empty_database_url(cls, value: str) -> str:
        """Rechaza un DSN vacío: el default solo cubre la ausencia, no un `""` explícito."""
        if not value.strip():
            raise ValueError("database_url no puede estar vacío")
        return value


@lru_cache
def get_settings() -> Settings:
    """Devuelve la instancia de Settings (cacheada una vez por proceso)."""
    return Settings()
