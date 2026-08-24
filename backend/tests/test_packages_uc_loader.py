"""Tests de `app.ingestion.packages_uc.load` (tarea backend-kb-source-packages-uc-01).

Descubrimiento de ficheros del `source_type` **`packages-uc`** (el formato REAL verificado):
`packages/<pkg>/docs/aiup/use-cases/UC-*.md` + `docs/aiup/glossaries/<dominio>.md`.

Fixtures en `tests/fixtures/kb_packages_uc/` — su `README.md` documenta qué aspecto del formato real
reproduce cada una. Los casos negativos y de permisos se construyen en `tmp_path` (no ensucian la
fixture ni dependen de que git preserve modos/directorios vacíos).

Nivel **unit**: sin BD, sin puertos; solo filesystem.
"""

from collections.abc import Callable
from pathlib import Path

import pytest
import structlog
from app.ingestion.loader import RawDoc
from app.ingestion.packages_uc import load

_FIXTURES_ROOT = Path(__file__).parent / "fixtures" / "kb_packages_uc"

_FIXTURE_UC_NAMES = {
    "UC-CORE-001-carga-de-la-configuracion.md",
    "UC-CORE-002-contenido-relacionado.md",
    "UC-RENDER-001-render-de-una-pagina.md",
}
_FIXTURE_GLOSSARY_NAMES = {"authoring-and-editor.md", "platform-and-devex.md"}


@pytest.fixture(autouse=True)
def _structlog_via_stdlib_for_caplog():
    """`caplog` captura el `logging` estándar; `structlog` usa su propio `PrintLoggerFactory` por
    defecto, así que aquí se reconfigura SOLO durante el test para que los eventos lleguen a
    `caplog` (mismo patrón que `test_loader.py`, establecido en el plan `kb-ingestion`)."""
    structlog.configure(
        processors=[structlog.processors.KeyValueRenderer(key_order=["event"])],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
    )
    yield
    structlog.reset_defaults()


# ── Helpers de construcción de árboles en `tmp_path` ─────────────────────────────────────────────


def _use_cases_dir(root: Path, package: str) -> Path:
    """El directorio de casos de uso de un subdirectorio de package, según la convención del tipo."""
    return root / "packages" / package / "docs" / "aiup" / "use-cases"


def _glossaries_dir(root: Path) -> Path:
    """El directorio COMPARTIDO de glosarios (uno plano por dominio), según la convención del tipo."""
    return root / "docs" / "aiup" / "glossaries"


