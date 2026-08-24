"""Tests de `app.ingestion.packages_uc.parse` (tarea backend-kb-source-packages-uc-02).

Parseo del `source_type` **`packages-uc`** (formato REAL verificado): frontmatter
`id`/`dominio`/`estado`/`traza`, título desde el **primer H1 del cuerpo**, `package` derivado del
subdirectorio y traducido por los **alias inyectados**, y glosario plano ingerido íntegro.

Nivel **unit**, 100% in-memory: los `RawDoc` de los casos borde se construyen a mano con rutas que **no
existen en disco** (el parser es puro, no toca el filesystem); los caminos felices usan las fixtures
reales vía `load()`, para que el test se rompa si el formato de la fixture y el del parser divergen.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest
import structlog
from app.ingestion.loader import RawDoc
from app.ingestion.packages_uc import load, parse
from app.ingestion.parser import GLOSARIO_UC_ID_PREFIX, ParsedUC, ParseError

_FIXTURES_ROOT = Path(__file__).parent / "fixtures" / "kb_packages_uc"

# Alias de deployment: subdirectorio de package (genérico en las fixtures) → valor del enum `Package`.
_ALIASES = {"vendor-core": "syntax-core", "vendor-render": "syntax-render"}

_KB_ROOT = Path("/kb")
_MTIME = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _structlog_via_stdlib_for_caplog():
    """`caplog` captura el `logging` estándar; `structlog` usa su propio `PrintLoggerFactory` por
    defecto (mismo patrón que `test_loader.py`/`test_packages_uc_loader.py`)."""
    structlog.configure(
        processors=[structlog.processors.KeyValueRenderer(key_order=["event"])],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
    )
    yield
    structlog.reset_defaults()


# ── Helpers ─────────────────────────────────────────────────────────────────────────────────────


def _raw(relative_path: str, content: str) -> RawDoc:
    """Un `RawDoc` sintético bajo `_KB_ROOT` — la ruta NO existe en disco (el parser es puro)."""
    return RawDoc(path=_KB_ROOT / relative_path, content=content, mtime=_MTIME)


def _uc(relative_path: str, content: str) -> RawDoc:
    return _raw(f"packages/vendor-core/docs/aiup/use-cases/{relative_path}", content)


def _parse(raw: RawDoc, aliases: dict[str, str] | None = None) -> ParsedUC | ParseError:
    return parse(raw, kb_root=_KB_ROOT, package_aliases=_ALIASES if aliases is None else aliases)


def _fixture_doc(name: str) -> RawDoc:
    docs = {doc.path.name: doc for doc in load(_FIXTURES_ROOT)}
    return docs[name]


def _parse_fixture(name: str, aliases: dict[str, str] | None = None) -> ParsedUC | ParseError:
    return parse(
        _fixture_doc(name),
        kb_root=_FIXTURES_ROOT,
        package_aliases=_ALIASES if aliases is None else aliases,
    )


_VALID_UC = """---
id: UC-CORE-001
dominio: platform-and-devex
estado: draft
traza:
  - src/config/loadConfig.ts
---

# Carga de la configuración

## Comportamiento

