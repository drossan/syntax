"""app.ingestion.pipeline — orquesta loader→parser→chunker→diff→embed→upsert→reconciliación
(tarea backend-kb-ingestion-06; `only_domain`/`dry_run`/`force_reconcile` añadidos en `-07` para la
CLI — extensión aditiva, todos con default que preserva el comportamiento original de `-06`).

Toda la lógica de negocio de CU-BE-07 vive aquí; los módulos anteriores (`loader`/`parser`/`chunker`/
`embedder`) son piezas puras/de infraestructura sin esta orquestación. `ingest()` no importa
`app.core.config`: `token_budget`/`encoding`/`batch_size`/`embedding_model_name` los resuelve el
llamante (la CLI, `-07`, desde `Settings`) — mismo criterio que el resto del paquete `app.ingestion`.

**Todo-o-nada** (decisión de `grilling`/`design-review`, plan `kb-ingestion`): el diff (¿qué chunks re-
embeber?) y el embed ocurren ENTERAMENTE en memoria, ANTES de escribir nada — así un fallo del embedder
a mitad de un batch de varios documentos no deja escritura parcial. Un fallo del `writer` a mitad de la
fase de escritura se propaga tal cual: la atomicidad de esa fase depende de que el `writer` que se pasa
aquí comparta una única sesión/transacción sin `commit()` intermedio, gestionada por el llamante (que
hace `rollback()` si `ingest()` lanza) — este módulo no conoce ni abre transacciones.

**Glosario (`index.md`)**: `KBDocumentDraft` exige `package`/`estado` no nulos, pero un glosario no
tiene ninguno de verdad (`ParsedUC.package`/`estado` llegan como `""` desde `-03`). Decisión de esta
tarea, sin precedente en la spec: se persiste con `estado=KbEstado.active` (contenido de referencia,
nunca señal "draft") y `package=Package.syntax_core` (placeholder neutro — el filtrado por `package` no
tiene consumidor todavía, tarea 14). A revisar si el retriever necesita semántica real de `package` para
glosarios.

Anti-patrón: escribir aunque sea un solo documento antes de validar `uc_id` duplicados del batch entero;
re-embeber un chunk cuyo contenido no cambió.
"""

import functools
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import structlog
import tiktoken

from app.domain.entities.enums import KbDomain, KbEstado, Package
from app.domain.errors import Conflict, Validation
from app.domain.ports.embeddings import EmbeddingModel
from app.domain.ports.vector import ChunkWrite, KBDocumentDraft, KBIndexWriter
from app.ingestion.chunker import Chunk, chunk
from app.ingestion.embedder import embed
from app.ingestion.parser import GLOSARIO_UC_ID_PREFIX, ParsedUC, ParseError
from app.ingestion.sources import ParseFn, resolve_source

_logger = structlog.get_logger(__name__)

_GLOSARIO_ESTADO = KbEstado.active
_GLOSARIO_PACKAGE = Package.syntax_core


@dataclass(frozen=True)
class IngestReport:
    """Resultado de una ejecución de `ingest()`."""

    processed: int
    """Documentos válidos procesados (creados + actualizados)."""
    created: int
    updated: int
    skipped: int
    """Documentos malformados, saltados (no cuentan como procesados)."""
    deleted: int
    """Documentos reconciliados (retirados del origen)."""