def _write(path: Path, content: str = "contenido\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _names(root: Path) -> list[str]:
    return [doc.path.name for doc in load(root)]


# ── Camino feliz: descubrimiento sobre la fixture del formato real ───────────────────────────────


def test_load_discovers_the_ucs_of_every_package_and_the_shared_glossaries() -> None:
    """Escenario (añadido por la tarea): UC en dos subdirectorios de package + glosarios de dominio."""
    docs = list(load(_FIXTURES_ROOT))

    assert {doc.path.name for doc in docs} == _FIXTURE_UC_NAMES | _FIXTURE_GLOSSARY_NAMES


def test_load_yields_the_shared_contract_raw_doc_unmodified() -> None:
    """`RawDoc` es el contrato source-agnostic de `loader.py`: se REUTILIZA, no se redefine."""
    docs = list(load(_FIXTURES_ROOT))

    assert docs
    assert all(isinstance(doc, RawDoc) for doc in docs)


def test_load_reads_the_real_uc_content() -> None:
    """CU `Ingesta de un UC del formato real` — parte de esta tarea: el fichero se descubre y se LEE."""
    docs = {doc.path.name: doc for doc in load(_FIXTURES_ROOT)}

    content = docs["UC-CORE-001-carga-de-la-configuracion.md"].content
    assert "id: UC-CORE-001" in content
    assert "# Carga de la configuración del proyecto" in content


def test_load_reads_the_whole_glossary_file() -> None:
    """CU `El glosario del formato real se ingiere íntegro` — parte de esta tarea: se descubre y se
    lee ENTERO (el fichero plano no tiene frontmatter ni sección `## Glosario` que recortar)."""
    docs = {doc.path.name: doc for doc in load(_FIXTURES_ROOT)}

    content = docs["authoring-and-editor.md"].content
    assert content.startswith("# Glosario — Edición de contenido")
    assert "**Publicada**" in content


def test_load_captures_a_timezone_aware_mtime_per_document() -> None:
    """El `mtime` se captura en el LOADER (no en el parser, que queda puro)."""
    docs = list(load(_FIXTURES_ROOT))

    assert docs
    assert all(doc.mtime.tzinfo is not None for doc in docs)


# ── Extensión 1k: el árbol hermano con otra convención ───────────────────────────────────────────


def test_load_never_picks_a_sibling_tree_with_another_convention() -> None:
    """CU extensión **1k**. La fixture legacy EXISTE (se afirma) — el test no puede pasar en vacío."""
    legacy_root = _FIXTURES_ROOT / "legacy-site"
    assert list(legacy_root.rglob("UC-*.md")), "la fixture del árbol hermano debe existir"

    docs = list(load(_FIXTURES_ROOT))

    assert not any(legacy_root in doc.path.parents for doc in docs)
    assert len(docs) == len(_FIXTURE_UC_NAMES) + len(_FIXTURE_GLOSSARY_NAMES)


# ── Orden de descubrimiento ──────────────────────────────────────────────────────────────────────


def test_load_lists_every_uc_before_any_glossary() -> None:
    """CU `El orden de descubrimiento sigue la convención documentada` — grupos."""
    names = _names(_FIXTURES_ROOT)

    last_uc = max(i for i, name in enumerate(names) if name in _FIXTURE_UC_NAMES)
    first_glossary = min(i for i, name in enumerate(names) if name in _FIXTURE_GLOSSARY_NAMES)
    assert last_uc < first_glossary


def test_load_orders_ucs_by_package_directory_then_by_file_name(tmp_path: Path) -> None:
    """El orden CONCRETO es parte del contrato (de él dependen el `ordinal` de los chunks y la
    reproducibilidad del batch), no solo que dos pasadas coincidan."""
    _write(_use_cases_dir(tmp_path, "vendor-b") / "UC-B-001.md")
    _write(_use_cases_dir(tmp_path, "vendor-a") / "UC-A-002.md")
    _write(_use_cases_dir(tmp_path, "vendor-a") / "UC-A-001.md")
    _write(_glossaries_dir(tmp_path) / "zeta.md")
    _write(_glossaries_dir(tmp_path) / "alfa.md")

    assert _names(tmp_path) == [
        "UC-A-001.md",
        "UC-A-002.md",
        "UC-B-001.md",
        "alfa.md",
        "zeta.md",
    ]


def test_load_order_is_stable_between_runs() -> None:
    assert _names(_FIXTURES_ROOT) == _names(_FIXTURES_ROOT)


# ── Entradas que matchean el patrón pero no son documentos ingeribles ────────────────────────────


def _a_directory_named_like_a_uc(root: Path) -> None:
    (_use_cases_dir(root, "vendor-a") / "UC-DIR-001.md").mkdir(parents=True)


def _a_file_without_the_uc_prefix(root: Path) -> None:
    _write(_use_cases_dir(root, "vendor-a") / "notas.md")


def _a_uc_nested_deeper_than_the_convention(root: Path) -> None:
    _write(_use_cases_dir(root, "vendor-a") / "sub" / "UC-DEEP-001.md")


def _a_glossary_inside_a_package(root: Path) -> None:
    _write(root / "packages" / "vendor-a" / "docs" / "aiup" / "glossaries" / "media-and-dam.md")


def _a_uc_whose_prefix_differs_in_case(root: Path) -> None:
    _write(_use_cases_dir(root, "vendor-a") / "uc-LOW-001.md")


def _a_uc_whose_extension_differs_in_case(root: Path) -> None:
    _write(_use_cases_dir(root, "vendor-a") / "UC-UPPER-001.MD")


def _a_non_markdown_file_among_the_glossaries(root: Path) -> None:
    _write(_glossaries_dir(root) / "notas.txt")


@pytest.mark.parametrize(
    "add_entry",
    [
        pytest.param(_a_directory_named_like_a_uc, id="directorio con nombre de UC"),
        pytest.param(_a_file_without_the_uc_prefix, id="fichero sin el prefijo de UC"),
        pytest.param(_a_uc_nested_deeper_than_the_convention, id="UC demasiado anidado"),
        pytest.param(_a_glossary_inside_a_package, id="glosario mal ubicado"),
        pytest.param(_a_uc_whose_prefix_differs_in_case, id="prefijo con otra caja"),
        pytest.param(_a_uc_whose_extension_differs_in_case, id="extension con otra caja"),
        pytest.param(_a_non_markdown_file_among_the_glossaries, id="glosario que no es .md"),
    ],
)
def test_load_ignores_entries_that_are_not_ingestible_documents(
    tmp_path: Path, add_entry: Callable[[Path], None]
) -> None:
    """CU `Scenario Outline: Entradas que matchean el patrón pero no son documentos ingeribles`.

    El documento válido de base comprueba la segunda mitad del `Then`: el recorrido se completa.
    """
    _write(_use_cases_dir(tmp_path, "vendor-a") / "UC-OK-001.md")
    _write(_glossaries_dir(tmp_path) / "media-and-dam.md")
    add_entry(tmp_path)

    assert _names(tmp_path) == ["UC-OK-001.md", "media-and-dam.md"]


# ── Ausencias en el árbol de origen ──────────────────────────────────────────────────────────────


def _without_the_use_cases_dir_of_a_package(root: Path) -> None:
    _write(root / "packages" / "vendor-sin-uc" / "README.md")


def _without_the_shared_glossaries_dir(root: Path) -> None:
    """No crea nada: el directorio compartido de glosarios simplemente no existe."""


def _without_the_packages_dir(root: Path) -> None:
    """No crea nada: no hay ningún subdirectorio de package en el origen."""


@pytest.mark.parametrize(
    "make_absence",
    [
        pytest.param(_without_the_use_cases_dir_of_a_package, id="sin use-cases de un package"),
        pytest.param(_without_the_shared_glossaries_dir, id="sin el directorio de glosarios"),
        pytest.param(_without_the_packages_dir, id="sin el directorio de packages"),
    ],
)
def test_load_completes_the_walk_despite_absences(
    tmp_path: Path, make_absence: Callable[[Path], None]
) -> None:
    """CU `Scenario Outline: Ausencias en el árbol de origen no rompen el recorrido`."""
    _write(_use_cases_dir(tmp_path, "vendor-a") / "UC-OK-001.md")
    make_absence(tmp_path)

    assert "UC-OK-001.md" in _names(tmp_path)


def test_a_non_ingestible_entry_does_not_stop_discovering_the_rest_of_its_directory(
    tmp_path: Path,
) -> None:
    """Entradas no ingeribles que ordenan ANTES de un documento válido en su propio directorio —
    descarta un `continue` mutado a `break`: se saltaría el resto del directorio, no solo la entrada.
    """
    _write(_use_cases_dir(tmp_path, "vendor-a") / "AAA-notas.md")
    _write(_use_cases_dir(tmp_path, "vendor-a") / "UC-A-001.md")
    _write(_glossaries_dir(tmp_path) / "aaa-notas.txt")
    _write(_glossaries_dir(tmp_path) / "media-and-dam.md")

    assert _names(tmp_path) == ["UC-A-001.md", "media-and-dam.md"]


def test_a_package_without_use_cases_does_not_stop_discovering_later_packages(
    tmp_path: Path,
) -> None:
    """Un package sin `use-cases/` seguido (alfabéticamente) de otro CON UC — descarta un `continue`
    mutado a `break`: pararía el recorrido en el primer package sin casos de uso."""
    _write(tmp_path / "packages" / "a-vendor-sin-uc" / "README.md")
    _write(_use_cases_dir(tmp_path, "b-vendor-con-uc") / "UC-Z-001.md")

    assert _names(tmp_path) == ["UC-Z-001.md"]


# ── Fronteras del número de documentos descubiertos ──────────────────────────────────────────────


def _an_empty_tree(root: Path) -> None:
    """Ni subdirectorios de package ni glosarios."""


def _a_single_uc_and_no_glossary(root: Path) -> None:
    _write(_use_cases_dir(root, "vendor-a") / "UC-A-001.md")


def _several_ucs_and_several_glossaries(root: Path) -> None:
    _write(_use_cases_dir(root, "vendor-a") / "UC-A-001.md")
    _write(_use_cases_dir(root, "vendor-a") / "UC-A-002.md")
    _write(_use_cases_dir(root, "vendor-b") / "UC-B-001.md")
    _write(_glossaries_dir(root) / "media-and-dam.md")
    _write(_glossaries_dir(root) / "navigation-and-menus.md")


@pytest.mark.parametrize(
    ("build_tree", "expected"),
    [
        pytest.param(_an_empty_tree, 0, id="ningun package ni glosario"),
        pytest.param(_a_single_uc_and_no_glossary, 1, id="un unico UC"),
        pytest.param(_several_ucs_and_several_glossaries, 5, id="varios UC y varios glosarios"),
    ],
)
def test_load_discovers_the_expected_number_of_documents(
    tmp_path: Path, build_tree: Callable[[Path], None], expected: int
) -> None:
    """`Scenario Outline: Fronteras del número de documentos descubiertos` (añadido por la tarea)."""
    build_tree(tmp_path)

    assert len(list(load(tmp_path))) == expected


# ── Validación EAGER de la raíz ──────────────────────────────────────────────────────────────────


def test_load_with_a_nonexistent_root_raises_a_clear_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no existe"):
        load(tmp_path / "no-existe")


def test_load_with_a_file_instead_of_a_directory_raises_a_clear_error(tmp_path: Path) -> None:
    a_file = _write(tmp_path / "not-a-dir")

    with pytest.raises(FileNotFoundError):
        load(a_file)


def test_load_validates_the_root_before_returning_the_iterator(tmp_path: Path) -> None:
    """Mismo criterio que `loader.load`: el error de uso llega en la propia llamada, no al primer
    `next()` — un generador puro no lanzaría hasta la primera iteración."""
    with pytest.raises(FileNotFoundError):
        load(tmp_path / "no-existe")  # sin iterar el resultado


# ── Skip + log: ficheros y directorios ilegibles ─────────────────────────────────────────────────


def test_load_skips_an_unreadable_file_with_log(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    unreadable = _write(_use_cases_dir(tmp_path, "vendor-a") / "UC-A-001.md")
    unreadable.chmod(0o000)
    _write(_glossaries_dir(tmp_path) / "media-and-dam.md")
    try:
        with caplog.at_level("WARNING"):
            names = _names(tmp_path)
    finally:
        unreadable.chmod(0o644)

    assert names == ["media-and-dam.md"]
    assert "kb_doc_illegible" in caplog.text


def test_load_skips_a_file_with_invalid_encoding_with_log(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    bad_encoding = _use_cases_dir(tmp_path, "vendor-a") / "UC-A-001.md"
    bad_encoding.parent.mkdir(parents=True)
    bad_encoding.write_bytes(b"\xff\xfe\x00\x01---no es utf8---")

    with caplog.at_level("WARNING"):
        names = _names(tmp_path)

    assert names == []
    assert "kb_doc_illegible" in caplog.text


def test_load_skips_a_directory_without_read_permission_with_log(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """CU `Un directorio sin permisos de lectura se salta con log` — el `PermissionError` es al
    LISTAR el directorio, no al leer un fichero, y el recorrido continúa con el resto."""
    locked = _use_cases_dir(tmp_path, "vendor-a")
    _write(locked / "UC-A-001.md")
    _write(_use_cases_dir(tmp_path, "vendor-b") / "UC-B-001.md")
    locked.chmod(0o000)
    try:
        with caplog.at_level("WARNING"):
            names = _names(tmp_path)
    finally:
        locked.chmod(0o755)

    assert names == ["UC-B-001.md"]
    assert "kb_dir_illegible" in caplog.text
