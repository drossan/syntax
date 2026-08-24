"""Tests de app.ingestion.chunker (tarea backend-kb-ingestion-04). `tiktoken` real (sin fake): la
palabra "a" repetida y separada por espacios tokeniza a razón de 1 token por repetición en el
encoding de `text-embedding-3-small` (verificado en esta sesión) — permite construir texto con un
conteo de tokens EXACTO para las fronteras de presupuesto.
"""

import dataclasses
from datetime import UTC, datetime

import pytest
import structlog
import tiktoken
from app.ingestion.chunker import Chunk, chunk, get_encoding
from app.ingestion.parser import GLOSARIO_UC_ID_PREFIX, ParsedUC

_ENCODING = tiktoken.encoding_for_model("text-embedding-3-small")
_MTIME = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _structlog_via_stdlib_for_caplog():
    structlog.configure(
        processors=[structlog.processors.KeyValueRenderer(key_order=["event"])],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
    )
    yield
    structlog.reset_defaults()


def _n_tokens(n: int) -> str:
    """Texto con EXACTAMENTE `n` tokens (`_ENCODING`)."""
    return " ".join(["a"] * n)


def _parsed(
    body: str,
    *,
    uc_id: str = "UC-CX-001",
    domain: str = "authoring-and-editor",
    package: str = "syntax-cx",
    estado: str = "active",
) -> ParsedUC:
    return ParsedUC(
        uc_id=uc_id,
        domain=domain,
        package=package,
        estado=estado,
        title="T",
        traza=[],
        relacionado=[],
        source_url="x",
        updated=_MTIME,
        body=body,
    )


def _chunk(parsed: ParsedUC, *, budget: int = 800) -> list[Chunk]:
    return chunk(parsed, token_budget=budget, encoding=_ENCODING)


# ── camino feliz ──


def test_standard_h2_sections_produce_one_chunk_each() -> None:
    body = (
        "## Comportamiento\n\nTexto de comportamiento.\n\n"
        "## Conceptos\n\nTexto de conceptos.\n\n"
        "## Reglas e invariantes\n\nTexto de reglas.\n\n"
        "## Detalles observados en QA\n\nTexto de QA.\n\n"
        "## Fidelidad\n\nTexto de fidelidad.\n"
    )
    result = _chunk(_parsed(body))

    assert [c.section_type for c in result] == [
        "comportamiento",
        "conceptos",
        "reglas",
        "detalles-qa",
        "fidelidad",
    ]
    assert [c.ordinal for c in result] == [0, 1, 2, 3, 4]


def test_chunk_inherits_the_5_facets_from_the_document() -> None:
    result = _chunk(_parsed("## Comportamiento\n\nTexto.\n"))

    assert len(result) == 1
    assert result[0].uc_id == "UC-CX-001"
    assert result[0].domain == "authoring-and-editor"
    assert result[0].package == "syntax-cx"
    assert result[0].estado == "active"


def test_get_encoding_returns_a_usable_tiktoken_encoding() -> None:
    encoding = get_encoding("text-embedding-3-small")

    assert len(encoding.encode("hola")) > 0


# ── tolerancia H2 ──


def test_a_missing_section_is_absent_but_the_rest_is_chunked() -> None:
    body = "## Comportamiento\n\nTexto.\n\n## Fidelidad\n\nOtro texto.\n"

    result = _chunk(_parsed(body))

    assert [c.section_type for c in result] == ["comportamiento", "fidelidad"]


def test_a_renamed_h2_variant_normalizes_to_the_base_section_type() -> None:
    body = "## Reglas e invariantes (draft — comportamiento esperado)\n\nTexto.\n"

    result = _chunk(_parsed(body))

    assert result[0].section_type == "reglas"


def test_content_before_the_first_h2_becomes_an_intro_chunk() -> None:
    body = "Este es el párrafo intro.\n\n## Comportamiento\n\nTexto.\n"

    result = _chunk(_parsed(body))

    assert result[0].section_type == "intro"
    assert "párrafo intro" in result[0].content
    assert result[1].section_type == "comportamiento"


def test_an_unknown_loose_h2_keeps_its_own_slug() -> None:
    body = "## Matriz (resumen observable)\n\nTexto.\n"

    result = _chunk(_parsed(body))

    assert result[0].section_type == "matriz-resumen-observable"


def test_a_document_with_no_h2_and_no_intro_content_yields_no_chunks() -> None:
    assert _chunk(_parsed("   \n\n")) == []


# ── presupuesto de tokens ──