Texto.
"""


# ── Camino feliz: un UC real del formato verificado ──────────────────────────────────────────────


def test_parses_a_real_uc_taking_the_title_from_the_h1_and_the_package_from_the_alias() -> None:
    """CU `Ingesta de un UC del formato real` — la parte de parseo."""
    parsed = _parse_fixture("UC-CORE-001-carga-de-la-configuracion.md")

    assert isinstance(parsed, ParsedUC)
    assert parsed.uc_id == "UC-CORE-001"
    assert parsed.domain == "platform-and-devex"
    assert parsed.estado == "draft"
    assert parsed.title == "Carga de la configuración del proyecto"
    assert parsed.package == "syntax-core"
    assert parsed.traza == ["src/config/loadConfig.ts", "src/config/schema.ts"]


def test_the_package_comes_from_the_path_not_from_the_frontmatter() -> None:
    """Dos UC de subdirectorios de package distintos, ninguno con `package` en su frontmatter."""
    core = _parse_fixture("UC-CORE-002-contenido-relacionado.md")
    render = _parse_fixture("UC-RENDER-001-render-de-una-pagina.md")

    assert isinstance(core, ParsedUC) and isinstance(render, ParsedUC)
    assert (core.package, render.package) == ("syntax-core", "syntax-render")


def test_the_body_drops_the_frontmatter_block_and_keeps_the_rest() -> None:
    parsed = _parse(_uc("UC-CORE-001.md", _VALID_UC))

    assert isinstance(parsed, ParsedUC)
    assert not parsed.body.lstrip().startswith("---")
    assert "## Comportamiento" in parsed.body


def test_the_updated_timestamp_is_the_mtime_captured_by_the_loader() -> None:
    """El parser no toca el filesystem: el `mtime` viene del `RawDoc` que produjo `load()`."""
    parsed = _parse(_uc("UC-CORE-001.md", _VALID_UC))

    assert isinstance(parsed, ParsedUC)
    assert parsed.updated == _MTIME


def test_the_source_url_is_the_path_relative_to_the_kb_root() -> None:
    """Escenario añadido: `La ruta de origen se deriva de la ruta relativa a la raíz de la KB`."""
    parsed = _parse(_uc("UC-CORE-001.md", _VALID_UC))

    assert isinstance(parsed, ParsedUC)
    assert parsed.source_url == "packages/vendor-core/docs/aiup/use-cases/UC-CORE-001.md"


def test_relacionado_is_empty_because_wiki_links_are_out_of_scope() -> None:
    """`design-review` #5: el campo no se persiste ni se consume — no se parsea (aún)."""
    parsed = _parse_fixture("UC-CORE-002-contenido-relacionado.md")

    assert isinstance(parsed, ParsedUC)
    assert "[[UC-CORE-001]]" in parsed.body  # el wiki-link SÍ está en el cuerpo…
    assert parsed.relacionado == []  # …pero no se extrae


def test_the_body_keeps_the_acceptance_criteria_labels_untouched() -> None:
    """Escenario añadido: `El cuerpo conserva las etiquetas de criterio de aceptación` — no se
    replica el `stripAcLabels` del generador de site de la fuente (decisión de `grilling`)."""
    parsed = _parse_fixture("UC-CORE-001-carga-de-la-configuracion.md")

    assert isinstance(parsed, ParsedUC)
    assert (
        "- **AC1** — Un fichero de configuración ausente nunca impide el arranque." in parsed.body
    )


def test_no_package_discrepancy_is_logged_in_this_format(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Escenario añadido: `En este formato no existe discrepancia de package que registrar` (RN-4) —
    el `package` tiene una sola fuente (ruta + alias), así que no hay nada que comparar."""
    with caplog.at_level("INFO"):
        parsed = _parse_fixture("UC-CORE-001-carga-de-la-configuracion.md")

    assert isinstance(parsed, ParsedUC)
    assert "kb_package_discrepancia" not in caplog.text


# ── Título: primer H1 del cuerpo, fuera de los bloques de código ─────────────────────────────────


def test_a_hash_line_inside_a_code_fence_is_not_mistaken_for_the_title() -> None:
    """CU `Una línea de comentario dentro de un bloque de código no se confunde con el título` — el
    riesgo real de bug de esta tarea (en `parser.py` el título venía del frontmatter)."""
    content = """---
id: UC-CORE-001
dominio: platform-and-devex
estado: draft
---

```bash
# esto es un comentario de shell, no el título
echo hola
```

# Título de verdad
"""
    parsed = _parse(_uc("UC-CORE-001.md", content))

    assert isinstance(parsed, ParsedUC)
    assert parsed.title == "Título de verdad"


def test_an_unclosed_code_fence_swallows_every_later_hash_line() -> None:
    """Mismo criterio que `chunker._split_sections`: un fence sin cerrar se traga el resto del
    documento — no quedan H1 válidos, así que el documento es malformado (1i), no un título falso."""
    content = """---
id: UC-CORE-001
dominio: platform-and-devex
estado: draft
---

```text
# no soy un título
"""
    parsed = _parse(_uc("UC-CORE-001.md", content))

    assert isinstance(parsed, ParseError)


def test_with_several_h1_headings_the_first_one_wins() -> None:
    """CU `Con varios encabezados principales se toma el primero`."""
    content = _VALID_UC + "\n# Segundo título\n"
    parsed = _parse(_uc("UC-CORE-001.md", content))

    assert isinstance(parsed, ParsedUC)
    assert parsed.title == "Carga de la configuración"


def test_a_uc_without_an_h1_is_skipped_with_log(caplog: pytest.LogCaptureFixture) -> None:
    """CU `Un UC sin encabezado principal se salta` (extensión 1i)."""
    content = """---
id: UC-CORE-001
dominio: platform-and-devex
estado: draft
---

## Comportamiento

Sin H1 en ninguna parte.
"""
    with caplog.at_level("WARNING"):
        parsed = _parse(_uc("UC-CORE-001.md", content))

    assert isinstance(parsed, ParseError)
    assert "kb_doc_malformado" in caplog.text


def test_a_heading_of_level_two_or_more_is_not_taken_as_the_title() -> None:
    """`##` no es un H1: descarta una comparación de nivel demasiado laxa."""
    content = """---
id: UC-CORE-001
dominio: platform-and-devex
estado: draft
---

## No soy H1

# Sí lo soy
"""
    parsed = _parse(_uc("UC-CORE-001.md", content))

    assert isinstance(parsed, ParsedUC)
    assert parsed.title == "Sí lo soy"


def test_the_title_is_stripped_of_surrounding_whitespace() -> None:
    content = _VALID_UC.replace("# Carga de la configuración", "#   Carga con espacios   ")
    parsed = _parse(_uc("UC-CORE-001.md", content))

    assert isinstance(parsed, ParsedUC)
    assert parsed.title == "Carga con espacios"


# ── `traza`: normalización defensiva (extensión 1j) ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("declaration", "expected"),
    [
        pytest.param("traza:\n  - a.ts\n  - b.ts", ["a.ts", "b.ts"], id="una lista de rutas"),
        pytest.param("traza: a.ts", ["a.ts"], id="un valor suelto"),
        pytest.param("traza: []", [], id="una lista vacia"),
        pytest.param("estado: draft", [], id="ausente"),
        pytest.param("traza:\n  - 1\n  - true", ["1", "True"], id="elementos no textuales"),
    ],
)
def test_traza_is_normalised_however_it_is_declared(declaration: str, expected: list[str]) -> None:
    """CU `Scenario Outline: Normalización de la traza según cómo venga declarada` (extensión 1j).

    La fila "ausente" repite `estado: draft` (ya presente) para no declarar `traza` en absoluto.
    """
    content = f"""---
id: UC-CORE-001
dominio: platform-and-devex
estado: draft
{declaration}
---

# Título
"""
    parsed = _parse(_uc("UC-CORE-001.md", content))

    assert isinstance(parsed, ParsedUC)
    assert parsed.traza == expected


