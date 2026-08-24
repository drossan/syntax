"""app.ingestion.sources — registro de tipos de fuente de la KB (tarea backend-kb-source-packages-uc-03).

Un `source_type` es un par `(load, parse)` más el metadato de si necesita alias de package. El registro
vive **en código**, no en un mapeo declarativo genérico: sin un segundo caso real confirmado, un mapeo
de campos/estructura configurable sería diseño especulativo (ver el ADR de este plan).

Tipos registrados:

- **`packages-uc`** — el formato REAL verificado (`app.ingestion.packages_uc`). Es el **default**: un
  despliegue apuntando a la fuente real sin `KB_SOURCE_TYPE` debe correr el loader correcto, no
  terminar "con éxito" reportando 0 procesados (`design-review` #2).
- **`vitepress-domains`** — el formato hipotético, **nunca verificado** contra una fuente real
  (`app.ingestion.loader`/`app.ingestion.parser`, referenciados **sin tocarlos**).

Anti-patrón: tolerar alias de caja (`"Packages-UC"`). Solo la forma canónica exacta se reconoce — un
valor "casi bueno" que se acepta en silencio es peor que un error de uso claro.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from app.domain.errors import Validation
from app.ingestion import loader, packages_uc, parser
from app.ingestion.loader import RawDoc
from app.ingestion.parser import ParsedUC, ParseError

LoadFn = Callable[[Path], Iterator[RawDoc]]
"""Descubre y lee los `.md` de una raíz. Idéntica en todos los tipos de fuente."""

ParseFn = Callable[..., ParsedUC | ParseError]
"""Parsea un `RawDoc`.

La elipsis es **deliberada y acotada**, no un `Any` de conveniencia: las dos implementaciones tienen
firmas distintas a propósito (`packages_uc.parse` exige el parámetro extra `package_aliases`, que
`parser.parse` no tiene ni debe tener). Quien lo consume —`pipeline.ingest`— lo especializa con
`functools.partial` y lo llama siempre con la firma reducida `(raw, *, kb_root)`.
"""


@dataclass(frozen=True)
class SourceType:
    """Descriptor de un tipo de fuente: su par `(load, parse)` y qué configuración necesita."""

    load: LoadFn
    parse: ParseFn
    requires_package_aliases: bool
    """Si este tipo traduce subdirectorios de package con alias de deployment.

    Es un **metadato del tipo**, no de la CLI: sin él, avisar de "alias vacíos" (extensión 1l) exigía
    un `if source_type == "packages-uc"` hardcodeado en la CLI, o emitía un **falso positivo** con
    `vitepress-domains` (que no los usa y cuyo default de alias también es vacío). Un tercer tipo
    futuro trae el suyo sin tocar la CLI.
    """


_REGISTRY: dict[str, SourceType] = {
    "packages-uc": SourceType(
        load=packages_uc.load, parse=packages_uc.parse, requires_package_aliases=True
    ),
    "vitepress-domains": SourceType(
        load=loader.load, parse=parser.parse, requires_package_aliases=False
    ),
}


def resolve_source(source_type: str) -> SourceType:
    """Devuelve el descriptor del `source_type` pedido.

    :param source_type: la forma canónica exacta (`"packages-uc"` / `"vitepress-domains"`); **no** se
        toleran variantes de caja ni sinónimos.
    :returns: el `SourceType` registrado (el mismo objeto en cada llamada — es una tabla, no una
        factoría).
    :raises app.domain.errors.Validation: si no está registrado. Mismo tipo de error que ya usa
        `pipeline.ingest` para el `uc_id` duplicado; el mensaje lleva el valor recibido **y** la lista
        de válidos, para que al operador le baste con leerlo (extensión 1g).
    """
    source = _REGISTRY.get(source_type)
    if source is None:
        valid = ", ".join(sorted(_REGISTRY))
        raise Validation(
            f"tipo de fuente de KB no reconocido: {source_type!r} — válidos: {valid}",
            code="ingestion.unknown_source_type",
            details={"source_type": source_type, "valid": sorted(_REGISTRY)},
        )
    return source
