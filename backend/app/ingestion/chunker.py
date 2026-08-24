"""app.ingestion.chunker — troceo por sección H2 tolerante (tarea backend-kb-ingestion-04).

Parte `ParsedUC.body` (`-03`) por sus encabezados **H2**, sin asumir estructura fija: H2 ausentes se
toleran (no fallan, no se rellenan); H2 renombrados/con variantes conocidas se normalizan a un
`section_type` base (`_KNOWN_PREFIXES`); H2 sueltos (desconocidos) conservan su propio slug. Contenido
antes del primer H2 → `section_type="intro"`.

Antes de trocear, se descartan el bloque `::: info Trazabilidad` y la línea `Relacionado:` que
`-03` deja inline en `body` (son metadatos, no contenido a embeber) — decisión de esta tarea, sin
precedente explícito en la spec; no toca el contrato de `-03` (`ParsedUC.body` sigue conteniéndolos,
solo el chunker los filtra antes de partir).

Una sección que excede `token_budget` (contado con `tiktoken`, encoding de `embedding_model`) se
sub-parte por bloques atómicos (párrafos/listas separados por línea en blanco); un bloque de código
(``` ... ```) o una tabla markdown (sin líneas en blanco internas, por convención) nunca se parte a
mitad — se tratan como un único bloque atómico, incluso si por sí solos exceden el presupuesto (con
log de aviso). Un fence sin cierre se trata como cerrado al final del documento.

Un `index.md` (glosario, `-03`: `uc_id` con el prefijo `GLOSARIO_UC_ID_PREFIX`) no se secciona por H2:
produce un único chunk `section_type="glosario"` con el `body` completo (ya recortado por `-03`), o
`[]` si `body` está vacío (glosario ausente).

Anti-patrón: asumir las 5 secciones fijas; cortar una tabla o un bloque de código a mitad.
"""

import re
from dataclasses import dataclass

import structlog
import tiktoken

from app.ingestion.parser import GLOSARIO_UC_ID_PREFIX, ParsedUC

_logger = structlog.get_logger(__name__)

_H2_RE = re.compile(r"^## (.+)$", re.MULTILINE)
_TRAZABILIDAD_RE = re.compile(r"::: info Trazabilidad\r?\n.*?\r?\n:::\r?\n?", re.DOTALL)
_RELACIONADO_RE = re.compile(r"^Relacionado:.*$\r?\n?", re.MULTILINE)
_FENCE_MARKER_RE = re.compile(r"^\s*```")
_NON_SLUG_RE = re.compile(r"[^a-z0-9]+")

_KNOWN_PREFIXES = {
    "reglas-e-invariantes": "reglas",
    "detalles-observados-en-qa": "detalles-qa",
}
"""H2 renombrados/con variantes que SÍ colapsan a una sección base (`rag-ingestion.md` §3) — el resto
de H2 desconocidos (`Matriz (resumen observable)`, etc.) conservan su propio slug."""


@dataclass(frozen=True)
class Chunk:
    """Un trozo de un documento, con las 5 facetas de categorización (`rag-ingestion.md` §4) ya
    heredadas del `ParsedUC` de origen."""

    content: str
    section_type: str
    token_count: int
    ordinal: int
    uc_id: str
    domain: str
    package: str
    estado: str


def get_encoding(embedding_model: str) -> tiktoken.Encoding:
    """El encoding de `tiktoken` para `embedding_model` (p.ej. `settings.embedding_model`)."""
    return tiktoken.encoding_for_model(embedding_model)


def chunk(parsed: ParsedUC, *, token_budget: int, encoding: tiktoken.Encoding) -> list[Chunk]:
    """Trocea `parsed` en `Chunk`s. `token_budget`/`encoding` los resuelve el llamante (el pipeline,
    desde `Settings`) — este módulo no depende de `app.core.config`."""
    if parsed.uc_id.startswith(GLOSARIO_UC_ID_PREFIX):
        return _chunk_glosario(parsed, encoding=encoding)

    body = _strip_metadata_blocks(parsed.body)
    chunks: list[Chunk] = []
    ordinal = 0
    for section_type, content in _split_sections(body):
        for text in _pack_into_budget(_split_into_atomic_blocks(content), token_budget, encoding):
            chunks.append(_make_chunk(parsed, text, section_type, ordinal, encoding))
            ordinal += 1
    return chunks


