"""Tests de integración de app.ingestion.pipeline (tarea backend-kb-ingestion-06). Postgres real vía
`superuser_engine` (`SqlAlchemyKBIndexWriter` real, `-02`); `EmbeddingModel` fake puro (sin red, `-05`).
Cubren, a nivel de integración, TODOS los escenarios Gherkin de `CU-BE-07-ingestion-de-la-kb.md`.
"""

import dataclasses
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
import tiktoken
from app.domain.errors import Conflict, PortError, Validation
from app.infra.db.models.kb import EMBEDDING_DIM_LITERAL
from app.infra.vector import SqlAlchemyKBIndexWriter
from app.ingestion.pipeline import IngestReport, ingest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

_ENCODING = tiktoken.encoding_for_model("text-embedding-3-small")
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


class _FakeEmbeddingModel:
    def __init__(self, *, raises: Exception | None = None) -> None:
        self.calls: list[list[str]] = []
        self._raises = raises

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        if self._raises is not None:
            raise self._raises
        return [[0.1] * EMBEDDING_DIM_LITERAL for _ in texts]


def _uc_file(
    root: Path,
    *,
    domain: str = "authoring-and-editor",
    uc_id: str = "UC-CX-001",
    package: str = "syntax-cx",
    estado: str = "active",
    trazabilidad_package: str | None = None,
    title: str = "T",
    filename: str | None = None,
    body: str = "Texto.",
) -> Path:
    uc_dir = root / domain / "uc"
    uc_dir.mkdir(parents=True, exist_ok=True)
    path = uc_dir / (filename or f"{uc_id}.md")
    path.write_text(
        f'---\ntitle: "{title}"\ndomain: {domain}\npackage: {package}\nuc: {uc_id}\n---\n\n'
        f"# {title}\n\n## Comportamiento\n\n{body}\n\n"
        "::: info Trazabilidad\n"
        f"- **Estado**: {estado}\n"
        f"- **Package**: {trazabilidad_package or package}\n"
        ":::\n"
    )
    return path


def _index_file(root: Path, *, domain: str = "authoring-and-editor") -> Path:
    domain_dir = root / domain
    domain_dir.mkdir(parents=True, exist_ok=True)
    path = domain_dir / "index.md"
    path.write_text(f"# {domain}\n\n## Glosario\n\n- **Editor** — componente de edición.\n")
    return path


async def _ingest(
    root: Path,
    writer: SqlAlchemyKBIndexWriter,
    model: object | None = None,
    *,
    token_budget: int = 800,
    batch_size: int = 100,
) -> IngestReport:
    return await ingest(
        root,
        writer=writer,
        model=model or _FakeEmbeddingModel(),
        token_budget=token_budget,
        encoding=_ENCODING,
        batch_size=batch_size,
        embedding_model_name="text-embedding-3-small",
        source_type="vitepress-domains",
    )


# ── camino feliz ──


async def test_ingests_a_valid_uc(tmp_path: Path, session: AsyncSession) -> None:
    _uc_file(tmp_path)
    writer = SqlAlchemyKBIndexWriter(session)

    report = await _ingest(tmp_path, writer)
    await session.commit()

    assert report == IngestReport(processed=1, created=1, updated=0, skipped=0, deleted=0)
    assert await writer.existing_uc_ids() == {"UC-CX-001"}


async def test_reingesting_unchanged_content_does_not_call_the_embedder_again(
    tmp_path: Path, session: AsyncSession
) -> None:
    _uc_file(tmp_path)
    writer = SqlAlchemyKBIndexWriter(session)
    model = _FakeEmbeddingModel()
    await _ingest(tmp_path, writer, model)
    await session.commit()
    calls_after_first_run = len(model.calls)

    report = await _ingest(tmp_path, writer, model)
    await session.commit()

    assert report.updated == 1
    assert report.created == 0
    assert len(model.calls) == calls_after_first_run


# ── documento malformado ──


