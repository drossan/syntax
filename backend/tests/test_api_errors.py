"""Tests de app.api.errors (tarea backend-routers-core-03) — envelope problem+json transversal.

Integración en proceso con `httpx.ASGITransport` (mismo patrón que `test_main.py`): monta rutas de
prueba que lanzan cada excepción a propósito sobre la app real de `create_app()`, para probar los
handlers tal como los usarán los routers reales (05-09), sin repetir la lógica de negocio de esos CU.
"""

import httpx
import pytest
from app.api.errors import (
    AuthorizationDenied,
    _status_for_domain_error,
    _validation_errors,
    localized_messages,
)
from app.core.config import Settings
from app.domain.errors import (
    Conflict,
    DomainError,
    InvalidTransition,
    NotFound,
    PortError,
    Validation,
)
from app.domain.services.rbac_service import Deny, DenyReason
from app.main import create_app
from fastapi import FastAPI


def _settings() -> Settings:
    return Settings(_env_file=None, jwt_secret="x" * 32, app_env="production", cors_origins=[])


def _client(app: FastAPI, *, raise_app_exceptions: bool = True) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.parametrize(
    ("exc_factory", "expected_status"),
    [
        (lambda: NotFound("no existe", code="x.not_found"), 404),
        (lambda: Conflict("conflicto", code="x.conflict"), 409),
        (lambda: InvalidTransition("transición inválida", code="x.invalid_transition"), 409),
        (lambda: Validation("inválido", code="x.validation"), 422),
        (lambda: PortError("proveedor externo falló"), 502),
    ],
)
async def test_each_domain_error_maps_to_its_status(
    exc_factory: object, expected_status: int
) -> None:
    """Cada DomainError se traduce al status correcto en application/problem+json."""
    app = create_app(_settings())

    @app.get("/_test/domain-error")
    async def _raise() -> None:
        raise exc_factory()  # type: ignore[operator]

    async with _client(app, raise_app_exceptions=False) as c:
        r = await c.get("/_test/domain-error")

    assert r.status_code == expected_status
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["status"] == expected_status


async def test_deny_no_capability_maps_to_403() -> None:
    """Deny(no_capability) se traduce a 403 problem+json."""
    app = create_app(_settings())

    @app.get("/_test/deny-capability")
    async def _raise() -> None:
        raise AuthorizationDenied(Deny(DenyReason.no_capability))

    async with _client(app, raise_app_exceptions=False) as c:
        r = await c.get("/_test/deny-capability")

    assert r.status_code == 403
    assert r.headers["content-type"].startswith("application/problem+json")


async def test_deny_out_of_scope_maps_to_404() -> None:
    """Deny(out_of_scope) se traduce a 404 problem+json (no revela que el recurso existe en otro tenant)."""
    app = create_app(_settings())

    @app.get("/_test/deny-scope")
    async def _raise() -> None:
        raise AuthorizationDenied(Deny(DenyReason.out_of_scope))

    async with _client(app, raise_app_exceptions=False) as c:
        r = await c.get("/_test/deny-scope")

    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")


async def test_unmapped_exception_returns_500_without_leaking_internal_detail() -> None:
    """Una excepción de Python no mapeada da 500 problem+json genérico, sin traza ni mensaje interno."""
    app = create_app(_settings())

    @app.get("/_test/boom-secret")
    async def _raise() -> None:
        raise RuntimeError("contraseña-super-secreta-no-debe-salir")

    async with _client(app, raise_app_exceptions=False) as c:
        r = await c.get("/_test/boom-secret")

    assert r.status_code == 500
    body = r.json()
    assert "contraseña-super-secreta-no-debe-salir" not in body["detail"]


@pytest.mark.parametrize(
    ("lang", "expected_lang_marker"),
    [("en", "en"), ("fr", "es"), ("garbage-!!", "es")],
)
async def test_domain_error_problem_respects_accept_language(
    lang: str, expected_lang_marker: str
) -> None:
    """title/detail de un error mapeado (NotFound) se localizan por Accept-Language; no soportado → es."""
    app = create_app(_settings())

    @app.get("/_test/not-found")
    async def _raise() -> None:
        raise NotFound("no existe", code="x.not_found")

    async with _client(app, raise_app_exceptions=False) as c:
        r = await c.get("/_test/not-found", headers={"Accept-Language": lang})

    title = r.json()["title"]
    if expected_lang_marker == "en":
        assert title == "Not Found"
    else:
        assert title == "No encontrado"