def test_a_non_list_non_string_traza_is_coerced_instead_of_rejected() -> None:
    """Decisión declarada sin precedente en la spec: `traza` es metadato opcional sin consumidor hoy;
    coercionar nunca pierde información ni aborta el batch."""
    content = _VALID_UC.replace("traza:\n  - src/config/loadConfig.ts", "traza: 42")
    parsed = _parse(_uc("UC-CORE-001.md", content))

    assert isinstance(parsed, ParsedUC)
    assert parsed.traza == ["42"]


# ── `package`: ruta + alias inyectado (extensión 1h) ─────────────────────────────────────────────


def test_a_package_directory_without_a_configured_alias_is_skipped_with_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """CU `Un package sin alias configurado se salta` (extensión 1h, caso a)."""
    with caplog.at_level("WARNING"):
        parsed = _parse(_uc("UC-CORE-001.md", _VALID_UC), aliases={"otro-vendor": "syntax-core"})

    assert isinstance(parsed, ParseError)
    assert "kb_doc_malformado" in caplog.text


def test_with_no_aliases_configured_at_all_nothing_is_parsed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """El default (`kb_package_aliases` vacío) no ingiere nada — comportamiento esperado, no un bug
    (extensión 1l; el aviso al operador es de la `-03`)."""
    with caplog.at_level("WARNING"):
        parsed = _parse(_uc("UC-CORE-001.md", _VALID_UC), aliases={})

    assert isinstance(parsed, ParseError)
    assert "kb_doc_malformado" in caplog.text


def test_an_alias_pointing_to_a_package_outside_the_catalogue_is_skipped_with_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """CU `Un alias que apunta a un package inexistente se salta` (extensión 1h, caso b).

    `design-review` #6: sin validarlo aquí, el typo llegaría a `pipeline._to_draft()` → `Package(...)`
    → `ValueError` → `except Exception` genérico de la CLI ("error inesperado").
    """
    with caplog.at_level("WARNING"):
        parsed = _parse(_uc("UC-CORE-001.md", _VALID_UC), aliases={"vendor-core": "syntax-typo"})

    assert isinstance(parsed, ParseError)
    assert "kb_doc_malformado" in caplog.text


def test_a_path_without_the_package_segment_is_skipped_as_malformed() -> None:
    """CU `Una ruta que no sigue la convención de package se salta como malformado` — nunca un
    `IndexError`/`ValueError` de un `split()`/`index()` ingenuo."""
    parsed = _parse(_raw("suelto/UC-CORE-001.md", _VALID_UC))

    assert isinstance(parsed, ParseError)


