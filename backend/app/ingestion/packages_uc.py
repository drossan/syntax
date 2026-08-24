"""app.ingestion.packages_uc — loader del `source_type` **`packages-uc`** (formato REAL verificado).

Este módulo implementa el descubrimiento de ficheros de una fuente de KB con este layout:

    <root>/packages/<pkg>/docs/aiup/use-cases/UC-*.md   → los casos de uso
    <root>/docs/aiup/glossaries/<dominio>.md            → un glosario plano por dominio

Los nombres de carpeta (`packages`/`docs`/`aiup`/`use-cases`/`glossaries`) son la **convención fija de
este `source_type`**, igual que `vitepress-domains` fija `<dominio>/uc/UC-*.md` — describen la forma
estructural que este tipo reconoce, no la marca de ningún cliente. Un árbol hermano con otra
convención (p. ej. una generación legacy de los mismos UC) **nunca** se recoge: solo se visitan las
rutas de arriba (CU-BE-07, extensión 1k).

Dos anti-patrones que este módulo evita a propósito:

1. **Asumir el layout `<dominio>/uc/`** de `app.ingestion.loader` (el formato hipotético
   `vitepress-domains`, nunca verificado contra una fuente real). Son dos recorridos distintos; este
   deriva el `package` del subdirectorio, aquel lo lee del frontmatter.
2. **Importar la privada `_read` de `loader.py`**. Los dos tipos de fuente son implementaciones
   independientes que comparten **solo el contrato de datos** (`RawDoc`, reutilizado aquí **sin
   modificar**), no sus detalles internos: acoplarlos por una privada haría que un cambio en el
   loader del formato hipotético rompiese el del formato real.

Streaming por fichero (generador): nunca carga la KB entera en memoria. Un fichero illegible o con
encoding no-UTF8, y un **directorio** sin permisos de lectura, se saltan con log — nunca abortan el
recorrido.

`parse()` completa el par `(load, parse)` del tipo de fuente. Frontmatter real
(`id`/`dominio`/`estado`/`traza`), título desde el **primer H1 del cuerpo** (este formato no trae
`title`) y `package` derivado del subdirectorio, traducido por los **alias inyectados**. Reutiliza sin
modificar `ParsedUC`/`ParseError`/`GLOSARIO_UC_ID_PREFIX` de `parser.py`. Tres anti-patrones más que
evita a propósito:

3. **`yaml.load` sin `safe_`**: un frontmatter con un tag adversario (`!!python/object/apply:...`) debe
   rechazarse como malformado, **jamás** ejecutar código.
4. **Importar los privados de `parser.py`** (`_VALID_DOMAINS`/`_VALID_ESTADOS`/`_FRONTMATTER_RE`): se
   derivan de nuevo aquí desde los enums, por el mismo motivo que `_read` (ver punto 2).
5. **Replicar el log `kb_package_discrepancia`**: en este formato **no puede darse** (RN-4 de
   `CU-BE-07`) — el `package` tiene una sola fuente, la ruta, así que no hay nada que comparar.
"""

import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import structlog
import yaml

from app.domain.entities.enums import KbDomain, KbEstado, Package
from app.ingestion.loader import RawDoc
from app.ingestion.parser import GLOSARIO_UC_ID_PREFIX, ParsedUC, ParseError

_logger = structlog.get_logger(__name__)

_PACKAGES_DIR = "packages"
_USE_CASES_SUBPATH = ("docs", "aiup", "use-cases")
_GLOSSARIES_SUBPATH = ("docs", "aiup", "glossaries")
_GLOSSARIES_DIR = _GLOSSARIES_SUBPATH[-1]
_UC_PREFIX = "UC-"
_MD_SUFFIX = ".md"

_VALID_DOMAINS = {member.value for member in KbDomain}
_VALID_ESTADOS = {member.value for member in KbEstado}
_VALID_PACKAGES = {member.value for member in Package}

_FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)
_H1_RE = re.compile(r"^#\s+(.+?)\s*$")
_FENCE_MARKER_RE = re.compile(r"^\s*```")


def load(root: Path) -> Iterator[RawDoc]:
    """Descubre y lee los `.md` de una KB con el layout `packages-uc` bajo `root`.

    Orden **documentado y estable** (de él dependen el `ordinal` de los chunks y la reproducibilidad
    del batch): primero **todos** los UC —alfabético por subdirectorio de package y, dentro de cada
    uno, por nombre de fichero—, después los glosarios (alfabético).

    Valida `root` de forma EAGER (antes de devolver el iterador, mismo criterio que `loader.load`):
    un generador puro no lanzaría hasta la primera iteración, y "falla claro" exige que el error de
    uso llegue en la propia llamada.

    :param root: raíz del árbol de la fuente (la que contiene `packages/` y `docs/`).
    :returns: iterador perezoso de `RawDoc` (ruta + contenido + `mtime`).
    :raises FileNotFoundError: si `root` no existe o no es un directorio.
    """
    if not root.is_dir():
        raise FileNotFoundError(f"la raíz de la KB no existe o no es un directorio: {root}")
    return _load_existing(root)


