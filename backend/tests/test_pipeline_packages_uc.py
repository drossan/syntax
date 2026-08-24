"""Tests de integración del `source_type` **`packages-uc`** end-to-end
(tarea backend-kb-source-packages-uc-03).

Postgres real vía `superuser_engine` (`SqlAlchemyKBIndexWriter` real); `EmbeddingModel` fake puro (sin
red). Cierran los escenarios de `CU-BE-07` que `-01`/`-02` solo verificaban a nivel de descubrimiento y
parseo: aquí el documento, sus chunks y sus embeddings quedan **realmente** en la base de datos.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
import tiktoken
from app.infra.db.models.kb import EMBEDDING_DIM_LITERAL
from app.infra.vector import SqlAlchemyKBIndexWriter
from app.ingestion.parser import GLOSARIO_UC_ID_PREFIX
from app.ingestion.pipeline import IngestReport, ingest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

_ENCODING = tiktoken.encoding_for_model("text-embedding-3-small")
_TRUNCATE_TABLES = "TRUNCATE embedding, kb_chunk, kb_document RESTART IDENTITY CASCADE"

_FIXTURES_ROOT = Path(__file__).parent / "fixtures" / "kb_packages_uc"
_ALIASES = {"vendor-core": "syntax-core", "vendor-render": "syntax-render"}

pytestmark = pytest.mark.asyncio


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


class _FakeEmbeddingModel:
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * EMBEDDING_DIM_LITERAL for _ in texts]


async def _ingest(
    root: Path,
    writer: SqlAlchemyKBIndexWriter,
    *,
    source_type: str = "packages-uc",
    package_aliases: dict[str, str] | None = None,
) -> IngestReport:
    return await ingest(
        root,
        writer=writer,
        model=_FakeEmbeddingModel(),
        token_budget=800,
        encoding=_ENCODING,
        batch_size=100,
        embedding_model_name="text-embedding-3-small",
        source_type=source_type,
        package_aliases=_ALIASES if package_aliases is None else package_aliases,
    )


def _vitepress_tree(root: Path, *, uc_id: str = "UC-CX-001") -> Path:
    """Un árbol mínimo del OTRO tipo de fuente (`vitepress-domains`), para la transición 4c."""
    uc_dir = root / "authoring-and-editor" / "uc"
    uc_dir.mkdir(parents=True)
    (uc_dir / f"{uc_id}.md").write_text(
        f'---\ntitle: "T"\ndomain: authoring-and-editor\npackage: syntax-cx\nuc: {uc_id}\n---\n\n'
        "# T\n\n## Comportamiento\n\nTexto.\n\n"
        "::: info Trazabilidad\n- **Estado**: active\n- **Package**: syntax-cx\n:::\n",
        encoding="utf-8",
    )
    return root


async def _uc_ids(writer: SqlAlchemyKBIndexWriter) -> set[str]:
    return await writer.existing_uc_ids()


async def _count(session: AsyncSession, sql: str) -> int:
    return (await session.execute(text(sql))).scalar_one()


# ── camino feliz end-to-end ──────────────────────────────────────────────────────────────────────


async def test_a_real_uc_ends_up_as_document_chunks_and_embeddings(session: AsyncSession) -> None:
    """CU `Ingesta de un UC del formato real` — cierre end-to-end."""
    writer = SqlAlchemyKBIndexWriter(session)

    report = await _ingest(_FIXTURES_ROOT, writer)
    await session.commit()

    assert report.skipped == 0
    assert "UC-CORE-001" in await _uc_ids(writer)
    assert (
        await _count(session, "SELECT count(*) FROM kb_document WHERE uc_id = 'UC-CORE-001'") == 1
    )
    assert (
        await _count(
            session,
            "SELECT count(*) FROM kb_chunk c JOIN kb_document d ON d.id = c.document_id"
            " WHERE d.uc_id = 'UC-CORE-001'",
        )
        > 0
    )
    assert (
        await _count(
            session,
            "SELECT count(*) FROM embedding e JOIN kb_chunk c ON c.id = e.chunk_id"
            " JOIN kb_document d ON d.id = c.document_id WHERE d.uc_id = 'UC-CORE-001'",
        )
        > 0
    )


async def test_the_package_persisted_is_the_one_translated_by_the_alias(
    session: AsyncSession,
) -> None:
    """El `package` no está en el frontmatter: sale del subdirectorio traducido por los alias."""
    writer = SqlAlchemyKBIndexWriter(session)

    await _ingest(_FIXTURES_ROOT, writer)
    await session.commit()

    packages = (
        await session.execute(
            text(
                "SELECT package::text FROM kb_document WHERE uc_id IN ('UC-CORE-001','UC-RENDER-001')"
            )
        )
    ).scalars()
    assert sorted(packages) == ["syntax-core", "syntax-render"]


async def test_the_title_persisted_is_the_h1_of_the_body(session: AsyncSession) -> None:
    writer = SqlAlchemyKBIndexWriter(session)

    await _ingest(_FIXTURES_ROOT, writer)
    await session.commit()

    title = (
        await session.execute(text("SELECT title FROM kb_document WHERE uc_id = 'UC-CORE-001'"))
    ).scalar_one()
    assert title == "Carga de la configuración del proyecto"


async def test_the_glossary_of_the_real_format_is_ingested_whole(session: AsyncSession) -> None:
    """CU `El glosario del formato real se ingiere íntegro` (extensión 2a) — cierre end-to-end."""
    writer = SqlAlchemyKBIndexWriter(session)

    await _ingest(_FIXTURES_ROOT, writer)
    await session.commit()

    uc_id = f"{GLOSARIO_UC_ID_PREFIX}authoring-and-editor"
    assert uc_id in await _uc_ids(writer)
    contents = await writer.existing_chunk_contents(uc_id)
    assert any("Publicada" in content for content in contents.values())


async def test_a_sibling_tree_with_another_convention_never_enters_the_corpus(
    session: AsyncSession,
) -> None:
    """CU `Un árbol hermano con otra convención de carpeta nunca se recoge` (1k) — end-to-end.

    La fixture legacy declara el MISMO `uc_id` (`UC-CORE-001`) que el árbol reconocido: si el loader lo
    recogiera, el batch fallaría por duplicado en vez de pasar. El test lo prueba por partida doble.
    """
    writer = SqlAlchemyKBIndexWriter(session)

    report = await _ingest(_FIXTURES_ROOT, writer)
    await session.commit()

    assert report.processed == 5  # 3 UC + 2 glosarios; nada del árbol hermano
    source_urls = (
        (await session.execute(text("SELECT source_url FROM kb_document"))).scalars().all()
    )
    assert not any("legacy-site" in url for url in source_urls)


# ── alias de package ─────────────────────────────────────────────────────────────────────────────


async def test_without_any_alias_configured_no_use_case_is_ingested(session: AsyncSession) -> None:
    """CU `Sin ningún alias configurado no se ingiere ningún caso de uso, y se avisa` (1l) — los UC se
    saltan como malformados; los **glosarios sí entran**, porque no dependen de los alias."""
    writer = SqlAlchemyKBIndexWriter(session)

    report = await _ingest(_FIXTURES_ROOT, writer, package_aliases={})
    await session.commit()

    assert report.skipped == 3  # los 3 UC
    assert await _uc_ids(writer) == {
        f"{GLOSARIO_UC_ID_PREFIX}authoring-and-editor",
        f"{GLOSARIO_UC_ID_PREFIX}platform-and-devex",
    }


async def test_forgetting_the_aliases_over_a_populated_database_reconciles_the_use_cases(
    session: AsyncSession,
) -> None:
    """CU `Olvidar los alias sobre una base ya poblada reconcilia los casos de uso existentes` (1l).

    La salvaguarda de 4b/RN-6 ("un run sin documentos válidos no reconcilia") **no** cubre este caso:
    los glosarios sí se ingieren, así que el run no queda vacío y los UC ya persistidos, al no
    reaparecer, se borran. Es el motivo por el que el aviso de la CLI es obligatorio.
    """
    writer = SqlAlchemyKBIndexWriter(session)
    await _ingest(_FIXTURES_ROOT, writer)
    await session.commit()
    assert "UC-CORE-001" in await _uc_ids(writer)

    report = await _ingest(_FIXTURES_ROOT, writer, package_aliases={})
    await session.commit()

    assert report.deleted == 3  # los 3 UC que ya estaban
    assert "UC-CORE-001" not in await _uc_ids(writer)


async def test_an_alias_pointing_outside_the_catalogue_skips_only_its_own_documents(
    session: AsyncSession,
) -> None:
    """CU `Un alias que apunta a un package inexistente se salta` (1h) — end-to-end: el batch NO
    aborta, y los documentos de los demás packages sí entran."""
    writer = SqlAlchemyKBIndexWriter(session)

    report = await _ingest(
        _FIXTURES_ROOT,
        writer,
        package_aliases={"vendor-core": "syntax-typo", "vendor-render": "syntax-render"},
    )
    await session.commit()

    assert report.skipped == 2  # los 2 UC de vendor-core
    assert "UC-RENDER-001" in await _uc_ids(writer)
    assert "UC-CORE-001" not in await _uc_ids(writer)


# ── transición entre tipos de fuente (extensión 4c) ──────────────────────────────────────────────


async def test_switching_the_source_type_reconciles_the_previous_format(
    tmp_path: Path, session: AsyncSession
) -> None:
    """CU `Cambiar el tipo de fuente entre ejecuciones reconcilia el formato anterior` (extensión 4c).

    La reconciliación compara `uc_id` origen-vs-BD **sin distinguir la procedencia**, así que cambiar
    el `source_type` sobre la misma BD borra lo que ya no aparece. Es lo esperado (el origen es la
    verdad), pero es un efecto masivo que un operador puede disparar sin querer — de ahí el test.
    """
    writer = SqlAlchemyKBIndexWriter(session)
    _vitepress_tree(tmp_path)

    first = await _ingest(tmp_path, writer, source_type="vitepress-domains")
    await session.commit()
    assert first.processed == 1
    assert "UC-CX-001" in await _uc_ids(writer)

    second = await _ingest(_FIXTURES_ROOT, writer)
    await session.commit()

    assert second.deleted == 1
    assert "UC-CX-001" not in await _uc_ids(writer)
    assert "UC-CORE-001" in await _uc_ids(writer)


async def test_the_uc_id_namespace_is_shared_between_source_types(
    tmp_path: Path, session: AsyncSession
) -> None:
    """Corolario de 4c, declarado explícitamente en la spec: no hay espacio de nombres por tipo de
    fuente — un mismo `uc_id` ingerido por el otro tipo **actualiza** el documento, no crea un segundo.
    """
    writer = SqlAlchemyKBIndexWriter(session)
    _vitepress_tree(tmp_path, uc_id="UC-CORE-001")

    await _ingest(tmp_path, writer, source_type="vitepress-domains")
    await session.commit()
    second = await _ingest(_FIXTURES_ROOT, writer)
    await session.commit()

    assert second.updated == 1  # UC-CORE-001 ya existía: se actualiza, no se duplica
    assert (
        await _count(session, "SELECT count(*) FROM kb_document WHERE uc_id = 'UC-CORE-001'") == 1
    )