def _two_blocks(total_tokens: int) -> str:
    """Dos párrafos (separados por línea en blanco) cuya suma es `total_tokens` — a diferencia de
    un párrafo único, SÍ tienen un punto de corte natural, así que sí se sub-particionan."""
    first = total_tokens // 2
    second = total_tokens - first
    return f"{_n_tokens(first)}\n\n{_n_tokens(second)}"


@pytest.mark.parametrize(
    ("tokens", "expected_chunks"),
    [(9, 1), (10, 1), (11, 2)],
    ids=["budget-1", "budget", "budget+1"],
)
def test_exact_token_budget_boundary(tokens: int, expected_chunks: int) -> None:
    body = f"## Comportamiento\n\n{_two_blocks(tokens)}\n"

    result = _chunk(_parsed(body), budget=10)

    assert len(result) == expected_chunks
    assert all(c.section_type == "comportamiento" for c in result)


def test_a_table_that_exceeds_the_budget_is_not_split_mid_table() -> None:
    table = "| a | b |\n" + "\n".join(f"| {_n_tokens(1)} | {_n_tokens(1)} |" for _ in range(20))
    body = f"## Conceptos\n\n{table}\n"

    result = _chunk(_parsed(body), budget=5)

    assert len(result) == 1
    assert result[0].content.count("|") == table.count("|")


def test_a_long_plain_text_section_is_sub_split_preserving_order(
    caplog: pytest.LogCaptureFixture,
) -> None:
    paragraphs = [_n_tokens(4) for _ in range(5)]  # 5 párrafos de 4 tokens, budget=10
    body = "## Comportamiento\n\n" + "\n\n".join(paragraphs) + "\n"

    result = _chunk(_parsed(body), budget=10)

    assert len(result) > 1
    assert all(c.section_type == "comportamiento" for c in result)
    assert [c.ordinal for c in result] == list(range(len(result)))


def test_a_single_paragraph_that_alone_exceeds_the_budget_stays_as_one_oversized_chunk(
    caplog: pytest.LogCaptureFixture,
) -> None:
    body = f"## Comportamiento\n\n{_n_tokens(50)}\n"

    with caplog.at_level("WARNING"):
        result = _chunk(_parsed(body), budget=10)

    assert len(result) == 1
    assert result[0].token_count == 50
    assert "kb_chunk_excede_presupuesto" in caplog.text


def test_an_unclosed_code_fence_does_not_swallow_the_rest_of_the_document() -> None:
    body = (
        "## Comportamiento\n\n```python\ncodigo sin cerrar\nmas codigo\n\n## Fidelidad\n\nTexto.\n"
    )

    result = _chunk(_parsed(body))

    # todo el resto del documento quedó DENTRO del fence sin cerrar de "Comportamiento": no hay
    # una sección "fidelidad" propia porque "## Fidelidad" es tratado como texto de código, no H2.
    assert [c.section_type for c in result] == ["comportamiento"]
    assert "codigo sin cerrar" in result[0].content
    assert "## Fidelidad" in result[0].content


def test_a_closed_code_fence_does_not_prevent_the_next_section_from_being_chunked() -> None:
    body = "## Comportamiento\n\n```python\nx = 1\n```\n\n## Fidelidad\n\nTexto.\n"

    result = _chunk(_parsed(body))

    assert [c.section_type for c in result] == ["comportamiento", "fidelidad"]


# ── metadatos (Trazabilidad / Relacionado) ──


def test_trazabilidad_block_does_not_leak_into_chunk_content() -> None:
    body = (
        "## Comportamiento\n\nTexto.\n\n"
        "::: info Trazabilidad\n- **Estado**: active\n- **Package**: syntax-cx\n:::\n"
    )

    result = _chunk(_parsed(body))

    assert "Trazabilidad" not in result[0].content
    assert "Estado" not in result[0].content


def test_relacionado_line_does_not_leak_into_chunk_content() -> None:
    body = "## Comportamiento\n\nTexto.\n\nRelacionado: [Otro](/domains/x/uc/UC-Y)\n"

    result = _chunk(_parsed(body))

    assert "Relacionado" not in result[0].content


# ── glosario (index.md) ──


def test_glosario_document_produces_a_single_glosario_chunk() -> None:
    parsed = _parsed(
        "- **Editor** — componente de edición.",
        uc_id=f"{GLOSARIO_UC_ID_PREFIX}authoring-and-editor",
        package="",
        estado="",
    )

    result = _chunk(parsed, budget=1)  # presupuesto irrelevante: glosario nunca se sub-parte

    assert len(result) == 1
    assert result[0].section_type == "glosario"
    assert result[0].content == "- **Editor** — componente de edición."
    assert result[0].ordinal == 0