def _chunk_glosario(parsed: ParsedUC, *, encoding: tiktoken.Encoding) -> list[Chunk]:
    if not parsed.body.strip():
        return []
    return [_make_chunk(parsed, parsed.body, "glosario", 0, encoding)]


def _make_chunk(
    parsed: ParsedUC, text: str, section_type: str, ordinal: int, encoding: tiktoken.Encoding
) -> Chunk:
    return Chunk(
        content=text,
        section_type=section_type,
        token_count=len(encoding.encode(text)),
        ordinal=ordinal,
        uc_id=parsed.uc_id,
        domain=parsed.domain,
        package=parsed.package,
        estado=parsed.estado,
    )


def _strip_metadata_blocks(body: str) -> str:
    body = _TRAZABILIDAD_RE.sub("", body)
    return _RELACIONADO_RE.sub("", body)


def _slugify(title: str) -> str:
    slug = _NON_SLUG_RE.sub("-", title.strip().lower()).strip("-")
    for prefix, base in _KNOWN_PREFIXES.items():
        if slug.startswith(prefix):
            return base
    return slug


def _split_sections(body: str) -> list[tuple[str, str]]:
    """Secciones por H2, ignorando cualquier `## ` que caiga DENTRO de un fence de código sin cerrar
    (o cerrado): un fence abre/cierra el estado, y mientras está abierto ningún `## ` cuenta como
    límite de sección — así "traga" el resto del documento si nunca cierra."""
    sections: list[tuple[str, str]] = []
    current_type = "intro"
    current_lines: list[str] = []
    in_fence = False
    for line in body.split("\n"):
        h2_match = None if in_fence else _H2_RE.match(line)
        if h2_match is not None:
            _flush_section(sections, current_type, current_lines)
            current_type = _slugify(h2_match.group(1))
            current_lines = []
            continue
        if _FENCE_MARKER_RE.match(line):
            in_fence = not in_fence
        current_lines.append(line)
    _flush_section(sections, current_type, current_lines)
    return sections


def _flush_section(sections: list[tuple[str, str]], section_type: str, lines: list[str]) -> None:
    content = "\n".join(lines).strip()
    if content:
        sections.append((section_type, content))


def _split_into_atomic_blocks(text: str) -> list[str]:
    """Bloques separados por línea en blanco, salvo un fence de código (``` ... ```), que se
    conserva ENTERO como un solo bloque (tolera blancos internos y un cierre ausente)."""
    lines = text.split("\n")
    blocks: list[str] = []
    current: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if _FENCE_MARKER_RE.match(line):
            if current:
                blocks.append("\n".join(current))
                current = []
            fence = [line]
            index += 1
            while index < len(lines) and not _FENCE_MARKER_RE.match(lines[index]):
                fence.append(lines[index])
                index += 1
            if index < len(lines):
                fence.append(lines[index])
                index += 1
            blocks.append("\n".join(fence))
            continue
        if line.strip() == "":
            if current:
                blocks.append("\n".join(current))
                current = []
            index += 1
            continue
        current.append(line)
        index += 1
    if current:
        blocks.append("\n".join(current))
    return blocks


def _pack_into_budget(blocks: list[str], budget: int, encoding: tiktoken.Encoding) -> list[str]:
    """Empaqueta bloques atómicos en sub-chunks bajo `budget`. Un bloque que por sí solo excede el
    presupuesto queda como su propio chunk sobredimensionado (log de aviso), nunca se parte a mitad."""
    packed: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for block in blocks:
        block_tokens = len(encoding.encode(block))
        if block_tokens > budget:
            if current:
                packed.append("\n\n".join(current))
                current, current_tokens = [], 0
            _logger.warning("kb_chunk_excede_presupuesto", tokens=block_tokens, budget=budget)
            packed.append(block)
            continue
        if current and current_tokens + block_tokens > budget:
            packed.append("\n\n".join(current))
            current, current_tokens = [], 0
        current.append(block)
        current_tokens += block_tokens
    if current:
        packed.append("\n\n".join(current))
    return packed
