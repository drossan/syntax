"""app.main — app factory (composición) + /health/live + envelope problem+json.

Único módulo que conoce API + infra a la vez. `create_app()` valida settings, configura logging, monta el
middleware de request-id (``app.core.logging``) y CORS, registra los handlers de error
``application/problem+json`` (RFC 9457; ``title``/``detail`` localizados por ``Accept-Language`` — contrato
en ``.claude/specs/general/api-contract.md``) y expone ``GET /health/live``. Exporta ``app`` para uvicorn
(``app.main:app``). Sin efectos en import (ni clientes ni conexiones): la validación de settings ocurre en el factory.

``GET /health/ready`` y el alias ``GET /health`` comprueban DB alcanzable + extensión pgvector + dimensión
viva == ``settings.embedding_dim`` (200) o **503 problem+json** con el detalle del fallo (chequeo en
``app.core.readiness``, acotado por timeout). ``GET /health/live`` no toca DB.

Los mensajes localizados y el builder del envelope viven en ``app.api.errors`` (fuente única, reusada
también por los handlers de ``DomainError``/``AuthorizationDenied`` que routers de tareas posteriores
disparan) — este módulo solo los reusa para 404/405/422/500/503 de infraestructura HTTP (ruta
desconocida, método no permitido, validación de request, excepción no controlada, readiness).
"""

from typing import cast

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.errors import problem_response, register_exception_handlers
from app.api.v1.routers.admin_roles import router as admin_roles_router
from app.api.v1.routers.admin_tenants import router as admin_tenants_router
from app.api.v1.routers.admin_users import router as admin_users_router
from app.api.v1.routers.auth import router as auth_router
from app.api.v1.routers.kb import router as kb_router
from app.api.v1.routers.messages import router as messages_router
from app.api.v1.routers.tickets import router as tickets_router
from app.core.config import Settings, get_settings
from app.core.logging import RequestIDMiddleware, configure_logging
from app.core.readiness import ReadinessError, check_database_ready

_logger = structlog.get_logger()


async def _http_exception_handler(request: Request, exc: Exception) -> Response:
    """``HTTPException``/``StarletteHTTPException`` (incl. 404/405) → problem+json localizado."""
    http_exc = cast(StarletteHTTPException, exc)
    return problem_response(status=http_exc.status_code, request=request)


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
    return problem_response(status=422, request=request, errors=errors)


async def _unhandled_exception_handler(request: Request, exc: Exception) -> Response:
    """Excepción no controlada → 500 problem+json (no la traza por defecto de FastAPI/Starlette)."""
    return problem_response(status=500, request=request)


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
    register_exception_handlers(app)
    app.add_exception_handler(Exception, _unhandled_exception_handler)

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(admin_tenants_router, prefix="/api/v1")
    app.include_router(admin_users_router, prefix="/api/v1")
    app.include_router(admin_roles_router, prefix="/api/v1")
    app.include_router(tickets_router, prefix="/api/v1")
    app.include_router(messages_router, prefix="/api/v1")
    app.include_router(kb_router, prefix="/api/v1")

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
            return problem_response(status=503, request=request, detail=str(exc))
        return JSONResponse(content={"status": "ready"})

    return app


app = create_app()
