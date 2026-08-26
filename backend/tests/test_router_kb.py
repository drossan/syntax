"""Tests de integración del router `kb` (tarea `backend-kb-retriever-07`): superficie HTTP sobre el
adaptador REAL (`PgVectorStore`). KB es global (sin RLS) — `superuser_engine` de sobra, igual que
`test_router_admin.py`.

**Regresión legítima, no un test roto**: la versión anterior de este fichero asertaba el vacío del
adaptador stub de la tarea `backend-routers-core-09` como comportamiento esperado — era su andamio,
no un contrato a preservar.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest_asyncio
from app.core.config import Settings, get_settings
from app.core.deps import get_db_session, get_embeddings_port
from app.core.security import JWT_ALGORITHM, create_access_token, hash_password
from app.domain.entities.enums import (
    KbDomain,
    KbEstado,
    Package,
    RoleKind,
    TenantStatus,
    UserStatus,
)
from app.domain.entities.identity import Role, Tenant, User, UserTenantMembership
from app.domain.errors import PortError
from app.domain.ports.vector import ChunkWrite, KBDocumentDraft
from app.infra.db.models.kb import EMBEDDING_DIM_LITERAL
from app.infra.db.repositories import (
    SqlAlchemyRoleRepository,
    SqlAlchemyTenantRepository,
    SqlAlchemyUserRepository,
    SqlAlchemyUserTenantMembershipRepository,
)
from app.infra.vector import SqlAlchemyKBIndexWriter
from app.ingestion.parser import GLOSARIO_UC_ID_PREFIX
from app.main import create_app
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

_JWT_SECRET = "x" * 32
_TTL = 900
_EMBEDDING_MODEL = "text-embedding-3-small"


def _settings() -> Settings:
    return Settings(_env_file=None, jwt_secret=_JWT_SECRET, app_env="production", cors_origins=[])


_TRUNCATE_TABLES = (
    "TRUNCATE user_tenant, refresh_session, auth_token, user_role, role_capability, "
    'capability, "user", role, tenant, embedding, kb_chunk, kb_document RESTART IDENTITY CASCADE'
)


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables(superuser_engine: AsyncEngine) -> AsyncIterator[None]:
    async with superuser_engine.begin() as conn:
        await conn.execute(text(_TRUNCATE_TABLES))
    yield
    async with superuser_engine.begin() as conn:
        await conn.execute(text(_TRUNCATE_TABLES))


@pytest_asyncio.fixture
async def db(superuser_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with async_sessionmaker(superuser_engine, expire_on_commit=False)() as s:
        yield s


def _axis(index: int, sign: float = 1.0) -> list[float]:
    vector = [0.0] * EMBEDDING_DIM_LITERAL
    vector[index] = sign
    return vector


class _FakeEmbeddingModel:
    """Doble del puerto de embeddings para los tests HTTP: devuelve un vector fijo, o levanta el
    error configurado (para el escenario 502)."""

    def __init__(self, vector: list[float] | None = None, error: Exception | None = None) -> None:
        self._vector = vector if vector is not None else _axis(0)
        self._error = error
        self.queries: list[str] = []

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise AssertionError("el router no debe embeber documentos")

    async def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        if self._error is not None:
            raise self._error
        return self._vector


@pytest_asyncio.fixture
async def app(superuser_engine: AsyncEngine) -> AsyncIterator[FastAPI]:
    test_app = create_app(_settings())

    async def _override_session() -> AsyncIterator[AsyncSession]:
        async with async_sessionmaker(superuser_engine, expire_on_commit=False)() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    test_app.dependency_overrides[get_db_session] = _override_session
    test_app.dependency_overrides[get_settings] = _settings
    test_app.dependency_overrides[get_embeddings_port] = lambda: _FakeEmbeddingModel()
    yield test_app
    test_app.dependency_overrides.clear()


def _client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _make_tenant() -> Tenant:
    return Tenant(
        id=uuid.uuid4(), slug=f"t-{uuid.uuid4()}", name="Tenant", status=TenantStatus.active
    )


async def _make_user(db: AsyncSession) -> User:
    return await SqlAlchemyUserRepository(db).add(
        User(
            id=uuid.uuid4(),
            email=f"u-{uuid.uuid4()}@example.com",
            password_hash=hash_password("pw"),
        )
    )


async def _add_membership(db: AsyncSession, *, user_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    await SqlAlchemyUserTenantMembershipRepository(db).add(
        UserTenantMembership(user_id=user_id, tenant_id=tenant_id, status=UserStatus.active)
    )


async def _grant_capability(
    db: AsyncSession, *, user_id: uuid.UUID, tenant_id: uuid.UUID, capability: str
) -> None:
    role_repo = SqlAlchemyRoleRepository(db)
    role = await role_repo.add(
        Role(
            id=uuid.uuid4(), name=f"role-{uuid.uuid4()}", kind=RoleKind.tenant, tenant_id=tenant_id
        )
    )
    existing_capability_id = (
        await db.execute(text("SELECT id FROM capability WHERE name = :name"), {"name": capability})
    ).scalar_one_or_none()
    if existing_capability_id is None:
        capability_id = uuid.uuid4()
        await db.execute(
            text("INSERT INTO capability (id, name, scope) VALUES (:id, :name, 'tenant')"),
            {"id": capability_id, "name": capability},
        )
    else:
        capability_id = existing_capability_id
    await db.execute(
        text("INSERT INTO role_capability (role_id, capability_id) VALUES (:r, :c)"),
        {"r": role.id, "c": capability_id},
    )
    await role_repo.assign(user_id, role.id, tenant_id)
    await db.commit()


def _access_token(user_id: uuid.UUID, tenant_id: uuid.UUID) -> str:
    return create_access_token(
        str(user_id),
        str(tenant_id),
        secret=_JWT_SECRET,
        algorithm=JWT_ALGORITHM,
        ttl=_TTL,
        now=datetime.now(UTC),
    )


async def _agent(db: AsyncSession, *, tenant: Tenant, with_capability: bool) -> str:
    user = await _make_user(db)
    await _add_membership(db, user_id=user.id, tenant_id=tenant.id)
    if with_capability:
        await _grant_capability(db, user_id=user.id, tenant_id=tenant.id, capability="kb.read")
    return _access_token(user.id, tenant.id)


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _seed(
    db: AsyncSession,
    uc_id: str,
    vector: list[float],
    *,
    domain: KbDomain = KbDomain.authoring_and_editor,
    package: Package = Package.syntax_cx,
    estado: KbEstado = KbEstado.draft,
    content: str = "contenido del chunk",
    title: str = "Título",
) -> None:
    writer = SqlAlchemyKBIndexWriter(db)
    await writer.upsert_document(
        KBDocumentDraft(
            uc_id=uc_id,
            domain=domain,
            package=package,
            estado=estado,
            title=title,
            source_url=f"packages/x/docs/aiup/use-cases/{uc_id}.md",
        ),
        [
            ChunkWrite(
                ordinal=0,
                section_type="comportamiento",
                content=content,
                token_count=len(content.split()),
                vector=vector,
                model=_EMBEDDING_MODEL,
            )
        ],
    )
    await db.commit()


# ── autorización (KB global, indiferente al tenant) ──


async def test_search_without_kb_read_is_forbidden(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token = await _agent(db, tenant=tenant, with_capability=False)

    async with _client(app) as c:
        r = await c.get("/api/v1/kb/search", params={"q": "algo"}, headers=_auth_header(token))

    assert r.status_code == 403
    assert r.headers["content-type"].startswith("application/problem+json")


async def test_list_documents_without_kb_read_is_forbidden(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token = await _agent(db, tenant=tenant, with_capability=False)

    async with _client(app) as c:
        r = await c.get("/api/v1/kb/documents", headers=_auth_header(token))

    assert r.status_code == 403


async def test_get_document_without_kb_read_is_forbidden(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token = await _agent(db, tenant=tenant, with_capability=False)

    async with _client(app) as c:
        r = await c.get("/api/v1/kb/documents/UC-API-001", headers=_auth_header(token))

    assert r.status_code == 403


async def test_search_does_not_depend_on_the_subjects_tenant(
    app: FastAPI, db: AsyncSession
) -> None:
    """KB no filtra por tenant (recurso global) — dos subjects de tenants DISTINTOS, ambos con
    kb.read, obtienen la misma respuesta."""
    await _seed(db, "UC-1", _axis(0))
    tenant_a = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    tenant_b = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token_a = await _agent(db, tenant=tenant_a, with_capability=True)
    token_b = await _agent(db, tenant=tenant_b, with_capability=True)

    async with _client(app) as c:
        r_a = await c.get("/api/v1/kb/search", params={"q": "algo"}, headers=_auth_header(token_a))
        r_b = await c.get("/api/v1/kb/search", params={"q": "algo"}, headers=_auth_header(token_b))

    assert r_a.status_code == r_b.status_code == 200
    assert r_a.json() == r_b.json()


# ── búsqueda: camino feliz, orden y snippet ──


async def test_search_returns_documents_ordered_by_relevance(
    app: FastAPI, db: AsyncSession
) -> None:
    """CU-BE-12 · *La búsqueda devuelve documentos ordenados por relevancia* (end-to-end vía HTTP)."""
    lejos = _axis(1)
    await _seed(db, "UC-LEJOS", lejos)
    await _seed(db, "UC-CERCA", _axis(0))
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token = await _agent(db, tenant=tenant, with_capability=True)

    async with _client(app) as c:
        r = await c.get("/api/v1/kb/search", params={"q": "algo"}, headers=_auth_header(token))

    assert r.status_code == 200
    body = r.json()
    assert [item["uc_id"] for item in body["items"]] == ["UC-CERCA", "UC-LEJOS"]
    assert body["items"][0]["score"] > body["items"][1]["score"]
    assert body["total"] == 2


async def test_search_includes_a_non_empty_snippet(app: FastAPI, db: AsyncSession) -> None:
    """CU-BE-12 · *El resultado incluye un fragmento de la sección que lo justifica*."""
    await _seed(db, "UC-1", _axis(0), content="El editor permite subir vídeos de hasta 2 GB.")
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token = await _agent(db, tenant=tenant, with_capability=True)

    async with _client(app) as c:
        r = await c.get("/api/v1/kb/search", params={"q": "algo"}, headers=_auth_header(token))

    assert r.json()["items"][0]["snippet"] == "El editor permite subir vídeos de hasta 2 GB."


async def test_search_applies_filters(app: FastAPI, db: AsyncSession) -> None:
    await _seed(db, "UC-MEDIA", _axis(0), domain=KbDomain.media_and_dam)
    await _seed(db, "UC-FORMS", _axis(0), domain=KbDomain.forms_and_submissions)
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token = await _agent(db, tenant=tenant, with_capability=True)

    async with _client(app) as c:
        r = await c.get(
            "/api/v1/kb/search",
            params={"q": "algo", "domain": KbDomain.media_and_dam.value},
            headers=_auth_header(token),
        )

    body = r.json()
    assert [item["uc_id"] for item in body["items"]] == ["UC-MEDIA"]


async def test_search_without_matches_returns_an_empty_page(app: FastAPI, db: AsyncSession) -> None:
    """CU-BE-12 · *Una búsqueda sin coincidencias devuelve vacío, no un error*."""
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token = await _agent(db, tenant=tenant, with_capability=True)

    async with _client(app) as c:
        r = await c.get("/api/v1/kb/search", params={"q": "algo"}, headers=_auth_header(token))

    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0


# ── búsqueda: entrada inválida (Outline: vacío · solo espacios · demasiado larga) ──


async def test_search_without_q_is_rejected(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token = await _agent(db, tenant=tenant, with_capability=True)

    async with _client(app) as c:
        r = await c.get("/api/v1/kb/search", headers=_auth_header(token))

    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")


async def test_search_with_empty_q_is_rejected(app: FastAPI, db: AsyncSession) -> None:
    """CU-BE-12 · *Un término de búsqueda inutilizable se rechaza sin consultar al proveedor* — vacío."""
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token = await _agent(db, tenant=tenant, with_capability=True)

    async with _client(app) as c:
        r = await c.get("/api/v1/kb/search", params={"q": ""}, headers=_auth_header(token))

    assert r.status_code == 422


async def test_search_with_whitespace_only_q_is_rejected(app: FastAPI, db: AsyncSession) -> None:
    """CU-BE-12 · *…* — solo espacios."""
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token = await _agent(db, tenant=tenant, with_capability=True)

    async with _client(app) as c:
        r = await c.get("/api/v1/kb/search", params={"q": "   "}, headers=_auth_header(token))

    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")


async def test_search_with_a_too_long_q_is_rejected(app: FastAPI, db: AsyncSession) -> None:
    """CU-BE-12 · *…* — más largo que el máximo admitido (contrato: `maxLength: 512`)."""
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token = await _agent(db, tenant=tenant, with_capability=True)

    async with _client(app) as c:
        r = await c.get("/api/v1/kb/search", params={"q": "x" * 513}, headers=_auth_header(token))

    assert r.status_code == 422


async def test_search_with_an_invalid_q_does_not_call_the_embeddings_provider(
    app: FastAPI, db: AsyncSession
) -> None:
    """CU-BE-12 · *…* — «no se consume ninguna llamada al proveedor de embeddings»."""
    fake = _FakeEmbeddingModel()
    app.dependency_overrides[get_embeddings_port] = lambda: fake
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token = await _agent(db, tenant=tenant, with_capability=True)

    async with _client(app) as c:
        await c.get("/api/v1/kb/search", params={"q": "   "}, headers=_auth_header(token))
        await c.get("/api/v1/kb/search", params={"q": ""}, headers=_auth_header(token))

    assert fake.queries == []


# ── búsqueda: fallo del proveedor no se disfraza de KB vacía ──


async def test_search_provider_failure_returns_502(app: FastAPI, db: AsyncSession) -> None:
    """CU-BE-12 · *Un fallo del proveedor de embeddings no se disfraza de KB vacía* (end-to-end)."""
    app.dependency_overrides[get_embeddings_port] = lambda: _FakeEmbeddingModel(
        error=PortError("proveedor caído")
    )
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token = await _agent(db, tenant=tenant, with_capability=True)

    async with _client(app) as c:
        r = await c.get("/api/v1/kb/search", params={"q": "algo"}, headers=_auth_header(token))

    assert r.status_code == 502
    assert r.headers["content-type"].startswith("application/problem+json")


# ── listado ──


async def test_list_documents_returns_seeded_documents(app: FastAPI, db: AsyncSession) -> None:
    await _seed(db, "UC-1", _axis(0))
    await _seed(db, "UC-2", _axis(0))
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token = await _agent(db, tenant=tenant, with_capability=True)

    async with _client(app) as c:
        r = await c.get("/api/v1/kb/documents", headers=_auth_header(token))

    assert r.status_code == 200
    body = r.json()
    assert [item["uc_id"] for item in body["items"]] == ["UC-1", "UC-2"]
    assert body["total"] == 2


async def test_list_documents_on_an_empty_kb_returns_an_empty_page(
    app: FastAPI, db: AsyncSession
) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token = await _agent(db, tenant=tenant, with_capability=True)

    async with _client(app) as c:
        r = await c.get("/api/v1/kb/documents", headers=_auth_header(token))

    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0


async def test_list_documents_does_not_require_the_embeddings_provider(
    app: FastAPI, db: AsyncSession
) -> None:
    """CU-BE-12 · *Listar documentos no requiere el proveedor de embeddings* — una config de
    embeddings inservible NO tumba `/kb/documents`. Fija la instanciación PEREZOSA del adaptador de
    embeddings dentro de `get_vector_store()` (`## Spec` de `-07`)."""
    await _seed(db, "UC-1", _axis(0))
    app.dependency_overrides[get_embeddings_port] = lambda: _FakeEmbeddingModel(
        error=PortError("config de embeddings inservible")
    )
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token = await _agent(db, tenant=tenant, with_capability=True)

    async with _client(app) as c:
        r = await c.get("/api/v1/kb/documents", headers=_auth_header(token))

    assert r.status_code == 200
    assert r.json()["total"] == 1


async def test_list_documents_is_stable_between_pages(app: FastAPI, db: AsyncSession) -> None:
    """CU-BE-12 · *El listado de documentos es estable entre páginas* (end-to-end vía HTTP)."""
    expected = [f"UC-{i:02d}" for i in range(1, 6)]
    for uc_id in expected:
        await _seed(db, uc_id, _axis(0))
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token = await _agent(db, tenant=tenant, with_capability=True)

    seen: list[str] = []
    async with _client(app) as c:
        for page in (1, 2, 3):
            r = await c.get(
                "/api/v1/kb/documents",
                params={"page": page, "page_size": 2},
                headers=_auth_header(token),
            )
            seen.extend(item["uc_id"] for item in r.json()["items"])

    assert seen == expected


async def test_list_documents_includes_glossaries(app: FastAPI, db: AsyncSession) -> None:
    """CU-BE-12 · *Los glosarios son documentos de pleno derecho* (end-to-end vía HTTP), con su
    `uc_id` sintético en la ruta de detalle."""
    glosario_id = f"{GLOSARIO_UC_ID_PREFIX}media-and-dam"
    await _seed(db, "UC-1", _axis(0))
    await _seed(db, glosario_id, _axis(0), domain=KbDomain.media_and_dam, title="Glosario")
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token = await _agent(db, tenant=tenant, with_capability=True)

    async with _client(app) as c:
        list_response = await c.get("/api/v1/kb/documents", headers=_auth_header(token))
        detail_response = await c.get(
            f"/api/v1/kb/documents/{glosario_id}", headers=_auth_header(token)
        )

    assert glosario_id in {item["uc_id"] for item in list_response.json()["items"]}
    assert detail_response.status_code == 200
    assert detail_response.json()["title"] == "Glosario"


# ── detalle ──


async def test_get_document_returns_the_seeded_document(app: FastAPI, db: AsyncSession) -> None:
    await _seed(db, "UC-API-001", _axis(0), title="Un caso de uso")
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token = await _agent(db, tenant=tenant, with_capability=True)

    async with _client(app) as c:
        r = await c.get("/api/v1/kb/documents/UC-API-001", headers=_auth_header(token))

    assert r.status_code == 200
    assert r.json()["title"] == "Un caso de uso"


async def test_get_document_returns_404(app: FastAPI, db: AsyncSession) -> None:
    """CU-BE-12 · *Abrir un documento inexistente* (end-to-end vía HTTP)."""
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token = await _agent(db, tenant=tenant, with_capability=True)

    async with _client(app) as c:
        r = await c.get("/api/v1/kb/documents/UC-API-001", headers=_auth_header(token))

    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")


# ── fronteras de paginación y longitud de `q` (destapadas por el gate de mutation) ──


async def test_search_with_a_single_character_q_is_accepted(app: FastAPI, db: AsyncSession) -> None:
    """Frontera `min_length=1`: un término de un solo carácter NO vacío es válido."""
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token = await _agent(db, tenant=tenant, with_capability=True)

    async with _client(app) as c:
        r = await c.get("/api/v1/kb/search", params={"q": "a"}, headers=_auth_header(token))

    assert r.status_code == 200


async def test_search_rejects_page_zero(app: FastAPI, db: AsyncSession) -> None:
    """Frontera `page: ge=1`: `page=0` no es una página válida."""
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token = await _agent(db, tenant=tenant, with_capability=True)

    async with _client(app) as c:
        r = await c.get(
            "/api/v1/kb/search", params={"q": "algo", "page": 0}, headers=_auth_header(token)
        )

    assert r.status_code == 422


async def test_list_documents_rejects_page_zero(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token = await _agent(db, tenant=tenant, with_capability=True)

    async with _client(app) as c:
        r = await c.get("/api/v1/kb/documents", params={"page": 0}, headers=_auth_header(token))

    assert r.status_code == 422


async def test_search_defaults_page_size_to_twenty(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token = await _agent(db, tenant=tenant, with_capability=True)

    async with _client(app) as c:
        r = await c.get("/api/v1/kb/search", params={"q": "algo"}, headers=_auth_header(token))

    assert r.json()["page_size"] == 20


async def test_list_documents_defaults_page_size_to_twenty(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token = await _agent(db, tenant=tenant, with_capability=True)

    async with _client(app) as c:
        r = await c.get("/api/v1/kb/documents", headers=_auth_header(token))

    assert r.json()["page_size"] == 20


async def test_search_page_size_bounds(app: FastAPI, db: AsyncSession) -> None:
    """Frontera `page_size: ge=1, le=100` — 1 y 100 son válidos; 0 y 101 no."""
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token = await _agent(db, tenant=tenant, with_capability=True)

    async with _client(app) as c:
        ok_min = await c.get(
            "/api/v1/kb/search",
            params={"q": "algo", "page_size": 1},
            headers=_auth_header(token),
        )
        ok_max = await c.get(
            "/api/v1/kb/search",
            params={"q": "algo", "page_size": 100},
            headers=_auth_header(token),
        )
        bad_min = await c.get(
            "/api/v1/kb/search",
            params={"q": "algo", "page_size": 0},
            headers=_auth_header(token),
        )
        bad_max = await c.get(
            "/api/v1/kb/search",
            params={"q": "algo", "page_size": 101},
            headers=_auth_header(token),
        )

    assert ok_min.status_code == 200
    assert ok_max.status_code == 200
    assert bad_min.status_code == 422
    assert bad_max.status_code == 422


async def test_list_documents_page_size_bounds(app: FastAPI, db: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(db).add(_make_tenant())
    await db.commit()
    token = await _agent(db, tenant=tenant, with_capability=True)

    async with _client(app) as c:
        ok_min = await c.get(
            "/api/v1/kb/documents", params={"page_size": 1}, headers=_auth_header(token)
        )
        ok_max = await c.get(
            "/api/v1/kb/documents", params={"page_size": 100}, headers=_auth_header(token)
        )
        bad_min = await c.get(
            "/api/v1/kb/documents", params={"page_size": 0}, headers=_auth_header(token)
        )
        bad_max = await c.get(
            "/api/v1/kb/documents", params={"page_size": 101}, headers=_auth_header(token)
        )

    assert ok_min.status_code == 200
    assert ok_max.status_code == 200
    assert bad_min.status_code == 422
    assert bad_max.status_code == 422
