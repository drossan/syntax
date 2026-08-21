"""Tests de app.ingestion.parser (tarea backend-kb-ingestion-03). Puro (sin filesystem real, salvo
`source_url`/`mtime` que solo necesitan un `Path`/`datetime`, no un fichero existente en disco)."""

import dataclasses
from datetime import UTC, datetime
from pathlib import Path

import pytest
import structlog
from app.ingestion.loader import RawDoc
from app.ingestion.parser import ParsedUC, ParseError, parse

_KB_ROOT = Path("/kb/domains")
_MTIME = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _structlog_via_stdlib_for_caplog():
    """Ver `test_loader.py` — mismo patrón de reenvío a `caplog`."""
    structlog.configure(
        processors=[structlog.processors.KeyValueRenderer(key_order=["event"])],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
    )
    yield
    structlog.reset_defaults()


def _uc_doc(
    *,
    uc_id: str = "UC-CX-001",
    domain: str = "authoring-and-editor",
    package: str = "syntax-cx",
    title: str = "Editor colaborativo",
    estado: str = "active",
    trazabilidad_package: str | None = None,
    traza: str | None = "`app/services/editor.py`, `app/api/editor.py`",
    relacionado_line: str | None = (
        "Relacionado: [Borradores](/domains/authoring-and-editor/uc/UC-CX-002)"
    ),
    include_trazabilidad: bool = True,
    frontmatter: str | None = None,
    path: Path | None = None,
) -> RawDoc:
    fm = (
        frontmatter
        if frontmatter is not None
        else f'title: "{title}"\ndomain: {domain}\npackage: {package}\nuc: {uc_id}'
    )
    trazabilidad_block = ""
    if include_trazabilidad:
        traza_line = f"- **Traza**: {traza}\n" if traza else ""
        trazabilidad_block = (
            "\n::: info Trazabilidad\n"
            f"- **Estado**: {estado}\n"
            f"- **Package**: {trazabilidad_package or package}\n"
            f"{traza_line}"
            ":::\n"
        )
    relacionado = f"\n{relacionado_line}\n" if relacionado_line else ""
    content = (
        f"---\n{fm}\n---\n\n# {title}\n\n## Comportamiento\n\nTexto.\n{trazabilidad_block}"
        f"{relacionado}"
    )
    resolved_path = path or _KB_ROOT / domain / "uc" / f"{uc_id}.md"
    return RawDoc(path=resolved_path, content=content, mtime=_MTIME)


def _index_doc(
    *,
    domain: str = "authoring-and-editor",
    glosario_body: str | None = "- **A** — a.",
    extra: str = "",
) -> RawDoc:
    glosario = f"## Glosario\n\n{glosario_body}\n\n" if glosario_body is not None else ""
    content = f"# {domain}\n\n## Casos de uso\n\n{extra}\n{glosario}## Todos los dominios\n\n- x\n"
    return RawDoc(path=_KB_ROOT / domain / "index.md", content=content, mtime=_MTIME)


# ── camino feliz (UC) ──


def test_parses_a_valid_uc_extracting_frontmatter_and_trazabilidad() -> None:
    result = parse(_uc_doc(), kb_root=_KB_ROOT)

    assert isinstance(result, ParsedUC)
    assert result.uc_id == "UC-CX-001"
    assert result.domain == "authoring-and-editor"
    assert result.package == "syntax-cx"
    assert result.estado == "active"
    assert result.title == "Editor colaborativo"
    assert result.traza == ["app/services/editor.py", "app/api/editor.py"]


def test_source_url_is_derived_from_the_path_relative_to_kb_root() -> None:
    result = parse(_uc_doc(), kb_root=_KB_ROOT)

    assert isinstance(result, ParsedUC)
    assert result.source_url == "authoring-and-editor/uc/UC-CX-001.md"


def test_updated_is_taken_from_raw_doc_mtime_not_the_filesystem() -> None:
    result = parse(_uc_doc(), kb_root=_KB_ROOT)

    assert isinstance(result, ParsedUC)
    assert result.updated == _MTIME


