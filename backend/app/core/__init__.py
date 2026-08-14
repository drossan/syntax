"""app.core — configuración transversal y arranque de la aplicación.

GUIÓN (→ tarea 07: Skeleton core + app factory + healthcheck)
--------------------------------------------------------------
Propósito: piezas transversales que todo el backend consume, sin lógica de negocio.

Qué implementar aquí:
  - ``config.py``   → ``Settings(BaseSettings)`` (pydantic-settings). Lee el entorno
                      (ver ``.env.example``). SIN efectos en import; inyectable vía deps.
  - ``security.py`` → hashing Argon2id, emisión/verificación JWT (access/refresh + rotación).
  - ``logging.py``  → logging estructurado + **request-id** por petición (middleware/contextvar).
  - ``deps.py``     → dependencias FastAPI (Settings, sesión DB, sujeto autenticado, capacidades).
  - ``main.py``     → app factory ``app.main:app`` (monta routers, middleware, ``GET /health``
                      que comprueba DB + extensión pgvector).

Contrato: ``get_settings() -> Settings`` cacheada; ``create_app() -> FastAPI``.
Dependencias: importa de ``app.infra`` SOLO en el factory/deps (composición), nunca en el dominio.
Anti-patrones: leer settings en tiempo de import; singletons globales con estado; secretos en código.
"""
