"""app.main — app factory (composición) + /health/live + envelope problem+json.

Único módulo que conoce API + infra a la vez. `create_app()` valida settings, configura logging, monta el
middleware de request-id (``app.core.logging``) y CORS, registra los handlers de error
``application/problem+json`` (RFC 9457; ``title``/``detail`` localizados por ``Accept-Language`` — contrato
en ``.claude/specs/general/api-contract.md``) y expone ``GET /health/live``. Exporta ``app`` para uvicorn
(``app.main:app``). Sin efectos en import (ni clientes ni conexiones): la validación de settings ocurre en el factory.

``GET /health/ready`` y el alias ``GET /health`` comprueban DB alcanzable + extensión pgvector + dimensión
viva == ``settings.embedding_dim`` (200) o **503 problem+json** con el detalle del fallo (chequeo en
``app.core.readiness``, acotado por timeout). ``GET /health/live`` no toca DB.
"""

from typing import Any, cast

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import Settings, get_settings
from app.core.logging import RequestIDMiddleware, configure_logging
from app.core.readiness import ReadinessError, check_database_ready

_PROBLEM_MEDIA_TYPE = "application/problem+json"
_DEFAULT_LANG = "es"
_SUPPORTED_LANGS = ("es", "en")

# Mensajes del envelope localizados por status (``es`` = idioma base, ``en`` = alterno).
_MESSAGES: dict[int, dict[str, dict[str, str]]] = {
    404: {
        "es": {"title": "No encontrado", "detail": "El recurso solicitado no existe."},
        "en": {"title": "Not Found", "detail": "The requested resource does not exist."},
    },
    405: {
        "es": {
            "title": "Método no permitido",
            "detail": "El método HTTP no está permitido en esta ruta.",
        },
        "en": {
            "title": "Method Not Allowed",
            "detail": "The HTTP method is not allowed on this route.",
        },
    },
    422: {
        "es": {"title": "Error de validación", "detail": "La petición no supera la validación."},
        "en": {"title": "Validation Error", "detail": "The request failed validation."},
    },
    500: {
        "es": {"title": "Error interno del servidor", "detail": "Ha ocurrido un error inesperado."},
        "en": {"title": "Internal Server Error", "detail": "An unexpected error occurred."},
    },
    503: {
        "es": {"title": "Servicio no disponible", "detail": "El servicio no está listo."},
        "en": {"title": "Service Unavailable", "detail": "The service is not ready."},
    },
}
_GENERIC_MESSAGE: dict[str, dict[str, str]] = {
    "es": {"title": "Error", "detail": "La petición no se pudo completar."},
    "en": {"title": "Error", "detail": "The request could not be completed."},
}

_logger = structlog.get_logger()


def _negotiate_language(accept_language: str | None) -> str:
    """Elige un idioma soportado desde ``Accept-Language``; fallback al idioma base (``es``)."""
    if not accept_language:
        return _DEFAULT_LANG
    for part in accept_language.split(","):
        primary = part.split(";")[0].strip().lower().split("-")[0]
        if primary in _SUPPORTED_LANGS:
            return primary
    return _DEFAULT_LANG


def _localized_messages(status: int, lang: str) -> dict[str, str]:
    """Devuelve ``{title, detail}`` para el ``status`` en ``lang`` (fallback al base)."""
    entry = _MESSAGES.get(status, _GENERIC_MESSAGE)
    return entry.get(lang, entry[_DEFAULT_LANG])


def _problem_response(
    *,
    status: int,
    request: Request,
    detail: str | None = None,
    errors: list[dict[str, str]] | None = None,
) -> JSONResponse:
    """Construye una respuesta ``application/problem+json`` (RFC 9457) localizada por ``Accept-Language``."""
    lang = _negotiate_language(request.headers.get("Accept-Language"))
    messages = _localized_messages(status, lang)
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": messages["title"],
        "status": status,
        "detail": detail if detail is not None else messages["detail"],
    }
    if errors is not None:
        body["errors"] = errors
    return JSONResponse(status_code=status, content=body, media_type=_PROBLEM_MEDIA_TYPE)


async def _http_exception_handler(request: Request, exc: Exception) -> Response:
    """``HTTPException``/``StarletteHTTPException`` (incl. 404/405) → problem+json localizado."""
    http_exc = cast(StarletteHTTPException, exc)
    return _problem_response(status=http_exc.status_code, request=request)


async def _validation_exception_handler(request: Request, exc: Exception) -> Response:
    """``RequestValidationError`` → 422 problem+json con ``errors[]`` (field/message/code)."""
    validation_exc = cast(RequestValidationError, exc)
    errors = [
        {
            "field": ".".join(str(part) for part in err.get("loc", ())),
            "message": str(err.get("msg", "")),
            "code": str(err.get("type", "")),
        }
        for err in validation_exc.errors()
    ]
    return _problem_response(status=422, request=request, errors=errors)


async def _unhandled_exception_handler(request: Request, exc: Exception) -> Response:
    """Excepción no controlada → 500 problem+json (no la traza por defecto de FastAPI/Starlette)."""
    return _problem_response(status=500, request=request)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Ensambla la aplicación FastAPI (composición).

    Valida settings (``get_settings()`` si no se inyectan → falla en el arranque si falta un requerido),
    configura logging, monta el middleware de request-id y CORS, registra los handlers problem+json y expone
    ``GET /health/live``. No abre conexiones ni crea clientes.
    """
    if settings is None:
        settings = get_settings()
    configure_logging(settings)

    app = FastAPI(title="Syntax API")

    # CORS: en development sin orígenes configurados → permisivo; si no, solo los orígenes listados.
    if settings.app_env == "development" and not settings.cors_origins:
        allow_origins = ["*"]
    else:
        allow_origins = settings.cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # request-id aplicado por fuera → etiqueta también las respuestas de error (404/405/422).
    app.add_middleware(RequestIDMiddleware)

    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)

    @app.get("/health/live")
    async def health_live() -> dict[str, str]:
        """Liveness: el proceso responde. NO toca DB ni dependencias externas."""
        _logger.info("health_live")
        return {"status": "alive"}

    @app.get("/health/ready")
    @app.get("/health")
    async def health_ready(request: Request) -> Response:
        """Readiness: DB alcanzable + extensión pgvector + dimensión viva == config → 200.

        Si algún chequeo falla → **503 application/problem+json** con el `detail` del fallo (usa el
        mismo envelope que los errores). `/health` es un alias de `/health/ready`. NO cuelga: el
        chequeo está acotado por timeout (una DB lenta → 503, no un cuelgue indefinido).
        """
        try:
            await check_database_ready(settings.database_url, settings.embedding_dim)
        except ReadinessError as exc:
            _logger.warning("health_ready_failed", detail=str(exc))
            return _problem_response(status=503, request=request, detail=str(exc))
        return JSONResponse(content={"status": "ready"})

    return app


app = create_app()
