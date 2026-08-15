"""Tests de app.main — app factory, /health/live, CORS y envelope problem+json.

Integración en proceso con ``httpx.ASGITransport`` (sin servidor ni DB).
"""

import json

import httpx
import pytest
from app.core.config import Settings
from app.main import create_app
from fastapi import FastAPI
from pydantic import ValidationError


def _settings(app_env: str = "production", cors_origins: list[str] | None = None) -> Settings:
    """Settings de test aislados del `.env` real."""
    return Settings(
        _env_file=None,
        jwt_secret="x" * 32,
        app_env=app_env,
        cors_origins=cors_origins or [],
    )


def _client(app: FastAPI, *, raise_app_exceptions: bool = True) -> httpx.AsyncClient:
    """Cliente httpx que habla con la app ASGI en proceso."""
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


# ── Construcción del factory ──


def test_create_app_returns_fastapi_instance() -> None:
    """create_app() con settings inyectados devuelve una FastAPI sin tocar red/DB."""
    app = create_app(_settings())

    assert isinstance(app, FastAPI)


def test_create_app_fails_with_invalid_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Si get_settings() no puede construir Settings (falta un requerido), create_app() falla al arrancar."""
    monkeypatch.setattr("app.main.get_settings", lambda: Settings(_env_file=None))

    with pytest.raises(ValidationError):
        create_app()


# ── Liveness + request-id ──


async def test_health_live_returns_200_alive() -> None:
    """GET /health/live → 200 con estado vivo, sin tocar dependencias."""
    app = create_app(_settings())

    async with _client(app) as c:
        r = await c.get("/health/live")

    assert r.status_code == 200
    assert r.json()["status"] == "alive"


async def test_response_has_generated_request_id() -> None:
    """Sin X-Request-ID entrante, la respuesta trae uno generado no vacío."""
    app = create_app(_settings())

    async with _client(app) as c:
        r = await c.get("/health/live")

    assert r.headers.get("X-Request-ID")


async def test_response_echoes_incoming_request_id() -> None:
    """La respuesta devuelve el X-Request-ID entrante válido."""
    app = create_app(_settings())

    async with _client(app) as c:
        r = await c.get("/health/live", headers={"X-Request-ID": "abc-123"})

    assert r.headers["X-Request-ID"] == "abc-123"


async def test_log_and_response_share_request_id(capsys: pytest.CaptureFixture[str]) -> None:
    """Correlación e2e: el log emitido al procesar la request lleva el mismo id que el header."""
    app = create_app(_settings("production"))  # JSON logs

    async with _client(app) as c:
        r = await c.get("/health/live", headers={"X-Request-ID": "corr-1"})

    out = capsys.readouterr().out
    logged = [json.loads(line) for line in out.strip().splitlines() if line.strip().startswith("{")]
    assert any(entry.get("request_id") == "corr-1" for entry in logged)
    assert r.headers["X-Request-ID"] == "corr-1"


# ── Envelope problem+json ──


async def test_unknown_route_returns_problem_json_404() -> None:
    """Ruta desconocida → 404 problem+json con envelope completo y request-id."""
    app = create_app(_settings())

    async with _client(app) as c:
        r = await c.get("/ruta-inexistente")

    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["type"]
    assert body["title"]
    assert body["status"] == 404
    assert body["detail"]
    assert r.headers.get("X-Request-ID")


async def test_validation_error_returns_422_with_errors() -> None:
    """Entrada inválida → 422 problem+json con errors[] (field/message/code)."""
    app = create_app(_settings())

    @app.get("/_test/validate")
    async def _validate(n: int) -> dict[str, int]:
        return {"n": n}

    async with _client(app) as c:
        r = await c.get("/_test/validate", params={"n": "no-es-int"})

    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["status"] == 422
    assert body["title"] == "Error de validación"
    assert len(body["errors"]) >= 1
    err = body["errors"][0]
    assert "field" in err
    assert "message" in err
    assert "code" in err


async def test_unhandled_exception_returns_500_problem_json() -> None:
    """Excepción no controlada → 500 problem+json (no la traza por defecto)."""
    app = create_app(_settings())

    @app.get("/_test/boom")
    async def _boom() -> None:
        raise RuntimeError("boom")

    async with _client(app, raise_app_exceptions=False) as c:
        r = await c.get("/_test/boom")

    assert r.status_code == 500
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["status"] == 500
    assert body["title"] == "Error interno del servidor"


async def test_method_not_allowed_returns_405_problem_json() -> None:
    """Método no permitido → 405 problem+json."""
    app = create_app(_settings())

    async with _client(app) as c:
        r = await c.post("/health/live")

    assert r.status_code == 405
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["title"] == "Método no permitido"


@pytest.mark.parametrize("route", ["/health/ready", "/health"])
async def test_deferred_health_routes_return_clean_404(route: str) -> None:
    """/health/ready y el alias /health, diferidos, dan 404 limpio (no 500) problem+json."""
    app = create_app(_settings())

    async with _client(app) as c:
        r = await c.get(route)

    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")


@pytest.mark.parametrize(
    ("lang", "expected_title"),
    [
        ("es", "No encontrado"),
        ("en", "Not Found"),
        ("fr", "No encontrado"),  # no soportado → fallback al base (es)
        ("en;q=0.9", "Not Found"),  # con q-value → se ignora el peso
        ("en-US", "Not Found"),  # subtag de región → idioma primario
    ],
)
async def test_problem_title_localized_by_accept_language(lang: str, expected_title: str) -> None:
    """title/detail se localizan por Accept-Language (base es + en; fallback base)."""
    app = create_app(_settings())

    async with _client(app) as c:
        r = await c.get("/ruta-inexistente", headers={"Accept-Language": lang})

    assert r.json()["title"] == expected_title


# ── CORS ──


async def test_cors_allows_listed_origin() -> None:
    """Preflight desde un origen listado → autorizado."""
    app = create_app(_settings("production", cors_origins=["https://app.example"]))

    async with _client(app) as c:
        r = await c.options(
            "/health/live",
            headers={
                "Origin": "https://app.example",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert r.headers.get("access-control-allow-origin") == "https://app.example"


async def test_cors_denies_unlisted_origin_in_production() -> None:
    """En production, un origen no listado no se autoriza."""
    app = create_app(_settings("production", cors_origins=["https://app.example"]))

    async with _client(app) as c:
        r = await c.options(
            "/health/live",
            headers={
                "Origin": "https://malo.example",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert r.headers.get("access-control-allow-origin") is None


async def test_cors_permissive_in_development_without_origins() -> None:
    """En development sin CORS_ORIGINS → permisivo (autoriza cualquier origen)."""
    app = create_app(_settings("development", cors_origins=[]))

    async with _client(app) as c:
        r = await c.options(
            "/health/live",
            headers={
                "Origin": "https://cualquiera.example",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert r.headers.get("access-control-allow-origin") == "https://cualquiera.example"


@pytest.mark.parametrize("env", ["production", "acceptance"])
async def test_cors_not_permissive_outside_development(env: str) -> None:
    """Solo development es permisivo: fuera de dev, cors vacío NO autoriza orígenes (no security hole)."""
    app = create_app(_settings(env, cors_origins=[]))

    async with _client(app) as c:
        r = await c.options(
            "/health/live",
            headers={
                "Origin": "https://algo.example",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert r.headers.get("access-control-allow-origin") is None
