"""Tests de integración de `PgVectorStore.list_documents`/`get_document` (tarea
`backend-kb-retriever-02`). Postgres real vía `superuser_engine` — KB es GLOBAL (sin RLS), así que
aquí no hay aislamiento de tenant que verificar (mismo criterio que `tests/test_vector_adapter.py`).

Escenarios de `CU-BE-12` que materializa este módulo: *Abrir un documento existente*, *Un documento sin
fecha de actualización se sirve igualmente*, *Abrir un documento inexistente*, *Un identificador con
forma inesperada no rompe la consulta*, *Los glosarios son documentos de pleno derecho*, *Un glosario se
abre por su identificador*, *El listado de documentos es estable entre páginas*, *Pedir una página más
allá del listado*, *Un fallo de la base de datos no se disfraza de KB vacía* y la mitad de *Los filtros
acotan la búsqueda* que corresponde a `list_documents` (la de `/kb/search` es de `-06`).

Los documentos se insertan con el ORM **directamente**, no con `SqlAlchemyKBIndexWriter`: este módulo
verifica el adaptador de LECTURA, y hacerlo pasar por el de escritura ataría sus tests a un segundo
adaptador que no está bajo prueba aquí.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from app.domain.entities.enums import KbDomain, KbEstado, Package
from app.domain.errors import PortError
from app.infra.db.models.enums import KbDomain as KbDomainOrm
from app.infra.db.models.enums import KbEstado as KbEstadoOrm
from app.infra.db.models.kb import KBDocument as KBDocumentModel
from app.infra.vectorstore.pgvector import PgVectorStore
from app.ingestion.parser import GLOSARIO_UC_ID_PREFIX
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_TRUNCATE_TABLES = "TRUNCATE embedding, kb_chunk, kb_document RESTART IDENTITY CASCADE"


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables(superuser_engine: AsyncEngine) -> AsyncIterator[None]:
    async with superuser_engine.begin() as conn:
        await conn.execute(text(_TRUNCATE_TABLES))
    yield
    async with superuser_engine.begin() as conn:
        await conn.execute(text(_TRUNCATE_TABLES))


@pytest_asyncio.fixture
async def session(superuser_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with async_sessionmaker(superuser_engine, expire_on_commit=False)() as s:
        yield s


@pytest_asyncio.fixture
async def broken_session() -> AsyncIterator[AsyncSession]:
    """Sesión sobre un engine apuntando a un puerto sin nadie escuchando: la primera query real falla
    en infra (no en validación de datos) — para probar que cada método envuelve en `PortError`."""
    broken_engine = create_async_engine("postgresql+asyncpg://x:y@localhost:59999/x")
    try:
        async with async_sessionmaker(broken_engine, expire_on_commit=False)() as s:
            yield s
    finally:
        await broken_engine.dispose()


async def _insert(
    session: AsyncSession,
    uc_id: str,
    *,
    domain: KbDomain = KbDomain.authoring_and_editor,
    package: Package = Package.syntax_cx,
    estado: KbEstado = KbEstado.active,
    title: str = "Título",
    source_url: str = "packages/x/docs/aiup/use-cases/UC-1.md",
    updated: datetime | None = None,
) -> None:
    """Inserta una fila de `kb_document`. `package` es `String` en el ORM (no un enum de Postgres),
    de ahí el `.value`; `domain`/`estado` sí son enums ORM y se convierten por valor."""
    session.add(
        KBDocumentModel(
            uc_id=uc_id,
            domain=KbDomainOrm(domain.value),
            package=package.value,
            estado=KbEstadoOrm(estado.value),
            title=title,
            source_url=source_url,
            updated=updated,
        )
    )
    await session.commit()


# ── get_document ──


async def test_get_document_returns_the_document_with_all_its_fields(session: AsyncSession) -> None:
    """CU-BE-12 · *Abrir un documento existente*."""
    updated = datetime(2026, 8, 20, 10, 30, tzinfo=UTC)
    await _insert(
        session,
        "UC-API-081",
        domain=KbDomain.media_and_dam,
        package=Package.syntax_api,
        estado=KbEstado.draft,
        title="Subida de activos",
        source_url="packages/api/docs/aiup/use-cases/UC-API-081.md",
        updated=updated,
    )
    store = PgVectorStore(session)

    document = await store.get_document("UC-API-081")

    assert document is not None
    assert document.uc_id == "UC-API-081"
    assert document.domain is KbDomain.media_and_dam
    assert document.package is Package.syntax_api
    assert document.estado is KbEstado.draft
    assert document.title == "Subida de activos"
    assert document.source_url == "packages/api/docs/aiup/use-cases/UC-API-081.md"
    assert document.updated == updated


async def test_get_document_without_updated_date_is_served_anyway(session: AsyncSession) -> None:
    """CU-BE-12 · *Un documento sin fecha de actualización se sirve igualmente* — la fecha llega
    ausente (`None`), no como error."""
    await _insert(session, "UC-1", title="Sin fecha", updated=None)
    store = PgVectorStore(session)

    document = await store.get_document("UC-1")

    assert document is not None
    assert document.title == "Sin fecha"
    assert document.updated is None


async def test_get_document_returns_none_for_an_unknown_uc_id(session: AsyncSession) -> None:
    """CU-BE-12 · *Abrir un documento inexistente* — `None`; el 404 lo traduce el router."""
    await _insert(session, "UC-1")
    store = PgVectorStore(session)

    assert await store.get_document("UC-NO-EXISTE") is None


@pytest.mark.parametrize(
    "uc_id",
    ["'; DROP TABLE kb_document; --", "UC-%", "UC_1", "", "  ", "UC-1\x00"],
)
async def test_get_document_with_an_unexpected_shaped_identifier_does_not_break(
    session: AsyncSession, uc_id: str
) -> None:
    """CU-BE-12 · *Un identificador con forma inesperada no rompe la consulta*.

    Cubre los comodines de `LIKE` (`%`/`_`): si la implementación usara `LIKE` en vez de `=`, `UC-%`
    y `UC_1` casarían con `UC-1` y devolverían un documento en vez de `None`.
    """
    await _insert(session, "UC-1")
    store = PgVectorStore(session)

    assert await store.get_document(uc_id) is None


async def test_get_document_opens_a_glossary_by_its_synthetic_identifier(
    session: AsyncSession,
) -> None:
    """CU-BE-12 · *Un glosario se abre por su identificador* (RN-9) — el `uc_id` sintético es un
    identificador válido de la API, sin ninguna rama especial en el adaptador."""
    uc_id = f"{GLOSARIO_UC_ID_PREFIX}media-and-dam"
    await _insert(session, uc_id, domain=KbDomain.media_and_dam, title="Glosario de media")
    store = PgVectorStore(session)

    document = await store.get_document(uc_id)

    assert document is not None
    assert document.uc_id == uc_id
    assert document.title == "Glosario de media"


async def test_get_document_wraps_infrastructure_failure_in_port_error(
    broken_session: AsyncSession,
) -> None:
    """CU-BE-12 · *Un fallo de la base de datos no se disfraza de KB vacía* — `PortError` (→ 502),
    nunca `None`, que el router traduciría a un 404 mentiroso."""
    store = PgVectorStore(broken_session)

    with pytest.raises(PortError):
        await store.get_document("UC-1")


# ── list_documents ──


async def test_list_documents_returns_every_document_with_its_total(session: AsyncSession) -> None:
    await _insert(session, "UC-1")
    await _insert(session, "UC-2")
    store = PgVectorStore(session)

    items, total = await store.list_documents()

    assert [d.uc_id for d in items] == ["UC-1", "UC-2"]
    assert total == 2


async def test_list_documents_is_ordered_by_uc_id_ascending(session: AsyncSession) -> None:
    """CU-BE-12 · RN-6 (*El listado de documentos es estable entre páginas*) — orden determinista.

    Se insertan en orden inverso a propósito: sin `ORDER BY` explícito Postgres puede devolverlos en
    orden de inserción, que aquí NO coincide con el esperado.
    """
    for uc_id in ["UC-9", "UC-3", "UC-7", "UC-1"]:
        await _insert(session, uc_id)
    store = PgVectorStore(session)

    items, _ = await store.list_documents()

    assert [d.uc_id for d in items] == ["UC-1", "UC-3", "UC-7", "UC-9"]


async def test_list_documents_paginates_without_repeating_or_losing_documents(
    session: AsyncSession,
) -> None:
    """CU-BE-12 · *El listado de documentos es estable entre páginas* — recorrer el listado página a
    página devuelve cada documento exactamente una vez."""
    expected = [f"UC-{i:02d}" for i in range(1, 8)]
    for uc_id in expected:
        await _insert(session, uc_id)
    store = PgVectorStore(session)

    seen: list[str] = []
    for page in (1, 2, 3):
        items, total = await store.list_documents(page=page, page_size=3)
        seen.extend(d.uc_id for d in items)
        assert total == 7

    assert seen == expected


async def test_list_documents_first_page_is_the_first_slice(session: AsyncSession) -> None:
    """La página 1 empieza en el offset 0 (un `page * page_size` en vez de `(page - 1) * page_size`
    se saltaría la primera página entera)."""
    for uc_id in ["UC-1", "UC-2", "UC-3"]:
        await _insert(session, uc_id)
    store = PgVectorStore(session)

    items, _ = await store.list_documents(page=1, page_size=2)

    assert [d.uc_id for d in items] == ["UC-1", "UC-2"]


async def test_list_documents_beyond_the_listing_returns_empty_keeping_the_total(
    session: AsyncSession,
) -> None:
    """CU-BE-12 · *Pedir una página más allá del listado* — página vacía, y el `total` sigue
    reflejando cuántos documentos hay."""
    await _insert(session, "UC-1")
    await _insert(session, "UC-2")
    store = PgVectorStore(session)

    items, total = await store.list_documents(page=5, page_size=20)

    assert items == []
    assert total == 2


async def test_list_documents_defaults_to_the_contract_page_size(session: AsyncSession) -> None:
    """El tamaño de página por defecto es **20**, el que fija el contrato compartido
    (`api-contract.md`: `page_size` ≤ 100, default 20). Se comprueba con más documentos que el
    default, o cualquier valor por defecto pasaría inadvertido."""
    for i in range(1, 24):
        await _insert(session, f"UC-{i:02d}")
    store = PgVectorStore(session)

    items, total = await store.list_documents()

    assert len(items) == 20
    assert total == 23


async def test_list_documents_on_an_empty_kb_returns_empty_and_zero(session: AsyncSession) -> None:
    store = PgVectorStore(session)

    items, total = await store.list_documents()

    assert items == []
    assert total == 0


async def test_list_documents_filters_by_domain(session: AsyncSession) -> None:
    """CU-BE-12 · *Los filtros acotan la búsqueda* (mitad de `list_documents`).

    Los otros dos dominios rodean al filtrado en el ORDEN del enum de Postgres (declarado en
    `KbDomain`): uno **antes** (`forms_and_submissions`) y otro **después** (`seo_sitemaps_and_edge`).
    Con un solo vecino por debajo, una comparación de desigualdad (`>=`) daría el mismo resultado que
    la de igualdad y el filtro parecería correcto estando roto.
    """
    await _insert(session, "UC-1", domain=KbDomain.media_and_dam)
    await _insert(session, "UC-2", domain=KbDomain.forms_and_submissions)
    await _insert(session, "UC-3", domain=KbDomain.seo_sitemaps_and_edge)
    store = PgVectorStore(session)

    items, total = await store.list_documents(domain=KbDomain.media_and_dam)

    assert [d.uc_id for d in items] == ["UC-1"]
    assert total == 1


async def test_list_documents_filters_by_package(session: AsyncSession) -> None:
    await _insert(session, "UC-1", package=Package.syntax_api)
    await _insert(session, "UC-2", package=Package.syntax_render)
    store = PgVectorStore(session)

    items, total = await store.list_documents(package=Package.syntax_render)

    assert [d.uc_id for d in items] == ["UC-2"]
    assert total == 1


async def test_list_documents_filters_by_estado(session: AsyncSession) -> None:
    await _insert(session, "UC-1", estado=KbEstado.draft)
    await _insert(session, "UC-2", estado=KbEstado.active)
    store = PgVectorStore(session)

    items, total = await store.list_documents(estado=KbEstado.draft)

    assert [d.uc_id for d in items] == ["UC-1"]
    assert total == 1


async def test_list_documents_combines_filters_by_conjunction(session: AsyncSession) -> None:
    """Los filtros combinados acotan por conjunción (`AND`), no por unión: un documento que cumple
    dos de tres restricciones NO entra."""
    await _insert(
        session,
        "UC-MATCH",
        domain=KbDomain.media_and_dam,
        package=Package.syntax_api,
        estado=KbEstado.draft,
    )
    await _insert(
        session,
        "UC-OTHER-DOMAIN",
        domain=KbDomain.forms_and_submissions,
        package=Package.syntax_api,
        estado=KbEstado.draft,
    )
    await _insert(
        session,
        "UC-OTHER-PACKAGE",
        domain=KbDomain.media_and_dam,
        package=Package.syntax_render,
        estado=KbEstado.draft,
    )
    await _insert(
        session,
        "UC-OTHER-ESTADO",
        domain=KbDomain.media_and_dam,
        package=Package.syntax_api,
        estado=KbEstado.active,
    )
    store = PgVectorStore(session)

    items, total = await store.list_documents(
        domain=KbDomain.media_and_dam, package=Package.syntax_api, estado=KbEstado.draft
    )

    assert [d.uc_id for d in items] == ["UC-MATCH"]
    assert total == 1


async def test_list_documents_total_counts_the_filtered_set_not_the_whole_corpus(
    session: AsyncSession,
) -> None:
    """El `total` se cuenta CON los filtros aplicados (y sin paginación): un `COUNT(*)` sin filtros
    haría que el front pintara páginas que no existen."""
    for i in range(1, 6):
        await _insert(session, f"UC-DRAFT-{i}", estado=KbEstado.draft)
    for i in range(1, 4):
        await _insert(session, f"UC-ACTIVE-{i}", estado=KbEstado.active)
    store = PgVectorStore(session)

    items, total = await store.list_documents(estado=KbEstado.active, page=1, page_size=2)

    assert len(items) == 2
    assert total == 3


async def test_list_documents_without_filters_returns_every_estado_and_package(
    session: AsyncSession,
) -> None:
    """Sin filtros explícitos no se filtra nada: `draft` y `active` conviven en el listado (el peso
    de `estado` es cosa de `/kb/search`, no del listado)."""
    await _insert(session, "UC-1", estado=KbEstado.draft, package=Package.syntax_ax)
    await _insert(session, "UC-2", estado=KbEstado.active, package=Package.syntax_core)
    store = PgVectorStore(session)

    items, total = await store.list_documents()

    assert {d.uc_id for d in items} == {"UC-1", "UC-2"}
    assert total == 2


async def test_list_documents_includes_glossaries(session: AsyncSession) -> None:
    """CU-BE-12 · *Los glosarios son documentos de pleno derecho* (RN-9) — se listan junto a los UC,
    sin filtrarse por su `uc_id` sintético."""
    await _insert(session, "UC-1")
    await _insert(session, f"{GLOSARIO_UC_ID_PREFIX}media-and-dam", domain=KbDomain.media_and_dam)
    store = PgVectorStore(session)

    items, total = await store.list_documents()

    assert f"{GLOSARIO_UC_ID_PREFIX}media-and-dam" in {d.uc_id for d in items}
    assert total == 2


async def test_list_documents_maps_orm_enums_to_domain_enums(session: AsyncSession) -> None:
    """El listado devuelve enums de DOMINIO, no los del ORM: son clases distintas a propósito
    (`_enum_bridge`), y cruzarlas sin convertir rompería la serialización del router."""
    await _insert(
        session,
        "UC-1",
        domain=KbDomain.seo_sitemaps_and_edge,
        package=Package.syntax_ax,
        estado=KbEstado.draft,
    )
    store = PgVectorStore(session)

    items, _ = await store.list_documents()

    assert items[0].domain is KbDomain.seo_sitemaps_and_edge
    assert items[0].package is Package.syntax_ax
    assert items[0].estado is KbEstado.draft


async def test_list_documents_wraps_infrastructure_failure_in_port_error(
    broken_session: AsyncSession,
) -> None:
    """CU-BE-12 · *Un fallo de la base de datos no se disfraza de KB vacía* — `PortError` (→ 502),
    nunca `([], 0)`, que sería indistinguible de una KB legítimamente vacía."""
    store = PgVectorStore(broken_session)

    with pytest.raises(PortError):
        await store.list_documents()
