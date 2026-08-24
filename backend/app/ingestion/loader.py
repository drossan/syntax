"""app.ingestion.loader — descubre y lee los .md de la KB (tarea backend-kb-ingestion-03).

Recorre `<path>/<dominio>/uc/UC-*.md` + `<path>/<dominio>/index.md`; el `<path>/index.md` RAÍZ nunca
se visita — no por un filtro explícito, sino porque solo se itera sobre SUBDIRECTORIOS de `path` (el
`index.md` raíz es un fichero, no un directorio). Streaming por fichero (generador), nunca carga toda
la KB en memoria. Un fichero illegible (permisos) o con encoding no-UTF8 se salta con log — nunca
aborta el recorrido completo (decisión de `scenario-coverage`).
"""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import structlog

_logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class RawDoc:
    """Un `.md` crudo, sin parsear — ruta absoluta + contenido tal cual en disco + `mtime` (capturado
    aquí, no en el parser, para que este último no toque el filesystem — puro, testeable in-memory)."""

    path: Path
    content: str
    mtime: datetime


def load(path: Path) -> Iterator[RawDoc]:
    """Descubre y lee los `.md` de la KB bajo `path` (la raíz `domains/`, no un nivel por encima).

    Valida `path` de forma EAGER (antes de devolver el iterador): un generador puro no lanzaría hasta
    la primera iteración, y "falla claro" exige que el error de uso llegue en la propia llamada.

    :raises FileNotFoundError: si `path` no existe o no es un directorio.
    """
    if not path.is_dir():
        raise FileNotFoundError(f"la raíz de la KB no existe o no es un directorio: {path}")
    return _load_existing(path)


def _load_existing(path: Path) -> Iterator[RawDoc]:
    for domain_dir in sorted(p for p in path.iterdir() if p.is_dir()):
        index_doc = _read(domain_dir / "index.md")
        if index_doc is not None:
            yield index_doc
        uc_dir = domain_dir / "uc"
        if not uc_dir.is_dir():
            continue
        for uc_path in sorted(uc_dir.glob("UC-*.md")):
            uc_doc = _read(uc_path)
            if uc_doc is not None:
                yield uc_doc


def _read(path: Path) -> RawDoc | None:
    if not path.is_file():
        return None
    try:
        content = path.read_text(encoding="utf-8")
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    except (OSError, UnicodeDecodeError) as exc:
        _logger.warning("kb_doc_illegible", path=str(path), reason=str(exc))
        return None
    return RawDoc(path=path, content=content, mtime=mtime)
