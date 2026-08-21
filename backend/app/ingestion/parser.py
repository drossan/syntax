"""app.ingestion.parser — frontmatter + Trazabilidad + glosario (tarea backend-kb-ingestion-03).

Frontmatter YAML (`title`/`domain`/`package`/`uc`) + bloque `::: info Trazabilidad` (`Estado`/
`Package`/`Traza`) + línea `Relacionado:`. Precedencia de `package`: gana el frontmatter, la
discrepancia con Trazabilidad solo se loguea (`structlog`), no bloquea ni cambia el resultado.

`index.md` no lleva frontmatter ni Trazabilidad: su `domain` se deriva del nombre de la carpeta padre,
y su `uc_id` es un identificador SINTÉTICO (`__glosario__:<dominio>`, nunca colisiona con un `uc_id`
real `UC-*`) — decisión de esta tarea, sin precedente en la spec (no hay fuente real en esta máquina
para verificar el formato exacto de `::: info Trazabilidad`; este parser es la interpretación
documentada de `rag-ingestion.md` §2, a confirmar cuando el owner tenga la fuente real). Solo el
bloque `## Glosario` de un `index.md` se conserva como `body` — el resto (navegación) se descarta
aquí mismo, no en el chunker (`-04`), que trata UC e `index.md` de forma uniforme.

Anti-patrón: leer `url` del frontmatter (no existe, `source_url` se deriva de la ruta); usar
`yaml.load` (sin `safe_`) — un frontmatter con un tag adversario (`!!python/object/...`) debe
rechazarse como malformado, nunca ejecutar código.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import structlog
import yaml

from app.domain.entities.enums import KbDomain, KbEstado, Package
from app.ingestion.loader import RawDoc

_logger = structlog.get_logger(__name__)

_VALID_DOMAINS = {member.value for member in KbDomain}
_VALID_PACKAGES = {member.value for member in Package}
_VALID_ESTADOS = {member.value for member in KbEstado}

_FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)
_TRAZABILIDAD_RE = re.compile(r"::: info Trazabilidad\r?\n(.*?)\r?\n:::", re.DOTALL)
_ESTADO_RE = re.compile(r"\*\*Estado\*\*:\s*(\S+)")
_PACKAGE_RE = re.compile(r"\*\*Package\*\*:\s*(\S+)")
_TRAZA_RE = re.compile(r"\*\*Traza\*\*:\s*(.+)")
_RELACIONADO_RE = re.compile(r"^Relacionado:\s*(.*)$", re.MULTILINE)
_RELACIONADO_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_GLOSARIO_RE = re.compile(r"^## Glosario\s*\r?\n(.*?)(?=^## |\Z)", re.DOTALL | re.MULTILINE)

_GLOSARIO_UC_ID_PREFIX = "__glosario__:"


@dataclass(frozen=True)
class ParsedUC:
    """Un documento parseado — un UC real, o el glosario sintético de un `index.md` de dominio."""

    uc_id: str
    domain: str
    package: str
    estado: str
    title: str
    traza: list[str]
    relacionado: list[str]
    source_url: str
    updated: datetime
    body: str


@dataclass(frozen=True)
class ParseError:
    """Un documento que no se pudo parsear — se salta con log, nunca lanza."""

    path: Path
    reason: str


def parse(raw: RawDoc, *, kb_root: Path) -> ParsedUC | ParseError:
    """Parsea `raw`. `kb_root` es la raíz de la KB (misma que se pasó a `load()`), para derivar
    `source_url` como la ruta relativa a ella."""
    if raw.path.name == "index.md":
        return _parse_index(raw, kb_root=kb_root)
    return _parse_uc(raw, kb_root=kb_root)


def _skip(path: Path, reason: str) -> ParseError:
    _logger.warning("kb_doc_malformado", path=str(path), reason=reason)
    return ParseError(path=path, reason=reason)


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


def _parse_uc(raw: RawDoc, *, kb_root: Path) -> ParsedUC | ParseError:
    frontmatter = _parse_frontmatter(raw)
    if isinstance(frontmatter, ParseError):
        return frontmatter

    uc_id = frontmatter.get("uc")
    if not uc_id or not isinstance(uc_id, str):
        return _skip(raw.path, "falta 'uc' en el frontmatter")

    domain = frontmatter.get("domain")
    if domain not in _VALID_DOMAINS:
        return _skip(raw.path, f"domain fuera de catálogo: {domain!r}")

    package = frontmatter.get("package")
    if package not in _VALID_PACKAGES:
        return _skip(raw.path, f"package fuera de catálogo: {package!r}")

    body = _FRONTMATTER_RE.sub("", raw.content, count=1)
    trazabilidad_match = _TRAZABILIDAD_RE.search(body)
    if trazabilidad_match is None:
        return _skip(raw.path, "sin bloque de Trazabilidad")
    trazabilidad = trazabilidad_match.group(1)

    estado_match = _ESTADO_RE.search(trazabilidad)
    estado = estado_match.group(1) if estado_match else None
    if estado not in _VALID_ESTADOS:
        return _skip(raw.path, f"Estado de Trazabilidad fuera de catálogo: {estado!r}")

    traza_match = _TRAZA_RE.search(trazabilidad)
    traza = _split_traza(traza_match.group(1)) if traza_match else []

    trazabilidad_package_match = _PACKAGE_RE.search(trazabilidad)
    if trazabilidad_package_match is not None:
        trazabilidad_package = trazabilidad_package_match.group(1)
        if trazabilidad_package != package:
            _logger.info(
                "kb_package_discrepancia",
                path=str(raw.path),
                frontmatter_package=package,
                trazabilidad_package=trazabilidad_package,
            )

    relacionado_match = _RELACIONADO_RE.search(body)
    relacionado = (
        _RELACIONADO_LINK_RE.findall(relacionado_match.group(1)) if relacionado_match else []
    )

    return ParsedUC(
        uc_id=uc_id,
        domain=domain,
        package=package,
        estado=estado,
        title=str(frontmatter.get("title", "")),
        traza=traza,
        relacionado=relacionado,
        source_url=str(raw.path.relative_to(kb_root)),
        updated=raw.mtime,
        body=body,
    )


def _parse_index(raw: RawDoc, *, kb_root: Path) -> ParsedUC | ParseError:
    domain = raw.path.parent.name
    if domain not in _VALID_DOMAINS:
        return _skip(raw.path, f"domain fuera de catálogo: {domain!r}")

    glosario_match = _GLOSARIO_RE.search(raw.content)
    body = glosario_match.group(1).strip() if glosario_match else ""

    return ParsedUC(
        uc_id=f"{_GLOSARIO_UC_ID_PREFIX}{domain}",
        domain=domain,
        package="",
        estado="",
        title=f"Glosario — {domain}",
        traza=[],
        relacionado=[],
        source_url=str(raw.path.relative_to(kb_root)),
        updated=raw.mtime,
        body=body,
    )


def _split_traza(raw_value: str) -> list[str]:
    return [item.strip(" `") for item in raw_value.split(",") if item.strip(" `")]
