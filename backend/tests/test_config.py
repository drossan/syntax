"""Tests de app.core.config — configuración inyectable por entorno."""

import pytest
from app.core.config import Settings, get_settings
from pydantic import ValidationError


@pytest.fixture(autouse=True)
def _reset_settings_cache(monkeypatch):
    """Aísla cada test: baseline de env requerido + limpia la caché de get_settings."""
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_get_settings_is_cached() -> None:
    """get_settings() devuelve siempre la misma instancia (cacheada)."""
    assert get_settings() is get_settings()


def test_reads_app_env_from_environment(monkeypatch) -> None:
    """Settings toma sus valores del entorno inyectado."""
    monkeypatch.setenv("APP_ENV", "production")
    assert get_settings().app_env == "production"


def test_reads_jwt_access_ttl_as_int(monkeypatch) -> None:
    """JWT_ACCESS_TTL llega como texto pero se expone como int."""
    monkeypatch.setenv("JWT_ACCESS_TTL", "900")
    assert get_settings().jwt_access_ttl == 900  # int 900, no "900


def test_jwt_access_ttl_defaults_to_900() -> None:
    """Sin JWT_ACCESS_TTL (ni entorno ni .env), jwt_access_ttl es 900 por defecto."""
    settings = Settings(_env_file=None, jwt_secret="x")
    assert settings.jwt_access_ttl == 900


def test_invalid_type_raises_validation_error(monkeypatch) -> None:
    """Un valor no numérico en un campo int aborta con ValidationError."""
    monkeypatch.setenv("JWT_ACCESS_TTL", "abc")
    with pytest.raises(ValidationError):
        get_settings()


def test_reads_required_secret_from_environment(monkeypatch) -> None:
    """Un campo requerido (sin default) se lee del entorno."""
    monkeypatch.setenv("JWT_SECRET", "super-secret")
    assert get_settings().jwt_secret == "super-secret"


def test_no_module_level_settings_instance(monkeypatch) -> None:
    """No hay una instancia de Settings creada a nivel de módulo (sin efectos en import)."""
    import app.core.config as config_module
    from app.core.config import Settings

    instances = [v for v in vars(config_module).values() if isinstance(v, Settings)]
    assert instances == []


def test_unknow_env_var_is_ignored(monkeypatch) -> None:
    """Una variable de entorno desconocida no rompe la carga (extra='ignore')."""
    monkeypatch.setenv("FOO_DESCONOCIDA", "bar")
    settings = get_settings()
    assert not hasattr(settings, "foo_desconocida")


@pytest.mark.parametrize(
    ("env_var", "attr", "default"),
    [
        ("LOGIN_MAX_ATTEMPTS", "login_max_attempts", 5),
        ("LOGIN_WINDOW_SECONDS", "login_window_seconds", 300),
        ("AI_DRAFT_RATE_LIMIT_PER_MINUTE", "ai_draft_rate_limit_per_minute", 10),
    ],
)
def test_b1_limits_have_defaults(monkeypatch, env_var, attr, default) -> None:
    """Sin la variable en el entorno, el límite B.1 toma su default."""
    monkeypatch.delenv(env_var, raising=False)
    assert getattr(get_settings(), attr) == default


def test_b1_limit_override_from_environment(monkeypatch) -> None:
    """Un límite B.1 se puede sobreescribir por entorno."""
    monkeypatch.setenv("LOGIN_MAX_ATTEMPTS", "9")
    assert get_settings().login_max_attempts == 9


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, []),  # var ausente
        ("", []),  # presente, vacía
        ("https://a.com", ["https://a.com"]),
        (" https://a.com , https://b.com ", ["https://a.com", "https://b.com"]),  # strip
        ("https://a.com,https://a.com", ["https://a.com"]),  # dedup
    ],
)
def test_cors_origins_normalized(monkeypatch, raw, expected) -> None:
    """CORS_ORIGINS → lista: separa por comas, quita espacios y vacíos, deduplica (preserva orden)."""
    if raw is None:
        monkeypatch.delenv("CORS_ORIGINS", raising=False)
    else:
        monkeypatch.setenv("CORS_ORIGINS", raw)

    assert get_settings().cors_origins == expected


# ── DB settings (tarea backend-database-foundation-01) ────────────────────────


def test_database_url_read_from_environment(monkeypatch) -> None:
    """DATABASE_URL del entorno se expone en settings.database_url."""
    dsn = "postgresql+asyncpg://syntax_app:pw@db:5432/syntax"
    monkeypatch.setenv("DATABASE_URL", dsn)
    assert get_settings().database_url == dsn


