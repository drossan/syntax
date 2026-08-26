"""app.domain.ports.vector — puerto de ESCRITURA de la KB (ingestión, tarea backend-kb-ingestion-02).

`KBIndexWriter`, no `VectorStore`: ese nombre ya lo tiene el puerto de LECTURA
(`app.domain.ports.vectorstore.VectorStore`, usado hoy por el router `kb`) — dos responsabilidades
distintas (escritura de ingestión vs lectura del router) con el mismo nombre habrían colisionado.

`search` se fijó aquí con su firma FINAL (decisión de `grilling`/`design-review` del plan
`kb-ingestion`) y ya está implementada de verdad (`backend-kb-retriever-04`): la usan tanto el camino
HTTP del panel como, en el plan del agent-graph, el nodo `retrieve`.

**Los dos puertos se mantienen** (ADR-0018): este de escritura+`search`, y `VectorStore` para la lectura
del router. Colapsarlos metería lectura paginada de negocio dentro de un puerto llamado `KBIndexWriter`
e invertiría la dirección de dependencia del router — router y agente son consumidores con formas
distintas (página de documentos deduplicados vs chunks con `chunk_id`). La deuda de tener dos puertos
sobre la misma tabla está registrada en el ADR y mitigada con la regla **un solo sitio por operación**:
el SQL de escritura de `kb_document` vive aquí, el de lectura en `PgVectorStore`.

Los tipos de datos de este módulo (`KBDocumentDraft`/`ChunkWrite`/`UpsertReport`/`Hit`) son DTOs
propios del puerto — mismo patrón que `PageResult` en `domain.ports.repositories` (`@dataclass`, no
`pydantic.BaseModel`: no son entidades de dominio compartidas, solo la forma de entrada/salida de
este puerto). `KBDocumentDraft` es distinto de `KBDocument` (la entidad de LECTURA de
`entities.business`, ya cerrada para la tarea 14) — evita acoplar el shape de escritura al de lectura.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.domain.entities.enums import KbDomain, KbEstado, Package


@dataclass(frozen=True)
class KBDocumentDraft:
    """Datos de escritura de un documento KB (frontmatter + Trazabilidad ya parseados)."""

    uc_id: str
    domain: KbDomain
    package: Package
    estado: KbEstado
    title: str
    source_url: str
    traza: list[str] | None = None
    updated: datetime | None = None


@dataclass(frozen=True)
class ChunkWrite:
    """Un chunk a escribir dentro de `upsert_document`.

    `vector=None` significa "no toques el embedding existente de este `ordinal`" (edición parcial de
    un UC, decisión de `scenario-coverage`: el pipeline solo manda vector real para los chunks cuyo
    contenido cambió) — `model` se ignora cuando `vector` es `None`.
    """

    ordinal: int
    section_type: str
    content: str
    token_count: int
    vector: list[float] | None = None
    model: str = ""


@dataclass(frozen=True)
class UpsertReport:
    """Resultado de `upsert_document`: `created` distingue alta de actualización; `chunks_deleted`
    cuenta los `kb_chunk` (con su `embedding`) borrados por reconciliación de `ordinal`."""

    created: bool
    chunks_deleted: int


@dataclass(frozen=True)
class Hit:
    """Un chunk recuperado por `search` (`rag-ingestion.md` §6.1).

    La unidad es el **chunk**, no el documento: el camino del agente los consume tal cual (varias
    secciones del mismo UC son varias piezas de contexto legítimas), y el camino HTTP los deduplica por
    `uc_id` en `app.rag` antes de publicarlos.

    - **`content`** es el texto COMPLETO del chunk: alimenta el `snippet` del panel y el prompt del nodo
      `generate`. Truncarlo aquí dejaría al agente sin el texto, y pedirlo con una segunda query por
      `chunk_id` sería un N+1 disfrazado de disciplina.
    - **`score` es la similitud CRUDA**, acotada a `[0, 1]`, **sin** el peso de `estado`. El peso se
      aplica al producir el `KBSearchHit` de la API (`app.rag.reranker`): si viajara ya aplicado aquí,
      la confianza híbrida de CU-BE-05 —que se compone de esta similitud más el `grade` del LLM—
      contaría `estado` **dos veces**.
    """

    uc_id: str
    chunk_id: uuid.UUID
    section_type: str
    title: str
    source_url: str
    domain: KbDomain
    estado: KbEstado
    score: float
    content: str


class KBIndexWriter(Protocol):
    """Puerto de escritura de la KB (ingestión)."""

    async def existing_uc_ids(self) -> set[str]:
        """El conjunto de `uc_id` ya persistidos (para el diff de reconciliación del pipeline)."""
        ...

    async def existing_chunk_contents(self, uc_id: str) -> dict[int, str]:
        """`{ordinal: content}` del documento persistido para `uc_id`; `{}` si no existe."""
        ...

    async def upsert_document(self, doc: KBDocumentDraft, chunks: list[ChunkWrite]) -> UpsertReport:
        """Upsert idempotente por `uc_id`. Borra los `kb_chunk`/`embedding` cuyo `ordinal` ya no está
        en `chunks`, aunque el documento siga vivo (no solo cuando el UC entero se retira).

        :raises app.domain.errors.PortError: fallo de infraestructura (BD caída/timeout).
        """
        ...

    async def delete_by_uc_ids(self, uc_ids: set[str]) -> int:
        """Borra (cascada a chunk/embedding) los documentos de `uc_ids`; devuelve cuántos borró."""
        ...

    async def search(
        self,
        query_vector: list[float],
        *,
        top_k: int,
        domain: KbDomain | None = None,
        package: Package | None = None,
        estado: KbEstado | None = None,
    ) -> list[Hit]:
        """Búsqueda por similitud coseno (fijada sin implementar — tarea 14, retriever CU-BE-05).

        :raises NotImplementedError: siempre, hasta que la tarea 14 la implemente de verdad.
        """
        ...

    async def try_acquire_ingestion_lock(self) -> bool:
        """`pg_try_advisory_lock`, NO bloqueante: `True` si lo adquiere, `False` de inmediato si otra
        ejecución ya lo tiene (nunca espera). El pipeline (`-06`) decide qué hacer con `False`."""
        ...