async def test_malformed_document_is_skipped_the_rest_is_processed(
    tmp_path: Path, session: AsyncSession
) -> None:
    _uc_file(tmp_path, uc_id="UC-CX-001")
    (tmp_path / "authoring-and-editor" / "uc" / "UC-CX-BAD.md").write_text("# sin frontmatter\n")
    writer = SqlAlchemyKBIndexWriter(session)

    report = await _ingest(tmp_path, writer)

    assert report.processed == 1
    assert report.skipped == 1


async def test_a_malformed_document_sorted_before_a_valid_one_does_not_stop_the_batch(
    tmp_path: Path, session: AsyncSession
) -> None:
    """El malformado ("UC-AAA...") ordena ANTES que el válido ("UC-CX-001") — descarta un
    `continue` mutado a `break`: pararía el recorrido en el primer malformado, perdiendo el resto."""
    (tmp_path / "authoring-and-editor" / "uc").mkdir(parents=True)
    (tmp_path / "authoring-and-editor" / "uc" / "UC-AAA-BAD.md").write_text("# sin frontmatter\n")
    _uc_file(tmp_path, uc_id="UC-CX-001")
    writer = SqlAlchemyKBIndexWriter(session)

    report = await _ingest(tmp_path, writer)

    assert report.processed == 1
    assert report.skipped == 1


async def test_domain_outside_the_catalog_is_skipped(tmp_path: Path, session: AsyncSession) -> None:
    _uc_file(tmp_path, domain="not-a-real-domain", uc_id="UC-X-001")
    writer = SqlAlchemyKBIndexWriter(session)

    report = await _ingest(tmp_path, writer)

    assert report.processed == 0
    assert report.skipped == 1


# ── uc_id duplicado (todo-o-nada) ──


async def test_duplicate_uc_id_aborts_the_whole_batch(
    tmp_path: Path, session: AsyncSession
) -> None:
    _uc_file(tmp_path, uc_id="UC-CX-001", filename="UC-FILE-A.md")
    _uc_file(tmp_path, uc_id="UC-CX-001", filename="UC-FILE-B.md")
    writer = SqlAlchemyKBIndexWriter(session)

    with pytest.raises(Validation):
        await _ingest(tmp_path, writer)

    assert await writer.existing_uc_ids() == set()


async def test_3_or_more_duplicate_files_report_all_of_them(
    tmp_path: Path, session: AsyncSession
) -> None:
    _uc_file(tmp_path, uc_id="UC-CX-001", filename="UC-FILE-A.md")
    _uc_file(tmp_path, uc_id="UC-CX-001", filename="UC-FILE-B.md")
    _uc_file(tmp_path, uc_id="UC-CX-001", filename="UC-FILE-C.md")
    writer = SqlAlchemyKBIndexWriter(session)

    with pytest.raises(Validation) as exc_info:
        await _ingest(tmp_path, writer)

    assert len(exc_info.value.details["UC-CX-001"]) == 3


async def test_duplicate_uc_id_also_blocks_reconciliation_of_the_same_run(
    tmp_path: Path, session: AsyncSession
) -> None:
    path_b = _uc_file(tmp_path, uc_id="UC-CX-002", filename="UC-FILE-B.md")
    _uc_file(tmp_path, uc_id="UC-CX-001", filename="UC-FILE-A.md")
    writer = SqlAlchemyKBIndexWriter(session)
    await _ingest(tmp_path, writer)
    await session.commit()

    path_b.unlink()
    _uc_file(tmp_path, uc_id="UC-CX-001", filename="UC-FILE-A-DUP.md")

    with pytest.raises(Validation):
        await _ingest(tmp_path, writer)

    assert await writer.existing_uc_ids() == {"UC-CX-001", "UC-CX-002"}


# ── reconciliación ──


async def test_a_retired_document_is_reconciled(tmp_path: Path, session: AsyncSession) -> None:
    path_a = _uc_file(tmp_path, uc_id="UC-CX-001", filename="UC-FILE-A.md")
    _uc_file(tmp_path, uc_id="UC-CX-002", filename="UC-FILE-B.md")
    writer = SqlAlchemyKBIndexWriter(session)
    await _ingest(tmp_path, writer)
    await session.commit()

    path_a.unlink()

    report = await _ingest(tmp_path, writer)
    await session.commit()

    assert report.deleted == 1
    assert await writer.existing_uc_ids() == {"UC-CX-002"}


