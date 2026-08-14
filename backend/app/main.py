"""app.main — app factory + healthcheck.

GUIÓN (→ tarea 07)
------------------
Propósito: ensamblar la aplicación FastAPI (composición). Único sitio que conoce API + infra a la vez.

Qué implementar:
  - ``create_app() -> FastAPI``: crea la app, valida settings (``get_settings()``), configura logging
    (``configure_logging``), monta middleware y routers, registra los handlers de error (envelope
    problem+json del contrato 06). Exporta ``app = create_app()`` para uvicorn (``app.main:app``).
  - **Middleware**: request-id (correlación, ``logging.py``); CORS; (refuerzo B.1) **throttling** de
    ``/auth/login`` y ``/auth/refresh`` (in-memory/Redis, con LOGIN_MAX_ATTEMPTS/WINDOW_SECONDS).
  - **Routers**: monta ``app.api.v1`` core (11) y flujo-IA (12) — placeholders hasta esas tareas.
  - **Healthcheck** con split liveness/readiness (refuerzo):
      - ``GET /health/live``  → liveness: el proceso responde (sin tocar dependencias).
      - ``GET /health/ready`` → readiness: **DB alcanzable** + **extensión pgvector presente**
        (p.ej. ``SELECT 1`` y comprobar ``pg_extension`` / ``CREATE EXTENSION IF NOT EXISTS vector``).
        Falla → 503. (Alias ``GET /health`` = readiness para compatibilidad.)
  - **Métricas** (refuerzo): ``GET /metrics`` básico (latencia del flujo-IA, contadores de aprobación/
    errores). Observabilidad de errores (hook Sentry) init en el factory según env.

Contrato: ``create_app()`` (fábrica, testeable con settings inyectados) y ``app`` (instancia para el server).

Anti-patrones: crear la app / clientes / conexiones a nivel de import; leer settings globales en import;
lógica de negocio en ``main.py`` (aquí solo composición); ``/health`` que no comprueba pgvector (el
producto depende de él → un ready verde sin vector es un falso positivo).
"""
