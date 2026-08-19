"""app.api.errors — envelope de error único (`application/problem+json`, RFC 9457) para toda la API.

Traduce las 5 `DomainError` de `app.domain.errors` y el `Deny` de `rbac_service.authorize` al mismo
envelope que ya usaba `app.main` para 404/405/422/500/503 (localizado por `Accept-Language`, es/en) —
este módulo es ahora la fuente única de esos mensajes; `app.main` los reusa para no divergir.

Mapeo de status: `NotFound`→404, `Conflict`/`InvalidTransition`→409, `Validation`→422, `PortError`→502
(fallo de un proveedor externo — no es culpa del cliente, tampoco un 500 genérico que sugeriría un bug
propio). `Deny` de `rbac_service.authorize` **no es una excepción** (el "no" es el camino esperado, no
un error de dominio) — `AuthorizationDenied` la envuelve para que un router la traduzca lanzándola, sin
un `if` ad-hoc por router: `no_capability`→403, `out_of_scope`→404 (no revela que el recurso existe en
otro tenant, CU-BE-03 RN-3).
"""

from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.domain.errors import Conflict, DomainError, NotFound, PortError, Validation
from app.domain.services.rbac_service import Deny, DenyReason

PROBLEM_MEDIA_TYPE = "application/problem+json"
DEFAULT_LANG = "es"
SUPPORTED_LANGS = ("es", "en")

# Mensajes del envelope localizados por status (``es`` = idioma base, ``en`` = alterno).
MESSAGES: dict[int, dict[str, dict[str, str]]] = {
    403: {
        "es": {"title": "Prohibido", "detail": "No tienes capacidad para esta acción."},
        "en": {"title": "Forbidden", "detail": "You lack the capability for this action."},
    },
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
    409: {
        "es": {"title": "Conflicto", "detail": "La operación no es válida en el estado actual."},
        "en": {"title": "Conflict", "detail": "The operation is not valid in the current state."},
    },
    422: {
        "es": {"title": "Error de validación", "detail": "La petición no supera la validación."},
        "en": {"title": "Validation Error", "detail": "The request failed validation."},
    },
    500: {
        "es": {"title": "Error interno del servidor", "detail": "Ha ocurrido un error inesperado."},
        "en": {"title": "Internal Server Error", "detail": "An unexpected error occurred."},
    },
    502: {
        "es": {
            "title": "Error de proveedor externo",
            "detail": "Un servicio externo del que dependemos ha fallado.",
        },
        "en": {"title": "Upstream Error", "detail": "An external service we depend on failed."},
    },
    503: {
        "es": {"title": "Servicio no disponible", "detail": "El servicio no está listo."},
        "en": {"title": "Service Unavailable", "detail": "The service is not ready."},
    },
}
GENERIC_MESSAGE: dict[str, dict[str, str]] = {
    "es": {"title": "Error", "detail": "La petición no se pudo completar."},
    "en": {"title": "Error", "detail": "The request could not be completed."},
}

_DENY_REASON_STATUS: dict[DenyReason, int] = {
    DenyReason.no_capability: 403,
    DenyReason.out_of_scope: 404,
}


class AuthorizationDenied(Exception):
    """Envuelve un `Deny` de `rbac_service.authorize` para que un router lo traduzca a HTTP lanzándolo,
    sin un `if` ad-hoc por router."""

    def __init__(self, deny: Deny) -> None:
        self.deny = deny
        super().__init__(deny.reason.value)


def negotiate_language(accept_language: str | None) -> str:
    """Elige un idioma soportado desde ``Accept-Language``; fallback al idioma base (``es``)."""
    if not accept_language:
        return DEFAULT_LANG
    for part in accept_language.split(","):
        primary = part.split(";")[0].strip().lower().split("-")[0]
        if primary in SUPPORTED_LANGS:
            return primary
    return DEFAULT_LANG


def localized_messages(status: int, lang: str) -> dict[str, str]:
    """Devuelve ``{title, detail}`` para el ``status`` en ``lang`` (fallback al idioma base)."""
    entry = MESSAGES.get(status, GENERIC_MESSAGE)
    return entry.get(lang, entry[DEFAULT_LANG])


def problem_response(
    *,
    status: int,
    request: Request,
    detail: str | None = None,
    errors: list[dict[str, str]] | None = None,
) -> JSONResponse:
    """Construye una respuesta ``application/problem+json`` (RFC 9457) localizada por ``Accept-Language``."""
    lang = negotiate_language(request.headers.get("Accept-Language"))
    messages = localized_messages(status, lang)
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": messages["title"],
        "status": status,
        "detail": detail if detail is not None else messages["detail"],
    }
    if errors is not None:
        body["errors"] = errors
    return JSONResponse(status_code=status, content=body, media_type=PROBLEM_MEDIA_TYPE)


def _status_for_domain_error(exc: DomainError) -> int:
    """Resuelve el status HTTP de una `DomainError` — orden por especificidad (`InvalidTransition` es
    una `Conflict`, ambas 409, así que el orden entre ellas no importa; sí importa comprobar cada base
    antes que asumir un fallback)."""
    if isinstance(exc, NotFound):
        return 404
    if isinstance(exc, Conflict):
        return 409
    if isinstance(exc, Validation):
        return 422
    if isinstance(exc, PortError):
        return 502
    return 500


def _validation_errors(exc: Validation) -> list[dict[str, str]] | None:
    """`Validation.details` con forma `{field, message}` se vuelca en `Problem.errors[]`; cualquier
    otra forma de `details` (contexto arbitrario de otros servicios) no se expone como `errors[]`."""
    if "field" in exc.details and "message" in exc.details:
        return [
            {
                "field": str(exc.details["field"]),
                "message": str(exc.details["message"]),
                "code": exc.code,
            }
        ]
    return None


async def domain_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """`NotFound`/`Conflict`/`InvalidTransition`/`Validation`/`PortError` → problem+json con su status."""
    domain_exc = cast(DomainError, exc)
    status = _status_for_domain_error(domain_exc)
    errors = _validation_errors(domain_exc) if isinstance(domain_exc, Validation) else None
    return problem_response(status=status, request=request, detail=str(domain_exc), errors=errors)


async def authorization_denied_handler(request: Request, exc: Exception) -> JSONResponse:
    """`AuthorizationDenied` → 403 (`no_capability`) / 404 (`out_of_scope`), sin detail específico
    (no revela por qué se denegó)."""
    denied = cast(AuthorizationDenied, exc)
    status = _DENY_REASON_STATUS[denied.deny.reason]
    return problem_response(status=status, request=request)


def register_exception_handlers(app: FastAPI) -> None:
    """Registra los handlers de `DomainError`/`AuthorizationDenied` en `app` (llamado por `create_app()`).

    Basta con registrar `NotFound`/`Conflict`/`Validation`/`PortError`: Starlette recorre el MRO de la
    excepción lanzada, así que `InvalidTransition` (subclase de `Conflict`) encuentra el handler de
    `Conflict` sin registro propio — mismo status (409) de todas formas.
    """
    app.add_exception_handler(NotFound, domain_error_handler)
    app.add_exception_handler(Conflict, domain_error_handler)
    app.add_exception_handler(Validation, domain_error_handler)
    app.add_exception_handler(PortError, domain_error_handler)
    app.add_exception_handler(AuthorizationDenied, authorization_denied_handler)