def test_relacionado_is_extracted_as_the_list_of_linked_targets() -> None:
    result = parse(
        _uc_doc(
            relacionado_line=(
                "Relacionado: [Borradores](/domains/authoring-and-editor/uc/UC-CX-002), "
                "[Permisos](/domains/identity-and-permissions/uc/UC-ID-005)"
            )
        ),
        kb_root=_KB_ROOT,
    )

    assert isinstance(result, ParsedUC)
    assert result.relacionado == [
        "/domains/authoring-and-editor/uc/UC-CX-002",
        "/domains/identity-and-permissions/uc/UC-ID-005",
    ]


def test_relacionado_is_absent_when_there_is_no_relacionado_line() -> None:
    result = parse(_uc_doc(relacionado_line=None), kb_root=_KB_ROOT)

    assert isinstance(result, ParsedUC)
    assert result.relacionado == []


def test_traza_is_empty_when_trazabilidad_has_no_traza_field() -> None:
    result = parse(_uc_doc(traza=None), kb_root=_KB_ROOT)

    assert isinstance(result, ParsedUC)
    assert result.traza == []


def test_body_excludes_the_frontmatter_block() -> None:
    result = parse(_uc_doc(), kb_root=_KB_ROOT)

    assert isinstance(result, ParsedUC)
    assert not result.body.startswith("---")
    assert "## Comportamiento" in result.body


def test_parsed_uc_is_immutable() -> None:
    result = parse(_uc_doc(), kb_root=_KB_ROOT)

    assert isinstance(result, ParsedUC)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.title = "otro"  # type: ignore[misc]


def test_parse_error_is_immutable() -> None:
    result = parse(_uc_doc(uc_id=""), kb_root=_KB_ROOT)

    assert isinstance(result, ParseError)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.reason = "otro"  # type: ignore[misc]


def test_a_uc_named_lexicographically_after_index_md_is_still_parsed_as_a_uc() -> None:
    """`raw.path.name == "index.md"` decide la rama; un nombre que ordena DESPUÉS de "index.md"
    (empieza por minúscula > 'i') descarta un `==` mutado a `>=`, que también daría verdadero."""
    doc = _uc_doc(path=_KB_ROOT / "authoring-and-editor" / "uc" / "zz-no-es-index.md")

    result = parse(doc, kb_root=_KB_ROOT)

    assert isinstance(result, ParsedUC)
    assert result.uc_id == "UC-CX-001"


# ── package: precedencia + log ──