def _load_existing(root: Path) -> Iterator[RawDoc]:
    yield from _load_use_cases(root)
    yield from _load_glossaries(root)


def _load_use_cases(root: Path) -> Iterator[RawDoc]:
    for package_dir in _list_dir(root / _PACKAGES_DIR):
        for entry in _list_dir(package_dir.joinpath(*_USE_CASES_SUBPATH)):
            if not _is_use_case(entry):
                continue
            doc = _read(entry)
            if doc is not None:
                yield doc


def _load_glossaries(root: Path) -> Iterator[RawDoc]:
    for entry in _list_dir(root.joinpath(*_GLOSSARIES_SUBPATH)):
        if not _is_markdown_file(entry):
            continue
        doc = _read(entry)
        if doc is not None:
            yield doc


def _list_dir(directory: Path) -> list[Path]:
    """Entradas de `directory` ordenadas, o `[]` si no se puede listar.

    Un directorio **ausente** (o un componente de la ruta que no es directorio) no es un error: la
    fuente real tiene packages sin casos de uso, y puede no tener glosarios. Un directorio **sin
    permisos de lectura** sí se loguea: es un problema del origen, pero el recorrido continúa con el
    resto (decisión de esta tarea; `loader.py` no cubre este caso).
    """
    try:
        return sorted(directory.iterdir())
    except (FileNotFoundError, NotADirectoryError):
        return []
    except OSError as exc:
        _logger.warning("kb_dir_illegible", path=str(directory), reason=str(exc))
        return []


def _is_use_case(entry: Path) -> bool:
    """Un UC es un **fichero** cuyo nombre empieza por `UC-` y acaba en `.md`, **respetando la caja**.

    La comprobación es explícita (no un glob) por dos motivos: `Path.glob` no distingue un directorio
    llamado `UC-algo.md` de un fichero, y la comparación de caja no debe depender de si el sistema de
    ficheros es case-insensitive.
    """
    return entry.name.startswith(_UC_PREFIX) and _is_markdown_file(entry)


def _is_markdown_file(entry: Path) -> bool:
    return entry.suffix == _MD_SUFFIX and entry.is_file()


def _read(path: Path) -> RawDoc | None:
    try:
        content = path.read_text(encoding="utf-8")
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    except (OSError, UnicodeDecodeError) as exc:
        _logger.warning("kb_doc_illegible", path=str(path), reason=str(exc))
        return None
    return RawDoc(path=path, content=content, mtime=mtime)


def parse(raw: RawDoc, *, kb_root: Path, package_aliases: dict[str, str]) -> ParsedUC | ParseError:
    """Parsea un `RawDoc` del formato `packages-uc`.

    Un documento mal formado **nunca lanza**: devuelve `ParseError` y se loguea (`kb_doc_malformado`),
    para que un fichero roto no aborte el batch entero.

    :param raw: el documento crudo que produjo `load()`.
    :param kb_root: la raíz que se pasó a `load()` — de ella se deriva `source_url` (ruta relativa).
    :param package_aliases: traducción `subdirectorio de package` → valor de `Package`. Es
        **configuración de deployment** (RN-5), se inyecta: este módulo no importa `app.core.config`.
        Vacío (el default) → ningún UC supera la validación de `package`; es el comportamiento
        esperado, no un fallo (extensión 1l; el aviso al operador vive en la CLI).
    :returns: el `ParsedUC`, o un `ParseError` con la ruta y el motivo.
    """
    try:
        relative_path = raw.path.relative_to(kb_root)
    except ValueError:
        return _skip(raw.path, f"la ruta no cuelga de la raíz de la KB: {kb_root}")
    if raw.path.parent.name == _GLOSSARIES_DIR:
        return _parse_glossary(raw, relative_path=relative_path)
    return _parse_uc(raw, relative_path=relative_path, package_aliases=package_aliases)


def _skip(path: Path, reason: str) -> ParseError:
    _logger.warning("kb_doc_malformado", path=str(path), reason=reason)
    return ParseError(path=path, reason=reason)