def test_the_package_is_the_segment_right_after_packages_wherever_it_sits() -> None:
    """El criterio es "la ruta **contiene** el segmento `packages/<pkg>/`": el `<pkg>` es el que va
    justo DESPUÉS de `packages/`, no el primer segmento de la ruta."""
    parsed = _parse(_raw("sub/packages/vendor-core/docs/aiup/use-cases/UC-1.md", _VALID_UC))

    assert isinstance(parsed, ParsedUC)
    assert parsed.package == "syntax-core"


def test_a_path_that_ends_in_the_package_segment_is_skipped_without_raising() -> None:
    """Frontera degenerada: no hay ningún segmento **después** de `packages` que traducir. Debe dar
    un skip limpio, nunca un `IndexError` por indexar más allá del final de la ruta."""
    raw = RawDoc(path=_KB_ROOT / "packages", content=_VALID_UC, mtime=_MTIME)

    parsed = parse(raw, kb_root=_KB_ROOT, package_aliases=_ALIASES)

    assert isinstance(parsed, ParseError)


def test_a_path_outside_the_kb_root_is_skipped_as_malformed() -> None:
    """`relative_to()` lanzaría `ValueError`: se convierte en un skip limpio, mismo criterio."""
    raw = RawDoc(path=Path("/otro/sitio/UC-1.md"), content=_VALID_UC, mtime=_MTIME)

    parsed = parse(raw, kb_root=_KB_ROOT, package_aliases=_ALIASES)

    assert isinstance(parsed, ParseError)


def test_a_package_segment_without_a_directory_after_it_is_skipped_as_malformed() -> None:
    """Frontera: la ruta acaba en `packages/` — no hay `<pkg>` que traducir."""
    parsed = _parse(_raw("packages/UC-CORE-001.md", _VALID_UC))

    assert isinstance(parsed, ParseError)


# ── Clases de equivalencia de "UC malformado" ────────────────────────────────────────────────────

_SIN_FRONTMATTER = "# Título\n\nTexto suelto.\n"
_YAML_INVALIDO = "---\nid: [sin cerrar\n---\n\n# Título\n"
_NO_MAPEO = "---\n- uno\n- dos\n---\n\n# Título\n"
_SIN_ID = "---\ndominio: platform-and-devex\nestado: draft\n---\n\n# Título\n"
_ID_VACIO = '---\nid: ""\ndominio: platform-and-devex\nestado: draft\n---\n\n# Título\n'
_ID_NO_TEXTUAL = "---\nid: 123\ndominio: platform-and-devex\nestado: draft\n---\n\n# Título\n"
_DOMINIO_FUERA = "---\nid: UC-X-001\ndominio: no-existe\nestado: draft\n---\n\n# Título\n"
_ESTADO_FUERA = (
    "---\nid: UC-X-001\ndominio: platform-and-devex\nestado: inventado\n---\n\n# Título\n"
)


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(_SIN_FRONTMATTER, id="sin bloque frontmatter"),
        pytest.param(_YAML_INVALIDO, id="YAML sintacticamente invalido"),
        pytest.param(_NO_MAPEO, id="frontmatter que no es un mapeo"),
        pytest.param(_SIN_ID, id="sin la clave del identificador"),
        pytest.param(_ID_VACIO, id="identificador vacio"),
        pytest.param(_ID_NO_TEXTUAL, id="identificador no textual"),
        pytest.param(_DOMINIO_FUERA, id="dominio fuera del catalogo"),
        pytest.param(_ESTADO_FUERA, id="estado fuera del catalogo"),
    ],
)
def test_malformed_ucs_are_skipped_with_log(content: str, caplog: pytest.LogCaptureFixture) -> None:
    """`Scenario Outline: Clases de equivalencia de "UC malformado"` + CU `Un identificador de tipo
    no textual se salta como malformado`."""
    with caplog.at_level("WARNING"):
        parsed = _parse(_uc("UC-X-001.md", content))

    assert isinstance(parsed, ParseError)
    assert "kb_doc_malformado" in caplog.text


def test_the_parse_error_carries_the_path_and_a_reason() -> None:
    parsed = _parse(_uc("UC-X-001.md", _SIN_FRONTMATTER))

    assert isinstance(parsed, ParseError)
    assert parsed.path == _KB_ROOT / "packages/vendor-core/docs/aiup/use-cases/UC-X-001.md"
    assert parsed.reason