async def ingest(
    path: Path,
    *,
    writer: KBIndexWriter,
    model: EmbeddingModel,
    token_budget: int,
    encoding: tiktoken.Encoding,
    batch_size: int,
    embedding_model_name: str,
    source_type: str = "packages-uc",
    package_aliases: dict[str, str] | None = None,
    only_domain: str | None = None,
    dry_run: bool = False,
    force_reconcile: bool = False,
) -> IngestReport:
    """Ejecuta una ingestión completa de la KB bajo `path`.

    `source_type` selecciona el par `(load, parse)` en `app.ingestion.sources`; su default es el
    **formato real verificado** (`design-review` #2). `package_aliases` es la traducción
    `subdirectorio de package` → `Package` que necesitan los tipos que lo declaran: se **inyecta** aquí
    (igual que `token_budget`/`encoding`/`batch_size`) porque este módulo **no importa
    `app.core.config`**; a los tipos que no lo declaran ni se les pasa. `None` ≡ sin alias (no un
    `{}` mutable por defecto, que ruff prohíbe con razón).

    `only_domain` filtra el batch a un solo dominio (los demás ni se cuentan como procesados ni como
    saltados — simplemente no entran). `dry_run` computa el diff/reconciliación real pero NUNCA llama
    a `embed()`/`writer.upsert_document`/`writer.delete_by_uc_ids` — el `IngestReport` refleja lo que
    SE HARÍA. `force_reconcile` anula la salida rápida "origen vacío → no toca la BD" (`CU-BE-07` 4b):
    con un origen vacío/todo-malformado, sin este flag no se reconcilia nada (comportamiento seguro
    por defecto); con él, se reconcilian (borran) TODOS los documentos existentes.

    :raises app.domain.errors.Conflict: si ya hay una ingestión en curso (advisory lock ocupado).
    :raises app.domain.errors.Validation: si el `source_type` no está registrado, o si dos o más
        ficheros declaran el mismo `uc_id` — en ese caso se reportan TODOS los ficheros en conflicto,
        para cada `uc_id` duplicado.
    :raises app.domain.errors.PortError: si el embedder o el `writer` fallan; no queda ningún efecto
        parcial siempre que el llamante no haga `commit()` hasta que `ingest()` retorne con éxito.
    """
    source = resolve_source(source_type)
    parse_fn: ParseFn = source.parse
    if source.requires_package_aliases:
        parse_fn = functools.partial(source.parse, package_aliases=package_aliases or {})

    if not await writer.try_acquire_ingestion_lock():
        raise Conflict("ya hay una ingestión en curso", code="ingestion.already_running")

    by_uc_id: dict[str, list[ParsedUC]] = defaultdict(list)
    skipped = 0
    for raw in source.load(path):
        parsed = parse_fn(raw, kb_root=path)
        if isinstance(parsed, ParseError):
            skipped += 1
            continue
        if only_domain is not None and parsed.domain != only_domain:
            continue
        by_uc_id[parsed.uc_id].append(parsed)

    duplicates = {uc_id: docs for uc_id, docs in by_uc_id.items() if len(docs) > 1}
    if duplicates:
        raise Validation(
            "uc_id duplicado entre ficheros",
            code="ingestion.duplicate_uc_id",
            details={uc_id: [doc.source_url for doc in docs] for uc_id, docs in duplicates.items()},
        )

    parsed_docs = [docs[0] for docs in by_uc_id.values()]
    if not parsed_docs and not force_reconcile:
        return IngestReport(processed=0, created=0, updated=0, skipped=skipped, deleted=0)

    existing_uc_ids_before = await writer.existing_uc_ids()

    plan = [
        (
            doc,
            await _diff_and_embed(
                doc,
                writer=writer,
                model=model,
                token_budget=token_budget,
                encoding=encoding,
                batch_size=batch_size,
                embedding_model_name=embedding_model_name,
                dry_run=dry_run,
            ),
        )
        for doc in parsed_docs
    ]

    created = 0
    updated = 0
    for doc, chunk_writes in plan:
        if not dry_run:
            await writer.upsert_document(_to_draft(doc), chunk_writes)
        if doc.uc_id in existing_uc_ids_before:
            updated += 1
        else:
            created += 1

    origin_uc_ids = {doc.uc_id for doc in parsed_docs}
    retired = existing_uc_ids_before - origin_uc_ids
    deleted = len(retired)
    if retired and not dry_run:
        await writer.delete_by_uc_ids(retired)

    return IngestReport(
        processed=len(parsed_docs),
        created=created,
        updated=updated,
        skipped=skipped,
        deleted=deleted,
    )


async def _diff_and_embed(
    doc: ParsedUC,
    *,
    writer: KBIndexWriter,
    model: EmbeddingModel,
    token_budget: int,
    encoding: tiktoken.Encoding,
    batch_size: int,
    embedding_model_name: str,
    dry_run: bool = False,
) -> list[ChunkWrite]:
    """Chunkea `doc`, compara contra el contenido ya persistido, y embebe SOLO lo nuevo/cambiado.

    Con `dry_run=True` NUNCA llama a `embed()` (evita coste/red real en una simulación) — los chunks
    que se embeberían quedan con `vector=None` en el resultado, que en modo dry-run nunca se escribe.
    """
    chunks = chunk(doc, token_budget=token_budget, encoding=encoding)
    existing_contents = await writer.existing_chunk_contents(doc.uc_id)

    unchanged: dict[int, ChunkWrite] = {}
    to_embed: list[Chunk] = []
    for candidate in chunks:
        if existing_contents.get(candidate.ordinal) == candidate.content:
            unchanged[candidate.ordinal] = ChunkWrite(
                ordinal=candidate.ordinal,
                section_type=candidate.section_type,
                content=candidate.content,
                token_count=candidate.token_count,
                vector=None,
            )
        else:
            to_embed.append(candidate)

    if dry_run:
        changed = {
            candidate.ordinal: ChunkWrite(
                ordinal=candidate.ordinal,
                section_type=candidate.section_type,
                content=candidate.content,
                token_count=candidate.token_count,
                vector=None,
            )
            for candidate in to_embed
        }
    else:
        embedded = await embed(to_embed, model, batch_size=batch_size) if to_embed else []
        changed = {
            item.chunk.ordinal: ChunkWrite(
                ordinal=item.chunk.ordinal,
                section_type=item.chunk.section_type,
                content=item.chunk.content,
                token_count=item.chunk.token_count,
                vector=item.vector,
                model=embedding_model_name,
            )
            for item in embedded
        }

    by_ordinal = {**unchanged, **changed}
    return [by_ordinal[ordinal] for ordinal in sorted(by_ordinal)]


def _to_draft(doc: ParsedUC) -> KBDocumentDraft:
    is_glosario = doc.uc_id.startswith(GLOSARIO_UC_ID_PREFIX)
    return KBDocumentDraft(
        uc_id=doc.uc_id,
        domain=KbDomain(doc.domain),
        package=_GLOSARIO_PACKAGE if is_glosario else Package(doc.package),
        estado=_GLOSARIO_ESTADO if is_glosario else KbEstado(doc.estado),
        title=doc.title,
        source_url=doc.source_url,
        traza=doc.traza,
        updated=doc.updated,
    )
