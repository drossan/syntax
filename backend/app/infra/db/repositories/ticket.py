"""app.infra.db.repositories.ticket — adaptador SQLAlchemy de `TicketRepository`.

`Ticket` lleva `TenantMixin` (tabla de NEGOCIO con RLS) — a diferencia de las de identidad, aquí SÍ
aplicaría `BaseRepository`, pero `list()` necesita paginación/filtros/orden dinámicos que esa base
genérica no cubre, así que se escribe una query propia (mismo patrón que el resto de adaptadores:
consultas directas, `PortError` envolviendo cualquier excepción de infra).

`list()` traduce `sort` (YA validado por el router contra `TICKET_SORT_FIELDS`) a una columna ORM real
vía un mapeo fijo — nunca interpola el string en SQL.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.business import Ticket
from app.domain.entities.enums import KbDomain, TicketPriority, TicketStatus
from app.domain.errors import PortError
from app.domain.ports.repositories import PageResult
from app.infra.db.models import Ticket as TicketModel
from app.infra.db.models.enums import KbDomain as KbDomainOrm
from app.infra.db.models.enums import TicketPriority as TicketPriorityOrm
from app.infra.db.models.enums import TicketStatus as TicketStatusOrm
from app.infra.db.repositories._enum_bridge import to_domain, to_orm

_SORT_COLUMNS = {
    "updated_at": TicketModel.updated_at,
    "created_at": TicketModel.created_at,
    "priority": TicketModel.priority,
    "sla_due": TicketModel.sla_due,
}
"""Mapeo `TICKET_SORT_FIELDS` (puerto) → columna ORM real — mismas claves por construcción."""


def _to_domain(row: TicketModel) -> Ticket:
    return Ticket(
        id=row.id,
        tenant_id=row.tenant_id,
        subject=row.subject,
        status=to_domain(TicketStatus, row.status),
        priority=to_domain(TicketPriority, row.priority),
        domain=to_domain(KbDomain, row.domain) if row.domain is not None else None,
        category=row.category,
        requester_id=row.requester_id,
        assignee_id=row.assignee_id,
        sla_due=row.sla_due,
        csat=row.csat,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyTicketRepository:
    """Adaptador de `TicketRepository` (`app.domain.ports.repositories`)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, ticket_id: uuid.UUID) -> Ticket | None:
        try:
            row = await self._session.get(TicketModel, ticket_id)
        except Exception as exc:
            raise PortError("fallo al leer ticket") from exc
        return _to_domain(row) if row is not None else None

    async def add(self, ticket: Ticket) -> Ticket:
        row = TicketModel(
            id=ticket.id,
            tenant_id=ticket.tenant_id,
            subject=ticket.subject,
            status=to_orm(TicketStatusOrm, ticket.status),
            priority=to_orm(TicketPriorityOrm, ticket.priority),
            domain=to_orm(KbDomainOrm, ticket.domain) if ticket.domain is not None else None,
            category=ticket.category,
            requester_id=ticket.requester_id,
            assignee_id=ticket.assignee_id,
            sla_due=ticket.sla_due,
            csat=ticket.csat,
        )
        self._session.add(row)
        try:
            await self._session.flush()
        except Exception as exc:
            raise PortError("fallo al crear ticket") from exc
        return _to_domain(row)

    async def update(self, ticket: Ticket) -> Ticket:
        try:
            row = await self._session.get(TicketModel, ticket.id)
        except Exception as exc:
            raise PortError("fallo al leer ticket") from exc
        if row is None:
            raise PortError(f"ticket {ticket.id} no existe")
        row.subject = ticket.subject
        row.status = to_orm(TicketStatusOrm, ticket.status)
        row.priority = to_orm(TicketPriorityOrm, ticket.priority)
        row.domain = to_orm(KbDomainOrm, ticket.domain) if ticket.domain is not None else None
        row.category = ticket.category
        row.requester_id = ticket.requester_id
        row.assignee_id = ticket.assignee_id
        row.sla_due = ticket.sla_due
        row.csat = ticket.csat
        try:
            await self._session.flush()
            await self._session.refresh(row)
        except Exception as exc:
            raise PortError("fallo al actualizar ticket") from exc
        return _to_domain(row)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        page: int,
        page_size: int,
        status: TicketStatus | None = None,
        priority: TicketPriority | None = None,
        domain: KbDomain | None = None,
        assignee_id: uuid.UUID | None = None,
        sort: str = "-updated_at",
    ) -> PageResult[Ticket]:
        column = _SORT_COLUMNS[sort.removeprefix("-")]
        order_by = column.desc() if sort.startswith("-") else column.asc()
        conditions = [TicketModel.tenant_id == tenant_id]
        if status is not None:
            conditions.append(TicketModel.status == to_orm(TicketStatusOrm, status))
        if priority is not None:
            conditions.append(TicketModel.priority == to_orm(TicketPriorityOrm, priority))
        if domain is not None:
            conditions.append(TicketModel.domain == to_orm(KbDomainOrm, domain))
        if assignee_id is not None:
            conditions.append(TicketModel.assignee_id == assignee_id)
        offset = (page - 1) * page_size
        try:
            total = (
                await self._session.execute(
                    select(func.count()).select_from(TicketModel).where(*conditions)
                )
            ).scalar_one()
            rows = (
                await self._session.execute(
                    select(TicketModel)
                    .where(*conditions)
                    .order_by(order_by)
                    .offset(offset)
                    .limit(page_size)
                )
            ).scalars()
            items = [_to_domain(row) for row in rows]
        except Exception as exc:
            raise PortError("fallo al listar tickets") from exc
        return PageResult(items=items, total=total)
