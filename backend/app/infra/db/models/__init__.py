"""app.infra.db.models — modelos SQLAlchemy 2 (una clase por entidad de data-model.md).

Importar este paquete **registra** todos los modelos en ``Base.metadata`` (lo consume
``alembic/env.py`` como ``target_metadata`` y el test de drift ``compare_metadata``, 06).

Grupos por frontera RLS (data-model.md §2):
  - **identidad/RBAC** (``identity``): cross-tenant de sistema, SIN RLS de fila (tarea 03).
  - **negocio** (``business``): ``tenant_id`` + RLS (tarea 04).
  - **KB** (``kb``): global, sin RLS (tarea 05).

Anti-patrón (hexagonal): exponer estos modelos a ``app.domain`` (el dominio no conoce SQLAlchemy).
"""

from app.infra.db.models.business import (
    AgentRun,
    ApprovalTask,
    Attachment,
    AuditLog,
    Message,
    Notification,
    Ticket,
)
from app.infra.db.models.identity import (
    AuthToken,
    Capability,
    RefreshSession,
    Role,
    RoleCapability,
    Tenant,
    User,
    UserRole,
)
from app.infra.db.models.kb import Embedding, KBChunk, KBDocument

__all__ = [
    "AgentRun",
    "ApprovalTask",
    "Attachment",
    "AuditLog",
    "AuthToken",
    "Capability",
    "Embedding",
    "KBChunk",
    "KBDocument",
    "Message",
    "Notification",
    "RefreshSession",
    "Role",
    "RoleCapability",
    "Tenant",
    "Ticket",
    "User",
    "UserRole",
]
