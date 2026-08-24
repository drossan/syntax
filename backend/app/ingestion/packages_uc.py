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
recorrido. El `parse()` de este tipo de fuente es la tarea `-02`.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import structlog

from app.ingestion.loader import RawDoc

_logger = structlog.get_logger(__name__)

_PACKAGES_DIR = "packages"
_USE_CASES_SUBPATH = ("docs", "aiup", "use-cases")
_GLOSSARIES_SUBPATH = ("docs", "aiup", "glossaries")
_UC_PREFIX = "UC-"
_MD_SUFFIX = ".md"


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
