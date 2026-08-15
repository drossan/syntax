"""Tests de app.infra.db.session — aislamiento RLS a nivel de sesión (tarea 07).

Integración OBLIGATORIA contra Postgres real como `syntax_app` (no-superuser → RLS aplica).
Traza a CU-BE-03 (autorización y aislamiento tenant) + FR-013/014/015 + NFR-002.

Estrategia (H5): filas COMMITEADAS + limpieza por TRUNCATE (no rollback envolvente, que haría
el footgun vacuo). `app_engine` tiene pool_size=1 → la conexión se reutiliza (footgun testeable).
"""

import uuid

import pytest
import pytest_asyncio
from app.core.config import get_settings
from app.infra.db.session import (
    get_sessionmaker,
    global_scope,
    tenant_scope,
)
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

_INSERT_TICKET = text(
    "INSERT INTO ticket (id, tenant_id, subject, status, priority, created_at, updated_at) "
    "VALUES (gen_random_uuid(), :t, 'subj', 'new', 'normal', now(), now())"
)
_COUNT_TICKETS = text("SELECT count(*) FROM ticket")


@pytest_asyncio.fixture
async def seeded_tenants(superuser_engine: AsyncEngine) -> tuple[uuid.UUID, uuid.UUID]:
    """Dos tenants (A, B) con un ticket cada uno + un kb_document global, COMMITEADOS.

    Sembrado como superuser (RLS no aplica). Limpieza por TRUNCATE en el teardown.
    """
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    async with superuser_engine.begin() as conn:
        for tenant_id in (tenant_a, tenant_b):
            await conn.execute(
                text(
                    "INSERT INTO tenant (id, slug, name, status, created_at, updated_at) "
                    "VALUES (:id, :slug, 't', 'active', now(), now())"
                ),
                {"id": tenant_id, "slug": str(tenant_id)},
            )
            await conn.execute(_INSERT_TICKET, {"t": tenant_id})
        await conn.execute(
            text(
                "INSERT INTO kb_document "
                "(id, uc_id, domain, package, estado, title, source_url, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :uc, 'media-and-dam', 'pkg', 'active', 't', 'u', now(), now())"
            ),
            {"uc": str(tenant_a)},
        )
    yield tenant_a, tenant_b
    async with superuser_engine.begin() as conn:
        await conn.execute(text("TRUNCATE ticket, tenant, kb_document CASCADE"))


def test_sessionmaker_does_not_expire_on_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    """El async_sessionmaker se crea con expire_on_commit=False (perezoso, sin conectar).

    Autónomo: fija JWT_SECRET para no depender de un `.env` ambiental.
    """
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()
    assert get_sessionmaker().kw["expire_on_commit"] is False