def test_frontmatter_package_wins_over_trazabilidad_package(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("INFO"):
        result = parse(
            _uc_doc(package="syntax-core", trazabilidad_package="syntax-api"), kb_root=_KB_ROOT
        )

    assert isinstance(result, ParsedUC)
    assert result.package == "syntax-core"
    assert "kb_package_discrepancia" in caplog.text


def test_matching_package_does_not_log_a_discrepancy(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("INFO"):
        result = parse(
            _uc_doc(package="syntax-cx", trazabilidad_package="syntax-cx"), kb_root=_KB_ROOT
        )

    assert isinstance(result, ParsedUC)
    assert "kb_package_discrepancia" not in caplog.text


def test_frontmatter_package_wins_even_when_alphabetically_smaller_than_trazabilidads(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Dirección opuesta a `test_frontmatter_package_wins_over_trazabilidad_package`: descarta un
    `!=` mutado a `<` (aquí `trazabilidad_package < package` sería falso pese a ser distintos)."""
    with caplog.at_level("INFO"):
        result = parse(
            _uc_doc(package="syntax-api", trazabilidad_package="syntax-core"), kb_root=_KB_ROOT
        )

    assert isinstance(result, ParsedUC)
    assert result.package == "syntax-api"
    assert "kb_package_discrepancia" in caplog.text


# ── catálogo ──


def test_domain_outside_the_catalog_is_skipped(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING"):
        result = parse(_uc_doc(domain="not-a-real-domain"), kb_root=_KB_ROOT)

    assert isinstance(result, ParseError)
    assert "kb_doc_malformado" in caplog.text


def test_package_outside_the_catalog_is_skipped() -> None:
    result = parse(_uc_doc(package="not-a-real-package"), kb_root=_KB_ROOT)

    assert isinstance(result, ParseError)


def test_estado_outside_the_catalog_is_skipped() -> None:
    result = parse(_uc_doc(estado="not-a-real-estado"), kb_root=_KB_ROOT)

    assert isinstance(result, ParseError)


# ── documento malformado (Scenario Outline) ──


@pytest.mark.parametrize(
    "make_doc",
    [
        lambda: RawDoc(
            path=_KB_ROOT / "authoring-and-editor" / "uc" / "UC-CX-001.md",
            content="# Sin frontmatter\n\ncontenido\n",
            mtime=_MTIME,
        ),
        lambda: _uc_doc(frontmatter="uc: [no cierra la lista"),
        lambda: _uc_doc(
            frontmatter='title: "Sin uc"\ndomain: authoring-and-editor\npackage: syntax-cx'
        ),
        lambda: _uc_doc(
            frontmatter='title: "Uc vacío"\ndomain: authoring-and-editor\npackage: syntax-cx\nuc: ""'
        ),
        lambda: _uc_doc(include_trazabilidad=False),
    ],
    ids=[
        "sin-bloque-frontmatter",
        "yaml-invalido",
        "sin-clave-uc",
        "uc-vacio",
        "sin-trazabilidad",
    ],
)
def test_malformed_document_variants_are_skipped_without_raising(make_doc) -> None:
    result = parse(make_doc(), kb_root=_KB_ROOT)

    assert isinstance(result, ParseError)


def test_a_yaml_tag_that_would_instantiate_a_python_object_is_rejected_not_executed() -> None:
    """`yaml.safe_load` (nunca `yaml.load`) rechaza el tag como frontmatter no-mapeo/erróneo, sin
    construir ningún objeto Python — el `ParseError` en sí ya demuestra que no se ejecutó nada."""
    doc = _uc_doc(frontmatter="uc: !!python/object/apply:os.getcwd []")

    result = parse(doc, kb_root=_KB_ROOT)

    assert isinstance(result, ParseError)


# ── index.md ──


def test_index_md_keeps_only_the_glosario_block_as_body() -> None:
    result = parse(
        _index_doc(glosario_body="- **Editor** — componente.", extra="- [UC](./uc/UC-X.md)"),
        kb_root=_KB_ROOT,
    )

    assert isinstance(result, ParsedUC)
    # Match EXACTO (no solo "contiene"): descarta un `.group(1)` mutado a `.group(0)`, que
    # incluiría la línea de cabecera "## Glosario" dentro del body.
    assert result.body == "- **Editor** — componente."


def test_index_md_without_a_glosario_block_is_not_an_error() -> None:
    result = parse(_index_doc(glosario_body=None), kb_root=_KB_ROOT)

    assert isinstance(result, ParsedUC)
    assert result.body == ""


def test_index_md_uc_id_is_synthetic_and_never_collides_with_a_real_uc_id() -> None:
    result = parse(_index_doc(domain="authoring-and-editor"), kb_root=_KB_ROOT)

    assert isinstance(result, ParsedUC)
    assert result.uc_id == "__glosario__:authoring-and-editor"
    assert not result.uc_id.startswith("UC-")


def test_index_md_domain_is_derived_from_the_parent_directory_name() -> None:
    result = parse(_index_doc(domain="sites-domains-instances"), kb_root=_KB_ROOT)

    assert isinstance(result, ParsedUC)
    assert result.domain == "sites-domains-instances"


def test_index_md_in_a_directory_outside_the_domain_catalog_is_skipped() -> None:
    doc = RawDoc(
        path=_KB_ROOT / "not-a-real-domain" / "index.md",
        content="# X\n\n## Glosario\n\n- **A** — a.\n",
        mtime=_MTIME,
    )

    result = parse(doc, kb_root=_KB_ROOT)

    assert isinstance(result, ParseError)


def test_index_md_source_url_is_also_relative_to_kb_root() -> None:
    result = parse(_index_doc(domain="authoring-and-editor"), kb_root=_KB_ROOT)

    assert isinstance(result, ParsedUC)
    assert result.source_url == "authoring-and-editor/index.md"