async def test_a_chunk_retired_from_a_still_alive_document_is_removed(
    tmp_path: Path, session: AsyncSession
) -> None:
    _uc_file(tmp_path, uc_id="UC-CX-001", body="Uno.\n\n## Fidelidad\n\nDos.")
    writer = SqlAlchemyKBIndexWriter(session)
    await _ingest(tmp_path, writer)
    await session.commit()
    # 3 chunks: intro (el H1 "# T" antes del primer H2) + comportamiento + fidelidad
    assert len(await writer.existing_chunk_contents("UC-CX-001")) == 3

    _uc_file(tmp_path, uc_id="UC-CX-001", body="Uno editado.")

    report = await _ingest(tmp_path, writer)
    await session.commit()

    assert len(await writer.existing_chunk_contents("UC-CX-001")) == 2
    assert report.deleted == 0
    assert await writer.existing_uc_ids() == {"UC-CX-001"}


# ── package: precedencia end-to-end ──


async def test_frontmatter_package_wins_end_to_end(tmp_path: Path, session: AsyncSession) -> None:
    _uc_file(tmp_path, package="syntax-cx", trazabilidad_package="syntax-api")
    writer = SqlAlchemyKBIndexWriter(session)

    await _ingest(tmp_path, writer)
    await session.commit()

    persisted_package = (
        await session.execute(text("SELECT package FROM kb_document WHERE uc_id = 'UC-CX-001'"))
    ).scalar_one()
    assert persisted_package == "syntax-cx"


# ── fallos reales (todo-o-nada) ──


async def test_a_real_failure_mid_batch_aborts_the_whole_run(
    tmp_path: Path, session: AsyncSession
) -> None:
    _uc_file(tmp_path, uc_id="UC-CX-001", filename="UC-FILE-A.md")
    _uc_file(tmp_path, uc_id="UC-CX-002", filename="UC-FILE-B.md")
    writer = SqlAlchemyKBIndexWriter(session)
    model = _FakeEmbeddingModel(raises=PortError("fallo del proveedor"))

    with pytest.raises(PortError):
        await _ingest(tmp_path, writer, model)

    assert await writer.existing_uc_ids() == set()


# ── ejecuciones concurrentes ──


async def test_concurrent_executions_do_not_overlap(
    tmp_path: Path, superuser_engine: AsyncEngine
) -> None:
    _uc_file(tmp_path)
    maker = async_sessionmaker(superuser_engine, expire_on_commit=False)
    holder = maker()
    contender = maker()
    try:
        assert await SqlAlchemyKBIndexWriter(holder).try_acquire_ingestion_lock() is True

        with pytest.raises(Conflict):
            await _ingest(tmp_path, SqlAlchemyKBIndexWriter(contender))
    finally:
        await holder.close()
        await contender.close()


# ── origen sin documentos válidos ──


async def test_an_origin_with_no_valid_documents_succeeds_without_touching_the_db(
    tmp_path: Path, session: AsyncSession
) -> None:
    uc_dir = tmp_path / "authoring-and-editor" / "uc"
    uc_dir.mkdir(parents=True)
    (uc_dir / "UC-X.md").write_text("# sin frontmatter\n")
    writer = SqlAlchemyKBIndexWriter(session)

    report = await _ingest(tmp_path, writer)

    assert report == IngestReport(processed=0, created=0, updated=0, skipped=1, deleted=0)
    assert await writer.existing_uc_ids() == set()


async def test_a_completely_empty_origin_succeeds_without_touching_the_db(
    tmp_path: Path, session: AsyncSession
) -> None:
    writer = SqlAlchemyKBIndexWriter(session)

    report = await _ingest(tmp_path, writer)

    assert report == IngestReport(processed=0, created=0, updated=0, skipped=0, deleted=0)


# ── edición parcial ──