def test_database_url_defaults_to_syntax_app_dsn(monkeypatch) -> None:
    """Sin DATABASE_URL (ni entorno ni .env) → DSN de dev del rol syntax_app."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(_env_file=None, jwt_secret="x")
    assert (
        settings.database_url == "postgresql+asyncpg://syntax_app:syntax_app@localhost:5432/syntax"
    )


def test_database_url_empty_is_rejected(monkeypatch) -> None:
    """DATABASE_URL presente pero vacío ('') → ValidationError (no cae al default)."""
    monkeypatch.setenv("DATABASE_URL", "")
    with pytest.raises(ValidationError):
        get_settings()


def test_embedding_dim_defaults_to_1536_int(monkeypatch) -> None:
    """Sin EMBEDDING_DIM, embedding_dim es 1536 (int)."""
    monkeypatch.delenv("EMBEDDING_DIM", raising=False)
    settings = Settings(_env_file=None, jwt_secret="x")
    assert settings.embedding_dim == 1536
    assert isinstance(settings.embedding_dim, int)


@pytest.mark.parametrize("value", ["no-numérico", "0", "-1"])
def test_embedding_dim_invalid_raises(monkeypatch, value) -> None:
    """EMBEDDING_DIM no numérico o no físico (<=0, gt=0) aborta la carga."""
    monkeypatch.setenv("EMBEDDING_DIM", value)
    with pytest.raises(ValidationError):
        get_settings()


@pytest.mark.parametrize("value", ["1", "1536", "3072"])
def test_embedding_dim_valid_positive(monkeypatch, value) -> None:
    """EMBEDDING_DIM positivo es válido (frontera gt=0: el mínimo válido es 1)."""
    monkeypatch.setenv("EMBEDDING_DIM", value)
    assert get_settings().embedding_dim == int(value)


def test_no_migration_database_url_field() -> None:
    """La URL de migración (superuser) NO es campo de Settings (least-privilege)."""
    settings = get_settings()
    assert not hasattr(settings, "migration_database_url")
    assert "migration_database_url" not in Settings.model_fields


# ── LLM/embeddings settings (tarea backend-kb-ingestion-01) ───────────────────


def test_llm_provider_defaults_to_openai() -> None:
    """Sin LLM_PROVIDER (ni entorno ni .env), llm_provider es "openai" por defecto."""
    settings = Settings(_env_file=None, jwt_secret="x")
    assert settings.llm_provider == "openai"


def test_openai_api_key_defaults_to_empty_string() -> None:
    """Sin OPENAI_API_KEY (ni entorno ni .env), openai_api_key es "" — Settings() es construible
    sin clave real."""
    settings = Settings(_env_file=None, jwt_secret="x")
    assert settings.openai_api_key == ""


def test_chat_model_defaults_to_gpt_4o_mini() -> None:
    """Sin CHAT_MODEL (ni entorno ni .env), chat_model es "gpt-4o-mini" por defecto."""
    settings = Settings(_env_file=None, jwt_secret="x")
    assert settings.chat_model == "gpt-4o-mini"


def test_embedding_model_defaults_to_text_embedding_3_small() -> None:
    """Sin EMBEDDING_MODEL (ni entorno ni .env), embedding_model es "text-embedding-3-small" por
    defecto."""
    settings = Settings(_env_file=None, jwt_secret="x")
    assert settings.embedding_model == "text-embedding-3-small"


@pytest.mark.parametrize(
    ("env_var", "attr", "value"),
    [
        ("LLM_PROVIDER", "llm_provider", "anthropic"),
        ("OPENAI_API_KEY", "openai_api_key", "sk-real-key"),
        ("CHAT_MODEL", "chat_model", "gpt-4o"),
        ("EMBEDDING_MODEL", "embedding_model", "text-embedding-3-large"),
    ],
)
def test_llm_settings_override_from_environment(monkeypatch, env_var, attr, value) -> None:
    """Cada campo LLM/embeddings se puede sobreescribir por entorno."""
    monkeypatch.setenv(env_var, value)
    assert getattr(get_settings(), attr) == value


# ── Chunking settings (tarea backend-kb-ingestion-04) ──────────────────────────


def test_chunk_token_budget_defaults_to_800(monkeypatch) -> None:
    """Sin CHUNK_TOKEN_BUDGET, chunk_token_budget es 800 (int) por defecto."""
    monkeypatch.delenv("CHUNK_TOKEN_BUDGET", raising=False)
    settings = Settings(_env_file=None, jwt_secret="x")
    assert settings.chunk_token_budget == 800
    assert isinstance(settings.chunk_token_budget, int)


@pytest.mark.parametrize("value", ["no-numérico", "0", "-1"])
def test_chunk_token_budget_invalid_raises(monkeypatch, value) -> None:
    """CHUNK_TOKEN_BUDGET no numérico o no físico (<=0, gt=0) aborta la carga."""
    monkeypatch.setenv("CHUNK_TOKEN_BUDGET", value)
    with pytest.raises(ValidationError):
        get_settings()


@pytest.mark.parametrize("value", ["1", "800", "2000"])
def test_chunk_token_budget_valid_positive(monkeypatch, value) -> None:
    """CHUNK_TOKEN_BUDGET positivo es válido (frontera gt=0: el mínimo válido es 1)."""
    monkeypatch.setenv("CHUNK_TOKEN_BUDGET", value)
    assert get_settings().chunk_token_budget == int(value)


# ── Embedding batch settings (tarea backend-kb-ingestion-05) ───────────────────


def test_embedding_batch_size_defaults_to_100(monkeypatch) -> None:
    """Sin EMBEDDING_BATCH_SIZE, embedding_batch_size es 100 (int) por defecto."""
    monkeypatch.delenv("EMBEDDING_BATCH_SIZE", raising=False)
    settings = Settings(_env_file=None, jwt_secret="x")
    assert settings.embedding_batch_size == 100
    assert isinstance(settings.embedding_batch_size, int)


@pytest.mark.parametrize("value", ["no-numérico", "0", "-1"])
def test_embedding_batch_size_invalid_raises(monkeypatch, value) -> None:
    """EMBEDDING_BATCH_SIZE no numérico o no físico (<=0, gt=0) aborta la carga."""
    monkeypatch.setenv("EMBEDDING_BATCH_SIZE", value)
    with pytest.raises(ValidationError):
        get_settings()


@pytest.mark.parametrize("value", ["1", "100", "500"])
def test_embedding_batch_size_valid_positive(monkeypatch, value) -> None:
    """EMBEDDING_BATCH_SIZE positivo es válido (frontera gt=0: el mínimo válido es 1)."""
    monkeypatch.setenv("EMBEDDING_BATCH_SIZE", value)
    assert get_settings().embedding_batch_size == int(value)
