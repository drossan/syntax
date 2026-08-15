"""app.core.config — configuración por entorno (pydantic-settings).

Inyectable y SIN efectos en import: `Settings` no se instancia a nivel de módulo,
"""

from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración de la app, cargada del entorno / `.env`."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    jwt_access_ttl: int = 900
    jwt_secret: str
    login_max_attempts: int = 5
    login_window_seconds: int = 300
    ai_draft_max_per_ticket: int = 10
    cors_origins: Annotated[list[str], NoDecode] = []

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        """'a, b, a' → ['a', 'b']: separa por comas, quita espacios y vacíos, deduplica."""
        if isinstance(value, str):
            origins = [item.strip() for item in value.split(",")]
            return list(dict.fromkeys(o for o in origins if o))
        return value


@lru_cache
def get_settings() -> Settings:
    """Devuelve la instancia de Settings (cacheada una vez por proceso)."""
    return Settings()