async def test_partial_edit_only_reembeds_the_changed_chunk(
    tmp_path: Path, session: AsyncSession
) -> None:
    _uc_file(tmp_path, uc_id="UC-CX-001", body="Uno.\n\n## Fidelidad\n\nDos.")
    writer = SqlAlchemyKBIndexWriter(session)
    await _ingest(tmp_path, writer, _FakeEmbeddingModel())
    await session.commit()

    _uc_file(tmp_path, uc_id="UC-CX-001", body="Uno EDITADO.\n\n## Fidelidad\n\nDos.")

    second_model = _FakeEmbeddingModel()
    await _ingest(tmp_path, writer, second_model)
    await session.commit()

    assert second_model.calls == [["Uno EDITADO."]]


# ── glosario (index.md) ──


async def test_a_glosario_document_is_persisted_with_its_own_estado_and_package(
    tmp_path: Path, session: AsyncSession
) -> None:
    """Descarta un `is_glosario` mutado a `not is_glosario` en `_to_draft`: el `estado` de un
    glosario (`active`, forzado) debe distinguirse del `estado` real de un UC normal (`draft`, de
    su propia Trazabilidad) — si se intercambian, este test lo detecta."""
    _index_file(tmp_path)
    _uc_file(tmp_path, uc_id="UC-CX-001", estado="draft")
    writer = SqlAlchemyKBIndexWriter(session)

    await _ingest(tmp_path, writer)
    await session.commit()

    glosario_row = (
        await session.execute(
            text("SELECT estado, package FROM kb_document WHERE uc_id LIKE '__glosario__%'")
        )
    ).one()
    uc_row = (
        await session.execute(
            text("SELECT estado, package FROM kb_document WHERE uc_id = 'UC-CX-001'")
        )
    ).one()
    assert glosario_row.estado == "active"
    assert glosario_row.package == "syntax-core"
    assert uc_row.estado == "draft"
    assert uc_row.package == "syntax-cx"


def test_ingest_report_is_immutable() -> None:
    report = IngestReport(processed=1, created=1, updated=0, skipped=0, deleted=0)

    with pytest.raises(dataclasses.FrozenInstanceError):
        report.processed = 2  # type: ignore[misc]


# ── only_domain / dry_run / force_reconcile (tarea backend-kb-ingestion-07) ──


async def test_only_domain_filters_the_batch_to_a_single_domain(
    tmp_path: Path, session: AsyncSession
) -> None:
    _uc_file(tmp_path, domain="authoring-and-editor", uc_id="UC-CX-001")
    _uc_file(tmp_path, domain="sites-domains-instances", uc_id="UC-CORE-001")
    writer = SqlAlchemyKBIndexWriter(session)

    report = await ingest(
        tmp_path,
        writer=writer,
        model=_FakeEmbeddingModel(),
        token_budget=800,
        encoding=_ENCODING,
        batch_size=100,
        embedding_model_name="text-embedding-3-small",
        source_type="vitepress-domains",
        only_domain="authoring-and-editor",
    )

    assert report.processed == 1
    assert await writer.existing_uc_ids() == {"UC-CX-001"}


async def test_only_domain_does_not_stop_at_the_first_non_matching_document(
    tmp_path: Path, session: AsyncSession
) -> None:
    """El dominio NO-coincidente ("authoring-and-editor") ordena ANTES que el coincidente
    ("sites-domains-instances") — descarta un `continue` mutado a `break`: pararía el recorrido en
    el primer documento filtrado, sin llegar nunca al que sí coincide."""
    _uc_file(tmp_path, domain="authoring-and-editor", uc_id="UC-CX-001")
    _uc_file(tmp_path, domain="sites-domains-instances", uc_id="UC-CORE-001")
    writer = SqlAlchemyKBIndexWriter(session)

    report = await ingest(
        tmp_path,
        writer=writer,
        model=_FakeEmbeddingModel(),
        token_budget=800,
        encoding=_ENCODING,
        batch_size=100,
        embedding_model_name="text-embedding-3-small",
        source_type="vitepress-domains",
        only_domain="sites-domains-instances",
    )

    assert report.processed == 1
    assert await writer.existing_uc_ids() == {"UC-CORE-001"}


