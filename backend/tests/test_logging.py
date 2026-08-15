"""Tests de app.core.logging — logging estructurado + request-id."""

import asyncio
import json

import pytest
import structlog
from app.core.config import Settings
from app.core.logging import RequestIDMiddleware, configure_logging, get_request_id
from starlette.requests import Request
from starlette.responses import Response
from structlog.contextvars import bind_contextvars, clear_contextvars


@pytest.fixture(autouse=True)
def _clean_contextvars():
    clear_contextvars()
    yield
    clear_contextvars()


def _settings(app_env: str = "production") -> Settings:
    return Settings(_env_file=None, jwt_secret="x", app_env=app_env)


def _make_request(headers: dict[str, str] | None = None) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({"type": "http", "headers": raw})


def test_get_request_id_is_none_without_context() -> None:
    """Fuera de toda request, no hay id de correlación."""
    clear_contextvars()

    assert get_request_id() is None


def test_log_carries_request_id_from_context(capsys) -> None:
    """El request-id del contexto aparece en la salida del log (JSON)."""
    configure_logging(_settings("production"))
    bind_contextvars(request_id="rid-1")

    structlog.get_logger().info("evento")

    out = capsys.readouterr().out
    assert '"request_id": "rid-1"' in out


@pytest.mark.parametrize(
    ("env", "is_json"),
    [("production", True), ("test", True), ("ci", True), ("development", False)],
)
def test_renderer_depends_on_env(capsys, env: str, is_json: bool) -> None:
    """JSON si APP_ENV != development; consola legible (sin color) en development."""
    configure_logging(_settings(env))

    structlog.get_logger().info("evt")

    out = capsys.readouterr().out.strip()
    if is_json:
        assert json.loads(out)["event"] == "evt"  # parsea como JSON
    else:
        assert not out.startswith("{")  # consola, no JSON
        assert "evt" in out
        assert "\x1b[" not in out  # sin códigos de color ANSI (colors=False)


def test_configure_logging_is_idempotent(capsys) -> None:
    """Configurar dos veces no duplica la salida del log."""
    configure_logging(_settings("production"))
    configure_logging(_settings("production"))

    structlog.get_logger().info("una-vez")

    out = capsys.readouterr().out
    assert out.count("una-vez") == 1


async def test_middleware_generates_id_when_absent() -> None:
    """Sin X-Request-ID entrante: genera uno y lo ecoa en la respuesta."""
    seen: dict[str, str | None] = {}

    async def call_next(request: Request) -> Response:
        seen["rid"] = get_request_id()
        return Response("ok")

    mw = RequestIDMiddleware(app=None)
    response = await mw.dispatch(_make_request(), call_next)

    assert seen["rid"] is not None
    assert response.headers["X-Request-ID"] == seen["rid"]


async def test_middleware_respects_valid_incoming_id() -> None:
    """Con X-Request-ID válido entrante, se usa y se ecoa tal cual."""
    seen: dict[str, str | None] = {}

    async def call_next(request: Request) -> Response:
        seen["rid"] = get_request_id()
        return Response("ok")

    mw = RequestIDMiddleware(app=None)
    response = await mw.dispatch(_make_request({"X-Request-ID": "abc-123"}), call_next)

    assert seen["rid"] == "abc-123"
    assert response.headers["X-Request-ID"] == "abc-123"


async def test_middleware_treats_empty_incoming_id_as_absent() -> None:
    """X-Request-ID presente pero vacío → se genera uno nuevo (no se usa el vacío)."""
    seen: dict[str, str | None] = {}

    async def call_next(request: Request) -> Response:
        seen["rid"] = get_request_id()
        return Response("ok")

    mw = RequestIDMiddleware(app=None)
    response = await mw.dispatch(_make_request({"X-Request-ID": ""}), call_next)

    assert seen["rid"]  # no vacío
    assert response.headers["X-Request-ID"] == seen["rid"]


async def test_middleware_sanitizes_crlf_in_incoming_id() -> None:
    """Un X-Request-ID con CR/LF se sanea (evita header/log injection)."""
    seen: dict[str, str | None] = {}

    async def call_next(request: Request) -> Response:
        seen["rid"] = get_request_id()
        return Response("ok")

    mw = RequestIDMiddleware(app=None)
    response = await mw.dispatch(_make_request({"X-Request-ID": "abc\r\nX-Evil: 1"}), call_next)

    rid = seen["rid"]
    assert rid is not None
    assert "\r" not in rid and "\n" not in rid
    assert "\r" not in response.headers["X-Request-ID"]
    assert "\n" not in response.headers["X-Request-ID"]


async def test_middleware_truncates_oversized_incoming_id() -> None:
    """Un X-Request-ID desmesurado se recorta al máximo permitido (128)."""
    seen: dict[str, str | None] = {}

    async def call_next(request: Request) -> Response:
        seen["rid"] = get_request_id()
        return Response("ok")

    mw = RequestIDMiddleware(app=None)
    response = await mw.dispatch(_make_request({"X-Request-ID": "z" * 10000}), call_next)

    assert seen["rid"] is not None
    assert len(seen["rid"]) == 128
    assert len(response.headers["X-Request-ID"]) == 128


async def test_concurrent_requests_do_not_leak_ids() -> None:
    """Dos requests async concurrentes conservan cada una su propio id."""
    seen: dict[str, str | None] = {}
    mw = RequestIDMiddleware(app=None)

    def make_call_next(tag: str):
        async def call_next(request: Request) -> Response:
            await asyncio.sleep(0.01)  # cede el control → fuerza el solape
            seen[tag] = get_request_id()
            return Response("ok")

        return call_next

    await asyncio.gather(
        mw.dispatch(_make_request({"X-Request-ID": "a"}), make_call_next("a")),
        mw.dispatch(_make_request({"X-Request-ID": "b"}), make_call_next("b")),
    )

    assert seen["a"] == "a"
    assert seen["b"] == "b"


async def test_contextvar_is_reset_after_request() -> None:
    """Tras terminar la request, el contextvar vuelve a None (no fuga a la siguiente)."""
    mw = RequestIDMiddleware(app=None)

    async def call_next(request: Request) -> Response:
        return Response("ok")

    await mw.dispatch(_make_request({"X-Request-ID": "abc"}), call_next)

    assert get_request_id() is None
