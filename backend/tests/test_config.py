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
        ("AI_DRAFT_MAX_PER_TICKET", "ai_draft_max_per_ticket", 10),
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
