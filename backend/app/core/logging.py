"""app.core.logging — logging estructurado (structlog) + request-id por request.

Primitivas de observabilidad. `configure_logging(settings)` se llama desde `create_app()`; el request-id
vive en los contextvars de structlog (task-local, async-safe) y `get_request_id()` lo lee.
"""

import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from structlog.contextvars import bound_contextvars

from app.core.config import Settings


def get_request_id() -> str | None:
    """Devuelve el request-id del contexto actual, o ``None`` fuera de una request."""
    return structlog.contextvars.get_contextvars().get("request_id")


def configure_logging(settings: Settings) -> None:
    """Configura structlog: JSON si ``APP_ENV != development``, consola legible en development.
    Idempotente y sin efectos en import (se llama desde ``create_app()``)."""
    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer()
        if settings.app_env != "development"
        else structlog.dev.ConsoleRenderer(colors=False)
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            renderer,
        ],
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )


def _new_request_id() -> str:
    """Genera un id de correlación nuevo (uuid4)."""
    return str(uuid.uuid4())


_MAX_REQUEST_ID_LEN = 128


def _sanitize_request_id(raw: str | None) -> str | None:
    """Sanea el X-Request-ID entrante: filtra caracteres no imprimibles (CR/LF/control) y recorta a
    ``_MAX_REQUEST_ID_LEN``. Devuelve None si queda vacío (→ generar uno nuevo)."""
    if raw is None:
        return None
    cleaned = "".join(c for c in raw if c.isprintable())[:_MAX_REQUEST_ID_LEN]
    return cleaned or None


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Fija un request-id por petición, lo bindea a structlog durante la request y lo ecoa en la respuesta."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        rid = _sanitize_request_id(request.headers.get("X-Request-ID")) or _new_request_id()
        with bound_contextvars(request_id=rid):
            response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response
