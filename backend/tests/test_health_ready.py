"""Tests de /health/ready + alias /health + deps.get_db_session (tarea 09).

Integración con `httpx.ASGITransport` + DB real (fixture). Los casos de fallo se simulan inyectando
`Settings` con una DB inalcanzable / una dimensión desajustada / una DB sin migrar.
"""

import uuid

import app.infra.db.session as session_module
import httpx
import pytest
from app.core.config import Settings, get_settings
from app.core.deps import get_db_session
from app.core.readiness import ReadinessError, check_database_ready
from app.main import create_app
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_UNREACHABLE = "postgresql+asyncpg://nobody:nobody@localhost:59999/nope"


def _settings(database_url: str, embedding_dim: int = 1536) -> Settings:
    return Settings(
        _env_file=None,
        jwt_secret="test-secret",
        database_url=database_url,
        embedding_dim=embedding_dim,
    )


async def _get(
    app_db_url: str, path: str, *, database_url: str | None = None, dim: int = 1536
) -> httpx.Response:
    app = create_app(_settings(database_url or app_db_url, dim))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


async def test_ready_returns_200_when_db_and_pgvector_ok(app_db_url: str) -> None:
    """ready con DB migrada + pgvector + dim correcta → 200 con estado listo."""
    response = await _get(app_db_url, "/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


async def test_health_alias_behaves_like_ready(app_db_url: str) -> None:
    """El alias /health se comporta como /health/ready (200)."""
    response = await _get(app_db_url, "/health")
    assert response.status_code == 200


async def test_unreachable_db_returns_503_problem_json(app_db_url: str) -> None:
    """DB inalcanzable → 503 application/problem+json con detail del fallo."""
    response = await _get(app_db_url, "/health/ready", database_url=_UNREACHABLE)
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["status"] == 503


async def test_health_alias_propagates_503(app_db_url: str) -> None:
    """El alias /health también propaga el 503 (no solo el 200)."""
    response = await _get(app_db_url, "/health", database_url=_UNREACHABLE)
    assert response.status_code == 503


@pytest.mark.parametrize("dim", [768, 1024, 3072])  # la DB tiene vector(1536)
async def test_dimension_mismatch_returns_503(app_db_url: str, dim: int) -> None:
    """Dimensión configurada != dimensión viva de embedding.vector → 503 (cualquier desajuste).

    Se prueban dims que ordenan lexicográficamente por debajo (1024) y por encima (768/3072) de "1536"
    para que el chequeo sea una comparación de igualdad estricta, no un `<`/`>` accidental.
    """
    response = await _get(app_db_url, "/health/ready", dim=dim)
    assert response.status_code == 503
    assert "dimensión" in response.json()["detail"]


async def test_liveness_ignores_db(app_db_url: str) -> None:
    """Liveness sigue devolviendo 200 aunque la DB no sea alcanzable (no depende de la DB)."""
    response = await _get(app_db_url, "/health/live", database_url=_UNREACHABLE)
    assert response.status_code == 200
    assert response.json()["status"] == "alive"


async def test_extension_absent_returns_503(app_db_url: str) -> None:
    """DB alcanzable pero sin la extensión vector → 503 (la DB de mantenimiento no la tiene)."""
    maintenance = "postgresql+asyncpg://syntax:syntax@localhost:5432/postgres"
    response = await _get(app_db_url, "/health/ready", database_url=maintenance)
    assert response.status_code == 503
    assert "vector" in response.json()["detail"]


async def test_not_migrated_returns_controlled_503(app_db_url: str) -> None:
    """DB alcanzable con extensión pero SIN tablas → 503 controlado (no un 500)."""
    import asyncpg

    empty_db = f"ready_empty_{uuid.uuid4().hex[:8]}"
    admin_dsn = "postgresql://syntax:syntax@localhost:5432/postgres"
    admin = await asyncpg.connect(dsn=admin_dsn)
    try:
        await admin.execute(f"CREATE DATABASE {empty_db}")
    finally:
        await admin.close()
    try:
        conn = await asyncpg.connect(dsn=f"postgresql://syntax:syntax@localhost:5432/{empty_db}")
        try:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        finally:
            await conn.close()
        empty_url = f"postgresql+asyncpg://syntax:syntax@localhost:5432/{empty_db}"
        response = await _get(app_db_url, "/health/ready", database_url=empty_url)
        assert response.status_code == 503
        assert "embedding" in response.json()["detail"]
    finally:
        admin = await asyncpg.connect(dsn=admin_dsn)
        try:
            await admin.execute(f"DROP DATABASE IF EXISTS {empty_db} WITH (FORCE)")
        finally:
            await admin.close()


async def test_readiness_times_out_on_slow_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """Una DB que no responde dentro del timeout → ReadinessError (no cuelga indefinidamente)."""
    import asyncio

    async def _hang(*args: object, **kwargs: object) -> object:
        await asyncio.sleep(10)
        return None

    monkeypatch.setattr("app.core.readiness.asyncpg.connect", _hang)
    with pytest.raises(ReadinessError, match="no alcanzable"):
        await check_database_ready(_UNREACHABLE, 1536, timeout=0.2)


async def test_get_db_session_yields_working_session(
    monkeypatch: pytest.MonkeyPatch, app_db_url: str
) -> None:
    """deps.get_db_session cede una AsyncSession operativa (de session.py)."""
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("DATABASE_URL", app_db_url)
    get_settings.cache_clear()
    monkeypatch.setattr(session_module, "_engine", None)
    monkeypatch.setattr(session_module, "_sessionmaker", None)
    async for session in get_db_session():
        assert isinstance(session, AsyncSession)
        assert (await session.execute(text("SELECT 1"))).scalar() == 1