def test_glosario_document_with_empty_body_yields_no_chunks() -> None:
    parsed = _parsed(
        "", uc_id=f"{GLOSARIO_UC_ID_PREFIX}authoring-and-editor", package="", estado=""
    )

    assert _chunk(parsed) == []


# ── robustez interna de _split_into_atomic_blocks / _pack_into_budget ──


def test_chunk_is_immutable() -> None:
    result = _chunk(_parsed("## Comportamiento\n\nTexto.\n"))

    with pytest.raises(dataclasses.FrozenInstanceError):
        result[0].content = "otro"  # type: ignore[misc]


def test_a_multiline_fence_stays_together_as_one_atomic_block_even_under_budget_pressure() -> None:
    """Un fence con VARIAS líneas de contenido, junto marca de apertura/cierre — descarta un avance
    de `index` roto dentro del fence (líneas 162/166/168) o un `<`/`not` mutado en su bucle interno
    (163): cualquiera de esos rompe el conteo y el fence deja de llegar entero a un único chunk."""
    fence_lines = ["```", _n_tokens(3), _n_tokens(3), _n_tokens(3), "```"]
    fence_body = "\n".join(fence_lines)
    body = f"## Comportamiento\n\n{fence_body}\n\n{_n_tokens(2)}\n"

    result = _chunk(_parsed(body), budget=5)

    assert len(result) == 2
    assert result[0].content == fence_body
    assert result[1].content == _n_tokens(2)


def test_a_fence_immediately_following_a_paragraph_flushes_the_paragraph_first() -> None:
    """Descarta un `if current:` mutado a `if not current:` (línea 158): dejaría sin volcar el
    párrafo pendiente antes de arrancar el fence, mezclando su contenido con lo que venga después."""
    body = "## Comportamiento\n\ntexto antes\n```\ncodigo\n```\n"

    result = _chunk(_parsed(body))

    assert len(result) == 1
    assert result[0].content == "texto antes\n\n```\ncodigo\n```"


def test_content_after_a_closed_fence_within_the_same_section_is_still_chunked() -> None:
    """Descarta un `continue` mutado a `break` en el manejo de fences (línea 170): pararía el
    troceo entero de la sección en el primer fence, perdiendo cualquier texto posterior."""
    body = "## Comportamiento\n\n```python\nx = 1\n```\n\ntexto despues del fence\n"

    result = _chunk(_parsed(body))

    assert "texto despues del fence" in result[-1].content


def test_a_block_after_an_oversized_one_is_still_packed() -> None:
    """Descarta un `continue` mutado a `break` en `_pack_into_budget` (línea 198): pararía el
    empaquetado entero tras el primer bloque sobredimensionado, perdiendo los bloques siguientes."""
    body = f"## Comportamiento\n\n{_n_tokens(50)}\n\n{_n_tokens(2)}\n"

    result = _chunk(_parsed(body), budget=10)

    assert len(result) == 2
    assert result[1].token_count == 2


def test_current_tokens_resets_to_zero_after_flushing_before_an_oversized_block() -> None:
    """Descarta un reset a un valor distinto de 0 (p.ej. -1) tras volcar el acumulador justo antes
    de un bloque sobredimensionado (línea 195): un baseline por debajo de 0 haría que dos bloques que
    juntos SÍ exceden el presupuesto (4+5=9>8) parezcan caber (3+5=8), fusionándolos por error."""
    body = (
        f"## Comportamiento\n\n{_n_tokens(2)}\n\n{_n_tokens(50)}\n\n"
        f"{_n_tokens(4)}\n\n{_n_tokens(5)}\n"
    )

    result = _chunk(_parsed(body), budget=8)

    assert len(result) == 4
    assert result[2].content == _n_tokens(4)
    assert result[3].content == _n_tokens(5)


def test_current_tokens_does_not_reset_above_zero_after_flushing_before_an_oversized_block() -> (
    None
):
    """Dirección opuesta al test anterior: descarta un reset a un valor por ENCIMA de 0 (p.ej. 1),
    que haría que dos bloques que juntos NO exceden el presupuesto (4+4=8) parezcan excederlo
    (5+4=9), separándolos por error cuando deberían fusionarse."""
    body = (
        f"## Comportamiento\n\n{_n_tokens(2)}\n\n{_n_tokens(50)}\n\n"
        f"{_n_tokens(4)}\n\n{_n_tokens(4)}\n"
    )

    result = _chunk(_parsed(body), budget=8)

    assert len(result) == 3
    assert result[2].content == f"{_n_tokens(4)}\n\n{_n_tokens(4)}"


