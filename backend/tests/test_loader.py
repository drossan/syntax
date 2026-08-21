"""Tests de app.ingestion.loader (tarea backend-kb-ingestion-03)."""

import dataclasses
from pathlib import Path

import pytest
import structlog
from app.ingestion.loader import load

_FIXTURES_ROOT = Path(__file__).parent / "fixtures" / "kb" / "domains"


@pytest.fixture(autouse=True)
def _structlog_via_stdlib_for_caplog():
    """`caplog` captura el `logging` estándar; `structlog` usa su propio `PrintLoggerFactory` por
    defecto, así que aquí se reconfigura SOLO durante el test para que los eventos lleguen a
    `caplog` (patrón nuevo en este repo, decisión de `scenario-coverage`)."""
    structlog.configure(
        processors=[structlog.processors.KeyValueRenderer(key_order=["event"])],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
    )
    yield
    structlog.reset_defaults()


def test_load_discovers_domain_ucs_and_domain_index_but_not_root_index() -> None:
    docs = list(load(_FIXTURES_ROOT))

    paths = {doc.path.name for doc in docs}
    assert paths == {"UC-CX-001.md", "UC-CX-002.md", "UC-CORE-001.md", "index.md"}
    # 2 index.md de dominio (uno por dominio) + el raíz NO está entre ellos: se comprueba por CONTEO,
    # no solo por nombre (dos "index.md" distintos comparten nombre de fichero).
    assert sum(1 for doc in docs if doc.path.name == "index.md") == 2
    assert _FIXTURES_ROOT / "index.md" not in {doc.path for doc in docs}


def test_load_reads_the_real_file_content() -> None:
    docs = {doc.path.name: doc for doc in load(_FIXTURES_ROOT)}

    assert "uc: UC-CX-001" in docs["UC-CX-001.md"].content


def test_load_captures_a_real_mtime_per_document() -> None:
    docs = list(load(_FIXTURES_ROOT))

    assert all(doc.mtime.tzinfo is not None for doc in docs)


def test_load_with_nonexistent_root_raises_clear_error(tmp_path: Path) -> None:
    missing = tmp_path / "no-existe"

    with pytest.raises(FileNotFoundError, match="no existe"):
        load(missing)


def test_load_with_a_file_instead_of_a_directory_raises_clear_error(tmp_path: Path) -> None:
    a_file = tmp_path / "not-a-dir"
    a_file.write_text("x")

    with pytest.raises(FileNotFoundError):
        load(a_file)


def test_load_validates_the_root_before_returning_the_iterator(tmp_path: Path) -> None:
    """`load()` no es un generador puro: el `FileNotFoundError` debe llegar en la propia llamada,
    ANTES de que el caller itere — nunca solo al primer `next()`."""
    missing = tmp_path / "no-existe"

    with pytest.raises(FileNotFoundError):
        load(missing)  # sin iterar el resultado


def test_load_skips_an_unreadable_file_with_log(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    domain_dir = tmp_path / "authoring-and-editor" / "uc"
    domain_dir.mkdir(parents=True)
    unreadable = domain_dir / "UC-X-001.md"
    unreadable.write_text("---\nuc: UC-X-001\n---\n")
    unreadable.chmod(0o000)
    try:
        with caplog.at_level("WARNING"):
            docs = list(load(tmp_path))
    finally:
        unreadable.chmod(0o644)

    assert docs == []
    assert "kb_doc_illegible" in caplog.text


def test_load_skips_a_file_with_invalid_encoding_with_log(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    domain_dir = tmp_path / "authoring-and-editor" / "uc"
    domain_dir.mkdir(parents=True)
    bad_encoding = domain_dir / "UC-X-002.md"
    bad_encoding.write_bytes(b"\xff\xfe\x00\x01---not utf8---")

    with caplog.at_level("WARNING"):
        docs = list(load(tmp_path))

    assert docs == []
    assert "kb_doc_illegible" in caplog.text


def test_load_a_domain_without_a_uc_directory_still_yields_its_index(tmp_path: Path) -> None:
    domain_dir = tmp_path / "solo-glosario"
    domain_dir.mkdir()
    (domain_dir / "index.md").write_text("# Solo glosario\n\n## Glosario\n\n- **A** — a.\n")

    docs = list(load(tmp_path))

    assert [doc.path.name for doc in docs] == ["index.md"]


def test_load_a_domain_without_an_index_md_still_yields_its_ucs(tmp_path: Path) -> None:
    uc_dir = tmp_path / "sin-index" / "uc"
    uc_dir.mkdir(parents=True)
    (uc_dir / "UC-Z-001.md").write_text("---\nuc: UC-Z-001\n---\n")

    docs = list(load(tmp_path))

    assert [doc.path.name for doc in docs] == ["UC-Z-001.md"]


def test_load_an_empty_root_yields_nothing(tmp_path: Path) -> None:
    assert list(load(tmp_path)) == []


def test_raw_doc_is_immutable() -> None:
    docs = list(load(_FIXTURES_ROOT))

    with pytest.raises(dataclasses.FrozenInstanceError):
        docs[0].content = "otro"  # type: ignore[misc]


def test_a_domain_without_a_uc_directory_does_not_stop_discovering_later_domains(
    tmp_path: Path,
) -> None:
    """Un dominio sin `uc/` seguido (alfabéticamente) de otro CON UCs — descarta un `continue`
    mutado a `break`: pararía todo el recorrido en el primer dominio sin `uc/`."""
    (tmp_path / "a-solo-index").mkdir()
    (tmp_path / "a-solo-index" / "index.md").write_text("# Solo índice\n")
    uc_dir = tmp_path / "b-con-ucs" / "uc"
    uc_dir.mkdir(parents=True)
    (uc_dir / "UC-Z-001.md").write_text("---\nuc: UC-Z-001\n---\n")

    docs = list(load(tmp_path))

    assert "UC-Z-001.md" in {doc.path.name for doc in docs}
