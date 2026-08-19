"""app.infra.db.repositories.audit_log — adaptador SQLAlchemy de `AuditLogRepository`.

`audit_log` es una tabla de NEGOCIO con RLS (`TenantMixin`, `data-model.md` §2/§6) — `tenant_id` viaja
en la propia `AuditLogEntry` (obligatorio en el dominio desde la tarea 06), no se resuelve aquí.
Append-only: no hay `get`/`update`/`delete`, solo `add`.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.business import AuditLogEntry
from app.domain.errors import PortError
from app.infra.db.models import AuditLog as AuditLogModel


class SqlAlchemyAuditLogRepository:
    """Adaptador de `AuditLogRepository` (`app.domain.ports.repositories`)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entry: AuditLogEntry) -> None:
        row = AuditLogModel(
            id=uuid.uuid4(),
            tenant_id=entry.tenant_id,
            actor_id=entry.actor_id,
            action=entry.action,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            payload=entry.payload,
        )
        self._session.add(row)
        try:
            await self._session.flush()
        except Exception as exc:
            raise PortError("fallo al escribir audit log") from exc
