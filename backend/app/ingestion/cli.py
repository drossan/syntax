"""app.ingestion.cli — interfaz de línea de comandos de la ingestión (tarea backend-kb-ingestion-07).

`main(argv) -> int`: parsea argumentos, resuelve la ruta de la KB (posicional o
`settings.kb_source_path`), construye los puertos reales (`get_embedding_model`, `-01`;
`SqlAlchemyKBIndexWriter`, `-02`) e invoca `pipeline.ingest(...)` (`-06`/`-07`). Sin lógica de negocio
propia — toda vive en `pipeline`.

Códigos de salida: `0` éxito; `1` fallo de negocio (`app.domain.errors.DomainError`: `uc_id`
duplicado, lock ocupado, fallo real del embedder/writer, fallo al construir los puertos) o cualquier
excepción inesperada (nunca se deja escapar una traza cruda al operador); `2` error de uso (ruta
ausente sin `settings.kb_source_path`, ruta inexistente, **`source_type` no registrado** (extensión
1g), **JSON de alias de package inválido** (extensión 1m), flags no reconocidas — esto último vía
`argparse`, que ya sale con `2`, capturado aquí para que `main()` siempre DEVUELVA un int en vez de
lanzar `SystemExit`).

Los dos errores de uso nuevos se resuelven **antes** de entrar en `_run()`: el `Validation` de
`resolve_source` es un `DomainError`, que este módulo mapea a `1` — si escapara desde dentro saldría
con el código equivocado. Validarlos arriba también garantiza que un typo de configuración no llegue
a abrir engine ni sesión.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings, get_settings
from app.domain.errors import DomainError, Validation
from app.infra.llm.openai_adapter import get_embedding_model
from app.infra.vector import SqlAlchemyKBIndexWriter
from app.ingestion.chunker import get_encoding
from app.ingestion.pipeline import IngestReport, ingest
from app.ingestion.sources import resolve_source


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada de `python -m app.ingestion` / `make ingest`."""
    try:
        args = _build_parser().parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2

    settings = get_settings()
    raw_path = args.path or settings.kb_source_path
    if not raw_path:
        print(
            "error: falta la ruta de la KB (ni argumento ni settings.kb_source_path)",
            file=sys.stderr,
        )
        return 2
    path = Path(raw_path)
    if not path.is_dir():
        print(f"error: la ruta de la KB no existe o no es un directorio: {path}", file=sys.stderr)
        return 2

    source_type = args.source_type or settings.kb_source_type
    try:
        source = resolve_source(source_type)
    except Validation as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        package_aliases = _parse_package_aliases(settings.kb_package_aliases)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if source.requires_package_aliases and not package_aliases:
        print(
            f"aviso: el tipo de fuente {source_type!r} traduce los subdirectorios de package con "
            "alias, y no hay ninguno configurado (KB_PACKAGE_ALIASES vacío): todos los casos de uso "
            "se saltarán. Un informe con 0 procesados NO significa que el origen esté vacío.",
            file=sys.stderr,
        )

    try:
        return asyncio.run(
            _run(path, args, settings, source_type=source_type, package_aliases=package_aliases)
        )
    except DomainError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 — última red: nunca traza cruda al operador
        print(f"error inesperado: {exc}", file=sys.stderr)
        return 1


def _parse_package_aliases(raw: str) -> dict[str, str]:
    """Parsea el JSON crudo de `settings.kb_package_aliases` (extensión 1m).

    Vive aquí, y no en `Settings`, a propósito: pydantic-settings validaría un `dict[str, str]` de
    forma **eager** al construir `Settings()`, y un typo en esa env var tumbaría el arranque de toda
    la app en vez de fallar acotado a `make ingest`.

    :raises ValueError: si el JSON es inválido o no es un objeto de cadena→cadena.
    """
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"los alias de package no son un JSON válido: {exc}") from exc
    # Las claves de un objeto JSON son siempre cadenas, así que solo hay que validar los valores.
    if not isinstance(parsed, dict) or not all(isinstance(value, str) for value in parsed.values()):
        raise ValueError(
            "los alias de package deben ser un objeto JSON de cadena→cadena, "
            'p. ej. {"vendor-render": "syntax-render"}'
        )
    return parsed


async def _run(
    path: Path,
    args: argparse.Namespace,
    settings: Settings,
    *,
    source_type: str,
    package_aliases: dict[str, str],
) -> int:
    model = get_embedding_model(settings)
    engine = create_async_engine(settings.database_url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            report = await ingest(
                path,
                writer=SqlAlchemyKBIndexWriter(session),
                model=model,
                token_budget=settings.chunk_token_budget,
                encoding=get_encoding(settings.embedding_model),
                batch_size=settings.embedding_batch_size,
                embedding_model_name=settings.embedding_model,
                source_type=source_type,
                package_aliases=package_aliases,
                only_domain=args.only,
                dry_run=args.dry_run,
                force_reconcile=args.reconcile,
            )
            if not args.dry_run:
                await session.commit()
    finally:
        await engine.dispose()
    print(_format_report(report, dry_run=args.dry_run))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.ingestion", description="Ingesta la KB (Markdown) en pgvector."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Ruta raíz de la KB. Por defecto, settings.kb_source_path.",
    )
    parser.add_argument(
        "--source-type",
        metavar="TIPO",
        default=None,
        help=(
            "Tipo de fuente: packages-uc (default) o vitepress-domains. "
            "Por defecto, settings.kb_source_type."
        ),
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Simula sin escribir en BD ni llamar al embedder."
    )
    parser.add_argument("--only", metavar="DOMINIO", default=None, help="Filtra a un solo dominio.")
    parser.add_argument(
        "--reconcile",
        action="store_true",
        help="Fuerza la reconciliación aunque el origen esté vacío o todo malformado.",
    )
    return parser


def _format_report(report: IngestReport, *, dry_run: bool) -> str:
    prefix = "[dry-run] " if dry_run else ""
    return (
        f"{prefix}procesados={report.processed} creados={report.created} "
        f"actualizados={report.updated} saltados={report.skipped} "
        f"reconciliados={report.deleted}"
    )