def test_current_tokens_resets_to_zero_after_a_normal_split() -> None:
    """Mismo argumento que el test anterior, para el reset de la rama de corte normal (línea 201):
    tras partir dos bloques de 6 (12>8), un tercer bloque de 3 SÍ excede junto al segundo (6+3=9>8) —
    un baseline de -1 lo dejaría en 5+3=8, fusionándolo por error."""
    body = f"## Comportamiento\n\n{_n_tokens(6)}\n\n{_n_tokens(6)}\n\n{_n_tokens(3)}\n"

    result = _chunk(_parsed(body), budget=8)

    assert len(result) == 3
    assert result[1].content == _n_tokens(6)
    assert result[2].content == _n_tokens(3)


def test_current_tokens_does_not_reset_above_zero_after_a_normal_split() -> None:
    """Dirección opuesta: tras partir dos bloques de 6, un tercer bloque de 2 NO excede junto al
    segundo (6+2=8) — un baseline de 1 lo dejaría en 7+2=9, separándolo por error."""
    body = f"## Comportamiento\n\n{_n_tokens(6)}\n\n{_n_tokens(6)}\n\n{_n_tokens(2)}\n"

    result = _chunk(_parsed(body), budget=8)

    assert len(result) == 2
    assert result[1].content == f"{_n_tokens(6)}\n\n{_n_tokens(2)}"


def test_a_block_with_exactly_the_budget_does_not_log_an_oversized_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Descarta `>` mutado a `>=` en la comprobación de bloque sobredimensionado (línea 192): un
    bloque de EXACTAMENTE el presupuesto no debe contar como "excede", solo por encima."""
    body = f"## Comportamiento\n\n{_n_tokens(10)}\n"

    with caplog.at_level("WARNING"):
        result = _chunk(_parsed(body), budget=10)

    assert len(result) == 1
    assert "kb_chunk_excede_presupuesto" not in caplog.text


def test_content_immediately_after_a_closing_fence_marker_is_not_skipped() -> None:
    """Descarta un avance de `index` de 2 en vez de 1 justo tras la marca de cierre (línea 168):
    se saltaría la línea que viene justo después del cierre, sin separador en blanco de por medio."""
    body = "## Comportamiento\n\n```\ncodigo\n```\ntexto pegado al cierre\n"

    result = _chunk(_parsed(body))

    assert "texto pegado al cierre" in result[0].content


def test_a_section_with_more_than_256_lines_terminates_correctly() -> None:
    """> 256 líneas: por encima del rango de enteros cacheados de CPython (-5..256), así que un
    mutante `<` → `is not` en la condición de parada del bucle externo (línea 155) NO puede
    coincidir por casualidad de identidad de objeto — si sobrevive, el bucle nunca termina y
    revienta con IndexError en vez de devolver una lista de chunks."""
    body = "## Comportamiento\n\n" + "\n".join(f"línea {i}" for i in range(300)) + "\n"

    result = _chunk(_parsed(body))

    assert len(result) == 1
    assert "línea 299" in result[0].content


def test_a_fence_with_more_than_256_internal_lines_terminates_correctly() -> None:
    """Mismo argumento que el test anterior, para el bucle interno del fence (líneas 163/166) en su
    camino de cierre encontrado: un fence con > 256 líneas de contenido fuerza enteros fuera del
    rango cacheado."""
    fence_lines = ["```", *[f"línea {i}" for i in range(300)], "```"]
    body = "## Comportamiento\n\n" + "\n".join(fence_lines) + "\ndespues del fence\n"

    result = _chunk(_parsed(body), budget=5000)

    assert len(result) == 1
    assert "línea 299" in result[0].content
    assert "despues del fence" in result[0].content


def test_an_unclosed_fence_with_more_than_256_lines_terminates_correctly() -> None:
    """El caso que de verdad ejercita el `index == len(lines)` del bucle interno del fence (líneas
    163/166): un fence SIN cierre y > 256 líneas — el cierre encontrado del test anterior nunca llega
    a comparar `index` contra `len(lines)` (para él para antes, al hallar la marca de cierre)."""
    fence_lines = ["```", *[f"línea {i}" for i in range(300)]]  # nunca cierra
    body = "## Comportamiento\n\n" + "\n".join(fence_lines) + "\n"

    result = _chunk(_parsed(body), budget=5000)

    assert len(result) == 1
    assert "línea 299" in result[0].content