async def test_only_domain_with_no_matching_documents_succeeds_with_zero_processed(
    tmp_path: Path, session: AsyncSession
) -> None:
    _uc_file(tmp_path, domain="authoring-and-editor", uc_id="UC-CX-001")
    writer = SqlAlchemyKBIndexWriter(session)

    report = await ingest(
        tmp_path,
        writer=writer,
        model=_FakeEmbeddingModel(),
        token_budget=800,
        encoding=_ENCODING,
        batch_size=100,
        embedding_model_name="text-embedding-3-small",
        source_type="vitepress-domains",
        only_domain="sites-domains-instances",
    )

    assert report == IngestReport(processed=0, created=0, updated=0, skipped=0, deleted=0)


async def test_dry_run_does_not_write_anything_nor_call_the_embedder(
    tmp_path: Path, session: AsyncSession
) -> None:
    _uc_file(tmp_path, uc_id="UC-CX-001")
    writer = SqlAlchemyKBIndexWriter(session)
    model = _FakeEmbeddingModel()

    report = await ingest(
        tmp_path,
        writer=writer,
        model=model,
        token_budget=800,
        encoding=_ENCODING,
        batch_size=100,
        embedding_model_name="text-embedding-3-small",
        source_type="vitepress-domains",
        dry_run=True,
    )

    assert report.created == 1
    assert model.calls == []
    assert await writer.existing_uc_ids() == set()


async def test_dry_run_reports_updates_and_deletions_without_persisting_them(
    tmp_path: Path, session: AsyncSession
) -> None:
    path_a = _uc_file(tmp_path, uc_id="UC-CX-001", filename="UC-FILE-A.md")
    writer = SqlAlchemyKBIndexWriter(session)
    await _ingest(tmp_path, writer)
    await session.commit()

    path_a.unlink()
    model = _FakeEmbeddingModel()

    report = await ingest(
        tmp_path,
        writer=writer,
        model=model,
        token_budget=800,
        encoding=_ENCODING,
        batch_size=100,
        embedding_model_name="text-embedding-3-small",
        source_type="vitepress-domains",
        dry_run=True,
        force_reconcile=True,
    )

    assert report.deleted == 1
    assert model.calls == []
    assert await writer.existing_uc_ids() == {"UC-CX-001"}


async def test_force_reconcile_deletes_everything_when_the_origin_is_empty(
    tmp_path: Path, session: AsyncSession
) -> None:
    _uc_file(tmp_path, uc_id="UC-CX-001")
    writer = SqlAlchemyKBIndexWriter(session)
    await _ingest(tmp_path, writer)
    await session.commit()
    (tmp_path / "authoring-and-editor" / "uc" / "UC-CX-001.md").unlink()

    report = await ingest(
        tmp_path,
        writer=writer,
        model=_FakeEmbeddingModel(),
        token_budget=800,
        encoding=_ENCODING,
        batch_size=100,
        embedding_model_name="text-embedding-3-small",
        source_type="vitepress-domains",
        force_reconcile=True,
    )

    assert report.deleted == 1
    assert await writer.existing_uc_ids() == set()


async def test_without_force_reconcile_an_empty_origin_does_not_touch_the_db(
    tmp_path: Path, session: AsyncSession
) -> None:
    _uc_file(tmp_path, uc_id="UC-CX-001")
    writer = SqlAlchemyKBIndexWriter(session)
    await _ingest(tmp_path, writer)
    await session.commit()
    (tmp_path / "authoring-and-editor" / "uc" / "UC-CX-001.md").unlink()

    report = await ingest(
        tmp_path,
        writer=writer,
        model=_FakeEmbeddingModel(),
        token_budget=800,
        encoding=_ENCODING,
        batch_size=100,
        embedding_model_name="text-embedding-3-small",
        source_type="vitepress-domains",
    )

    assert report == IngestReport(processed=0, created=0, updated=0, skipped=0, deleted=0)
    assert await writer.existing_uc_ids() == {"UC-CX-001"}