async def test_validation_details_with_field_and_message_populate_problem_errors() -> None:
    """Validation con details={field, message} se vuelca en Problem.errors[]; detail no expone más."""
    app = create_app(_settings())

    @app.get("/_test/validation-field")
    async def _raise() -> None:
        raise Validation(
            "valor inválido",
            code="ticket.invalid_priority",
            details={"field": "priority", "message": "valor inválido"},
        )

    async with _client(app, raise_app_exceptions=False) as c:
        r = await c.get("/_test/validation-field")

    body = r.json()
    assert body["status"] == 422
    assert body["errors"] == [
        {"field": "priority", "message": "valor inválido", "code": "ticket.invalid_priority"}
    ]


async def test_deny_no_capability_title_is_localized_to_forbidden() -> None:
    """El título de un Deny(no_capability) (403) usa el mensaje propio, no el genérico de fallback."""
    app = create_app(_settings())

    @app.get("/_test/deny-capability-title")
    async def _raise() -> None:
        raise AuthorizationDenied(Deny(DenyReason.no_capability))

    async with _client(app, raise_app_exceptions=False) as c:
        r = await c.get("/_test/deny-capability-title")

    assert r.json()["title"] == "Prohibido"


async def test_conflict_title_is_localized_to_conflicto() -> None:
    """El título de un Conflict (409) usa el mensaje propio, no el genérico de fallback."""
    app = create_app(_settings())

    @app.get("/_test/conflict-title")
    async def _raise() -> None:
        raise Conflict("conflicto", code="x.conflict")

    async with _client(app, raise_app_exceptions=False) as c:
        r = await c.get("/_test/conflict-title")

    assert r.json()["title"] == "Conflicto"


async def test_port_error_title_is_localized_to_upstream() -> None:
    """El título de un PortError (502) usa el mensaje propio, no el genérico de fallback."""
    app = create_app(_settings())

    @app.get("/_test/port-error-title")
    async def _raise() -> None:
        raise PortError("proveedor externo falló")

    async with _client(app, raise_app_exceptions=False) as c:
        r = await c.get("/_test/port-error-title")

    assert r.json()["title"] == "Error de proveedor externo"


@pytest.mark.parametrize(
    ("status", "expected_title"),
    [
        (403, "Prohibido"),
        (404, "No encontrado"),
        (405, "Método no permitido"),
        (409, "Conflicto"),
        (422, "Error de validación"),
        (500, "Error interno del servidor"),
        (502, "Error de proveedor externo"),
        (503, "Servicio no disponible"),
    ],
)
def test_localized_messages_has_its_own_title_per_status_not_the_generic_fallback(
    status: int, expected_title: str
) -> None:
    """Cada status con entrada propia en MESSAGES tiene su título específico (no el genérico de
    fallback) — cubre las 8 claves declaradas, mutation-kill de cualquier clave desplazada."""
    assert localized_messages(status, "es")["title"] == expected_title


class _UnmappedDomainError(DomainError):
    """Doble de test: una DomainError que no es ninguna de las 4 subclases con handler registrado."""


def test_status_for_domain_error_falls_back_to_500_for_unmapped_subclasses() -> None:
    """_status_for_domain_error responde 500 para una DomainError que no es Not Found/Conflict/
    Validation/PortError (rama de fallback, no alcanzable vía los handlers registrados pero
    probada aquí a nivel de unidad)."""
    assert _status_for_domain_error(_UnmappedDomainError("x", code="x.unmapped")) == 500


def test_validation_errors_requires_both_field_and_message_not_just_one() -> None:
    """_validation_errors exige AMBAS claves (field Y message), no basta con una sola."""
    only_field = Validation("x", code="x.v", details={"field": "priority"})
    only_message = Validation("x", code="x.v", details={"message": "valor inválido"})

    assert _validation_errors(only_field) is None
    assert _validation_errors(only_message) is None


async def test_validation_without_field_message_details_has_no_errors_array() -> None:
    """Validation con details que NO tienen forma field/message no rellena Problem.errors[]."""
    app = create_app(_settings())

    @app.get("/_test/validation-generic")
    async def _raise() -> None:
        raise Validation(
            "transición inválida",
            code="ticket.invalid_transition",
            details={"from": "new", "to": "closed"},
        )

    async with _client(app, raise_app_exceptions=False) as c:
        r = await c.get("/_test/validation-generic")

    assert "errors" not in r.json()
