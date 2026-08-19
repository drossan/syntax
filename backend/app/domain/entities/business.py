"""app.domain.entities.business — entidades de negocio (data-model.md §4.2) + Resource + AuditLogEntry.

`Resource` (`rbac.md §7`) aporta el `tenant_id`/dueño que `rbac_service.authorize` valida contra el
ámbito del sujeto; `tenant_id` es `None` para recursos globales (KB, sin RLS de tenant). `AuditLogEntry`
espeja `audit_log` (data-model.md §4.2).
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.domain.entities.enums import (
    AgentRunStatus,
    ApprovalStatus,
    KbDomain,
    KbEstado,
    MessageVisibility,
    NotificationType,
    Package,
    TicketPriority,
    TicketStatus,
)


class Ticket(BaseModel):
    """Ticket de soporte."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    subject: str
    status: TicketStatus
    priority: TicketPriority
    domain: KbDomain | None = None
    category: str | None = None
    requester_id: uuid.UUID | None = None
    assignee_id: uuid.UUID | None = None
    sla_due: datetime | None = None
    csat: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Message(BaseModel):
    """Mensaje de un ticket."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    ticket_id: uuid.UUID
    author_id: uuid.UUID | None = None
    visibility: MessageVisibility
    is_ai_draft: bool = False
    body: str
    created_at: datetime | None = None


class Attachment(BaseModel):
    """Adjunto de un mensaje. El binario vive fuera de Postgres (`storage_key` → puerto `Storage`,
    tarea 08); `tenant_id` propio (no derivado del mensaje) porque la tabla lleva `TenantMixin`/RLS."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    message_id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    storage_key: str
    created_at: datetime | None = None


class ApprovalTask(BaseModel):
    """Tarea HITL: draft del agente que un humano aprueba/edita/rechaza."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    ticket_id: uuid.UUID
    agent_run_id: uuid.UUID
    status: ApprovalStatus
    draft_body: str
    final_body: str | None = None
    human_note: str | None = None
    decided_by: uuid.UUID | None = None
    decided_at: datetime | None = None
    created_at: datetime | None = None


class AgentRun(BaseModel):
    """Una ejecución del grafo LangGraph."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    ticket_id: uuid.UUID
    langgraph_thread_id: str
    run_seq: int
    status: AgentRunStatus
    confidence: float | None = None
    escalated: bool = False
    sources: list[dict[str, Any]] | None = None
    error: str | None = None
    langsmith_trace_url: str | None = None
    created_at: datetime | None = None
    finished_at: datetime | None = None


class Notification(BaseModel):
    """Notificación in-app."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    type: NotificationType
    payload: dict[str, Any]
    read_at: datetime | None = None
    created_at: datetime | None = None


class Resource(BaseModel):
    """Recurso sobre el que se autoriza una acción (`rbac.md §7`).

    `tenant_id=None` marca un recurso **global** (p.ej. KB): `authorize` no compara tenant en ese caso.
    """

    tenant_id: uuid.UUID | None = None


class AuditLogEntry(BaseModel):
    """Entrada de auditoría append-only (data-model.md §4.2).

    `tenant_id` es obligatorio: `audit_log` es una tabla de NEGOCIO con RLS (`data-model.md` §2/§6,
    columna `NOT NULL`) — un `AuditLogRepository` real (06) necesita el tenant de cada entrada para
    persistirla; sin él, la única vía de detectarlo era una `IntegrityError` en el primer `INSERT` real
    (el puerto solo se había ejercitado con fakes en `domain-services`, que no validan el shape de la
    fila)."""

    tenant_id: uuid.UUID
    action: str
    entity_type: str
    entity_id: str
    payload: dict[str, Any]
    actor_id: uuid.UUID | None = None


class KBDocument(BaseModel):
    """Documento de KB (global, sin `tenant_id` — recurso cross-tenant, `rbac.md`). `uc_id` es la
    clave única de negocio (contrato); sin `id` propio expuesto (detalle interno de `kb_document`)."""

    uc_id: str
    domain: KbDomain
    package: Package
    estado: KbEstado
    title: str
    source_url: str
    updated: datetime | None = None


class KBSearchHit(BaseModel):
    """Resultado de `VectorStore.search` — recorte de `KBDocument` + `section_type`/`score` del
    retrieval (tarea 14: hoy el adaptador es un stub, el shape ya es el final)."""

    uc_id: str
    title: str
    section_type: str
    domain: KbDomain
    estado: KbEstado
    source_url: str
    score: float