def test_an_adversarial_yaml_tag_is_rejected_without_executing_anything() -> None:
    """Escenario añadido: `Un frontmatter con un tag YAML adversario se rechaza sin ejecutar nada`.

    Anti-patrón: `yaml.load` (sin `safe_`) construiría el objeto. `safe_load` levanta
    `ConstructorError` (subclase de `YAMLError`) → malformado.
    """
    content = "---\nid: !!python/object/apply:os.system ['echo pwned']\n---\n\n# Título\n"

    parsed = _parse(_uc("UC-X-001.md", content))

    assert isinstance(parsed, ParseError)


# ── Glosario: fichero plano, íntegro (extensión 2a) ──────────────────────────────────────────────


def test_a_glossary_is_ingested_whole_under_the_synthetic_uc_id() -> None:
    """CU `El glosario del formato real se ingiere íntegro` (extensión 2a) — la parte de parseo."""
    parsed = _parse_fixture("authoring-and-editor.md")

    assert isinstance(parsed, ParsedUC)
    assert parsed.uc_id == f"{GLOSARIO_UC_ID_PREFIX}authoring-and-editor"
    assert parsed.domain == "authoring-and-editor"
    assert parsed.body == _fixture_doc("authoring-and-editor.md").content
    assert "## Estados" in parsed.body  # NO se recorta ningún bloque `## Glosario`


def test_a_glossary_has_no_package_and_no_estado() -> None:
    """Igual que `parser._parse_index`: qué persistir para un glosario ya lo decidió el pipeline."""
    parsed = _parse_fixture("platform-and-devex.md")

    assert isinstance(parsed, ParsedUC)
    assert (parsed.package, parsed.estado, parsed.traza) == ("", "", [])


def test_a_glossary_takes_its_title_from_its_own_h1() -> None:
    """Decisión de esta tarea, sin precedente en la spec (el task file no fija el `title` del
    glosario): el H1 real es más fiel para las citas que un título sintético."""
    parsed = _parse_fixture("authoring-and-editor.md")

    assert isinstance(parsed, ParsedUC)
    assert parsed.title == "Glosario — Edición de contenido"


def test_an_empty_glossary_is_a_valid_glossary_with_an_empty_body() -> None:
    """CU `Un glosario vacío se ingiere como glosario sin contenido` — no es un malformado."""
    parsed = _parse(_raw("docs/aiup/glossaries/media-and-dam.md", ""))

    assert isinstance(parsed, ParsedUC)
    assert parsed.body == ""
    assert parsed.uc_id == f"{GLOSARIO_UC_ID_PREFIX}media-and-dam"


def test_an_empty_glossary_falls_back_to_a_synthetic_title() -> None:
    """Sin H1 del que tirar, el glosario NO se descarta (a diferencia de un UC): título sintético."""
    parsed = _parse(_raw("docs/aiup/glossaries/media-and-dam.md", ""))

    assert isinstance(parsed, ParsedUC)
    assert parsed.title == "Glosario — media-and-dam"


def test_a_glossary_of_a_domain_outside_the_catalogue_is_skipped_with_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Escenario añadido: `Un glosario de un dominio fuera del catálogo se salta`."""
    with caplog.at_level("WARNING"):
        parsed = _parse(_raw("docs/aiup/glossaries/dominio-inventado.md", "# Glosario\n"))

    assert isinstance(parsed, ParseError)
    assert "kb_doc_malformado" in caplog.text


def test_a_glossary_needs_no_package_alias() -> None:
    """Un glosario no vive bajo `packages/`: los alias no le aplican y su ausencia no lo descarta."""
    parsed = _parse(_raw("docs/aiup/glossaries/media-and-dam.md", "# G\n"), aliases={})

    assert isinstance(parsed, ParsedUC)


def test_a_document_in_a_directory_sorting_before_the_glossaries_one_is_still_a_uc() -> None:
    """El discriminador glosario/UC es el nombre **exacto** del directorio padre, no una comparación
    de orden alfabético: `casos` ordena antes que `glossaries` y aun así es un UC."""
    parsed = _parse(_raw("packages/vendor-core/docs/aiup/casos/UC-1.md", _VALID_UC))

    assert isinstance(parsed, ParsedUC)
    assert parsed.uc_id == "UC-CORE-001"


def test_the_glossary_source_url_is_relative_to_the_kb_root() -> None:
    parsed = _parse(_raw("docs/aiup/glossaries/media-and-dam.md", "# G\n"))

    assert isinstance(parsed, ParsedUC)
    assert parsed.source_url == "docs/aiup/glossaries/media-and-dam.md"