def _parse_uc(
    raw: RawDoc, *, relative_path: Path, package_aliases: dict[str, str]
) -> ParsedUC | ParseError:
    frontmatter = _parse_frontmatter(raw)
    if isinstance(frontmatter, ParseError):
        return frontmatter

    uc_id = frontmatter.get("id")
    if not uc_id or not isinstance(uc_id, str):
        return _skip(raw.path, f"'id' ausente, vacío o no textual: {uc_id!r}")

    domain = frontmatter.get("dominio")
    if domain not in _VALID_DOMAINS:
        return _skip(raw.path, f"dominio fuera de catálogo: {domain!r}")

    estado = frontmatter.get("estado")
    if estado not in _VALID_ESTADOS:
        return _skip(raw.path, f"estado fuera de catálogo: {estado!r}")

    package = _resolve_package(relative_path, package_aliases)
    if package is None:
        return _skip(raw.path, f"sin alias de package válido para la ruta: {relative_path}")

    body = _FRONTMATTER_RE.sub("", raw.content, count=1)
    title = _first_h1(body)
    if title is None:
        return _skip(raw.path, "sin encabezado H1 del que derivar el título")

    return ParsedUC(
        uc_id=uc_id,
        domain=str(domain),
        package=package,
        estado=str(estado),
        title=title,
        traza=_normalise_traza(frontmatter.get("traza")),
        relacionado=[],
        source_url=str(relative_path),
        updated=raw.mtime,
        body=body,
    )


def _parse_glossary(raw: RawDoc, *, relative_path: Path) -> ParsedUC | ParseError:
    """Un glosario de este formato es un fichero **plano**: sin frontmatter y sin sección
    `## Glosario` que recortar (extensión 2a) — se ingiere íntegro, incluso vacío."""
    domain = raw.path.stem
    if domain not in _VALID_DOMAINS:
        return _skip(raw.path, f"dominio fuera de catálogo: {domain!r}")

    return ParsedUC(
        uc_id=f"{GLOSARIO_UC_ID_PREFIX}{domain}",
        domain=domain,
        package="",
        estado="",
        title=_first_h1(raw.content) or f"Glosario — {domain}",
        traza=[],
        relacionado=[],
        source_url=str(relative_path),
        updated=raw.mtime,
        body=raw.content,
    )


def _parse_frontmatter(raw: RawDoc) -> dict[str, object] | ParseError:
    match = _FRONTMATTER_RE.match(raw.content)
    if match is None:
        return _skip(raw.path, "sin bloque frontmatter")
    try:
        frontmatter = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        return _skip(raw.path, f"YAML de frontmatter inválido: {exc}")
    if not isinstance(frontmatter, dict):
        return _skip(raw.path, "frontmatter no es un mapeo YAML")
    return frontmatter


def _resolve_package(relative_path: Path, package_aliases: dict[str, str]) -> str | None:
    """El `package` sale del segmento `packages/<pkg>/` de la ruta, traducido por los alias.

    Devuelve `None` —nunca lanza— en los tres casos que la spec trata como malformado: la ruta no
    tiene el segmento, el `<pkg>` no tiene alias configurado, o su alias no es un miembro de `Package`.
    """
    parts = relative_path.parts
    if _PACKAGES_DIR not in parts:
        return None
    package_index = parts.index(_PACKAGES_DIR) + 1
    if package_index >= len(parts):
        return None
    package = package_aliases.get(parts[package_index])
    if package not in _VALID_PACKAGES:
        return None
    return package


def _first_h1(body: str) -> str | None:
    """El primer H1 **fuera** de un bloque de código.

    Un regex multilínea a secas matchearía una línea `# comentario` dentro de un fence (probable en
    UC reales: ejemplos de shell, `mermaid`). Mismo criterio de fences que `chunker._split_sections`:
    un fence abre/cierra el estado y, sin cerrar, se traga el resto del documento.
    """
    in_fence = False
    for line in body.split("\n"):
        if _FENCE_MARKER_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        h1_match = _H1_RE.match(line)
        if h1_match is not None:
            return h1_match.group(1)
    return None


def _normalise_traza(value: object) -> list[str]:
    """`traza` nunca invalida un documento (extensión 1j): lista tal cual, valor suelto envuelto en
    lista de un elemento, ausente/vacía → lista vacía.

    Los elementos **no textuales** se convierten a su representación textual — decisión declarada
    **sin precedente en la spec** (`scenario-coverage`): `traza` es metadato opcional sin consumidor
    hoy, y coercionar nunca pierde información ni aborta; ninguno de los UC reales verificados lo
    presenta (es defensivo).
    """
    if value is None:
        return []
    if isinstance(value, list):
        return [item if isinstance(item, str) else str(item) for item in value]
    return [value if isinstance(value, str) else str(value)]