def test_get_engine_is_lazy_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_engine() crea un AsyncEngine (sin conectar) y lo memoiza (misma instancia)."""
    from app.infra.db.session import get_engine

    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()
    engine = get_engine()
    assert isinstance(engine, AsyncEngine)
    assert get_engine() is engine


async def test_tenant_scope_isolates_reads(
    app_engine: AsyncEngine, seeded_tenants: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """Con el contexto en un tenant solo se ven sus filas."""
    tenant_a, tenant_b = seeded_tenants
    maker = async_sessionmaker(app_engine, expire_on_commit=False)
    async with maker() as session, tenant_scope(session, tenant_a):
        assert (await session.execute(_COUNT_TICKETS)).scalar() == 1
    async with maker() as session, tenant_scope(session, tenant_b):
        assert (await session.execute(_COUNT_TICKETS)).scalar() == 1


async def test_pool_reuse_does_not_leak_tenant_context(
    app_engine: AsyncEngine, seeded_tenants: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """Reúso de conexión del pool no filtra: tras un contexto A, sin contexto se ven 0 filas."""
    tenant_a, _ = seeded_tenants
    maker = async_sessionmaker(app_engine, expire_on_commit=False)
    async with maker() as session, tenant_scope(session, tenant_a):
        assert (await session.execute(_COUNT_TICKETS)).scalar() == 1
    # misma conexión del pool (pool_size=1), sin contexto → fail-closed (el SET LOCAL no persiste).
    async with maker() as session, session.begin():
        assert (await session.execute(_COUNT_TICKETS)).scalar() == 0


async def test_global_scope_sees_all_tenants(
    app_engine: AsyncEngine, seeded_tenants: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """El ámbito global (bypass por transacción) ve filas de todos los tenants."""
    maker = async_sessionmaker(app_engine, expire_on_commit=False)
    async with maker() as session, global_scope(session):
        assert (await session.execute(_COUNT_TICKETS)).scalar() == 2


async def test_bypass_does_not_leak_to_next_transaction(
    app_engine: AsyncEngine, seeded_tenants: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """El bypass global no se arrastra: la siguiente transacción con tenant A solo ve A."""
    tenant_a, _ = seeded_tenants
    maker = async_sessionmaker(app_engine, expire_on_commit=False)
    async with maker() as session, global_scope(session):
        assert (await session.execute(_COUNT_TICKETS)).scalar() == 2
    async with maker() as session, tenant_scope(session, tenant_a):
        assert (await session.execute(_COUNT_TICKETS)).scalar() == 1


async def test_no_context_is_fail_closed(
    app_engine: AsyncEngine, seeded_tenants: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """Sin GUC de tenant no se ve nada (0 filas, sin excepción; current_setting missing_ok)."""
    maker = async_sessionmaker(app_engine, expire_on_commit=False)
    async with maker() as session, session.begin():
        assert (await session.execute(_COUNT_TICKETS)).scalar() == 0


async def test_kb_is_not_filtered_by_tenant(
    app_engine: AsyncEngine, seeded_tenants: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """Las tablas KB (globales) no filtran por tenant: visibles bajo cualquier contexto."""
    tenant_a, _ = seeded_tenants
    maker = async_sessionmaker(app_engine, expire_on_commit=False)
    async with maker() as session, tenant_scope(session, tenant_a):
        docs = (await session.execute(text("SELECT count(*) FROM kb_document"))).scalar()
    assert docs == 1


async def test_write_is_scoped_to_context_tenant(
    app_engine: AsyncEngine, seeded_tenants: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """Una escritura con el tenant del contexto se acepta (WITH CHECK)."""
    tenant_a, _ = seeded_tenants
    maker = async_sessionmaker(app_engine, expire_on_commit=False)
    async with maker() as session, tenant_scope(session, tenant_a):
        await session.execute(_INSERT_TICKET, {"t": tenant_a})
        assert (await session.execute(_COUNT_TICKETS)).scalar() == 2  # seed de A + nuevo


async def test_write_cross_tenant_is_rejected(
    app_engine: AsyncEngine, seeded_tenants: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """Escribir una fila con tenant_id de OTRO tenant se rechaza (WITH CHECK), no se reescribe."""
    tenant_a, tenant_b = seeded_tenants
    maker = async_sessionmaker(app_engine, expire_on_commit=False)
    with pytest.raises(DBAPIError):
        async with maker() as session, tenant_scope(session, tenant_a):
            await session.execute(_INSERT_TICKET, {"t": tenant_b})  # tenant B bajo contexto A


async def test_malformed_tenant_id_raises_controlled_error(
    app_engine: AsyncEngine, seeded_tenants: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """Un tenant_id no-UUID falla de forma controlada (ValueError), no con error crudo de PG."""
    maker = async_sessionmaker(app_engine, expire_on_commit=False)
    async with maker() as session:
        with pytest.raises(ValueError, match="UUID"):
            async with tenant_scope(session, "not-a-uuid"):
                pass


async def test_context_discarded_on_rollback(
    app_engine: AsyncEngine, seeded_tenants: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """El contexto se descarta en ROLLBACK: la conexión reutilizada no ve el tenant anterior."""
    tenant_a, _ = seeded_tenants
    maker = async_sessionmaker(app_engine, expire_on_commit=False)
    with pytest.raises(RuntimeError):
        async with maker() as session, tenant_scope(session, tenant_a):
            raise RuntimeError("boom")
    async with maker() as session, session.begin():
        assert (await session.execute(_COUNT_TICKETS)).scalar() == 0


@pytest.mark.parametrize(("value", "expected"), [("on", 2), ("true", 0), ("1", 0)])
async def test_only_literal_on_activates_bypass(
    app_engine: AsyncEngine,
    seeded_tenants: tuple[uuid.UUID, uuid.UUID],
    value: str,
    expected: int,
) -> None:
    """Solo el literal 'on' activa el bypass; otros valores no (sin contexto → fail-closed)."""
    maker = async_sessionmaker(app_engine, expire_on_commit=False)
    async with maker() as session, session.begin():
        await session.execute(text("SELECT set_config('app.bypass_rls', :v, true)"), {"v": value})
        assert (await session.execute(_COUNT_TICKETS)).scalar() == expected
