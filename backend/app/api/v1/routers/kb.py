"""app.api.v1.routers.kb — búsqueda y documentos de KB (contrato 06/09).

KB es un recurso GLOBAL (sin `tenant_id`/RLS, `rbac.md`) — `require_capability("kb.read")` se reusa
igual que en el resto de routers (decide `global_scope`/`tenant_scope` según el ámbito concedido de la
capacidad al subject), pero el resultado es indiferente aquí: `kb_document`/`kb_chunk` no llevan
`TenantMixin`, así que ninguna política RLS depende del GUC que abra.

**Estado transitorio**: el adaptador cableado hoy (`StubVectorStore`, tarea 09) devuelve siempre
vacío/`None`, así que `/kb` se ve vacío aunque la KB esté ingerida. Es el andamio de la tarea 09, no un
comportamiento deseable: el plan `kb-retriever` lo **borra** y cablea el adaptador real
(`PgVectorStore`) en su tarea `-07`, que además valida `q` (vacía / solo espacios / demasiado larga →
**422**, sin llamar al proveedor de embeddings) y añade el `snippet` que el contrato declara y este
router todavía no mapea. Decisiones y porqués: CU-BE-12 + ADR-0018.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.common import Page
from app.api.v1.schemas.kb import KBDocument as KBDocumentSchema
from app.api.v1.schemas.kb import KBSearchHit as KBSearchHitSchema
from app.core.deps import get_vector_store, require_capability
from app.domain.entities.business import KBDocument as KBDocumentEntity
from app.domain.entities.business import KBSearchHit as KBSearchHitEntity
from app.domain.entities.enums import KbDomain, KbEstado, Package
from app.domain.entities.identity import Subject
from app.domain.errors import NotFound
from app.domain.ports.vectorstore import VectorStore

router = APIRouter(prefix="/kb", tags=["kb"])

_CAPABILITY = "kb.read"


def _document_to_schema(document: KBDocumentEntity) -> KBDocumentSchema:
    return KBDocumentSchema(
        uc_id=document.uc_id,
        domain=document.domain.value,
        package=document.package.value,
        estado=document.estado.value,
        title=document.title,
        source_url=document.source_url,
        updated=document.updated,
    )


def _hit_to_schema(hit: KBSearchHitEntity) -> KBSearchHitSchema:
    return KBSearchHitSchema(
        uc_id=hit.uc_id,
        title=hit.title,
        section_type=hit.section_type,
        domain=hit.domain.value,
        estado=hit.estado.value,
        source_url=hit.source_url,
        score=hit.score,
        snippet=hit.snippet,
    )


@router.get("/search")
async def search(
    q: str = Query(...),
    domain: KbDomain | None = Query(None),
    package: Package | None = Query(None),
    estado: KbEstado | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    subject_session: tuple[Subject, AsyncSession] = Depends(require_capability(_CAPABILITY)),
    vector_store: VectorStore = Depends(get_vector_store),
) -> Page[KBSearchHitSchema]:
    _subject, _session = subject_session
    hits, total = await vector_store.search(
        q, domain=domain, package=package, estado=estado, page=page, page_size=page_size
    )
    return Page(
        items=[_hit_to_schema(h) for h in hits], page=page, page_size=page_size, total=total
    )


@router.get("/documents")
async def list_documents(
    domain: KbDomain | None = Query(None),
    package: Package | None = Query(None),
    estado: KbEstado | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    subject_session: tuple[Subject, AsyncSession] = Depends(require_capability(_CAPABILITY)),
    vector_store: VectorStore = Depends(get_vector_store),
) -> Page[KBDocumentSchema]:
    _subject, _session = subject_session
    documents, total = await vector_store.list_documents(
        domain=domain, package=package, estado=estado, page=page, page_size=page_size
    )
    return Page(
        items=[_document_to_schema(d) for d in documents],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/documents/{uc_id}")
async def get_document(
    uc_id: str,
    subject_session: tuple[Subject, AsyncSession] = Depends(require_capability(_CAPABILITY)),
    vector_store: VectorStore = Depends(get_vector_store),
) -> KBDocumentSchema:
    _subject, _session = subject_session
    document = await vector_store.get_document(uc_id)
    if document is None:
        raise NotFound(f"documento de KB {uc_id} no existe", code="kb.document_not_found")
    return _document_to_schema(document)
