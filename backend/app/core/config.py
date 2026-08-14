"""app.core.config — settings inyectables (pydantic-settings).

GUIÓN (→ tarea 07)
------------------
Propósito: cargar la configuración por entorno SIN efectos en import y exponerla inyectable.

Qué implementar:
  - ``class Settings(BaseSettings)`` (pydantic-settings, v2) con los campos de ``.env.example``:
      APP_ENV; DATABASE_URL (asyncpg); JWT_SECRET / JWT_ALGORITHM / JWT_ACCESS_TTL / JWT_REFRESH_TTL;
      OPENAI_API_KEY / CHAT_MODEL / EMBEDDING_MODEL / EMBEDDING_DIM; LANGSMITH_TRACING / _API_KEY /
      _PROJECT / _ENDPOINT; y los límites B.1 (LOGIN_MAX_ATTEMPTS, LOGIN_WINDOW_SECONDS,
      AI_DRAFT_MAX_PER_TICKET) con defaults.
      ``model_config = SettingsConfigDict(env_file=".env", extra="ignore")``.
  - ``@lru_cache`` sobre ``get_settings() -> Settings`` (una instancia por proceso, perezosa).
  - ``EMBEDDING_DIM`` es la FUENTE de ``vector(N)`` (03/04): cambiarla exige re-embed + migración.

Contrato: ``get_settings() -> Settings`` (cacheada). Se inyecta vía ``app.core.deps``, nunca se lee
como global en tiempo de import.

Anti-patrones (prohibidos): instanciar ``Settings()`` a nivel de módulo; validar/crear credenciales o
clientes (DB/OpenAI) al importar; secretos hardcodeados. La validación de settings ocurre en el arranque
del factory, no en import (así los tests inyectan settings falsos sin tocar el entorno).
"""
