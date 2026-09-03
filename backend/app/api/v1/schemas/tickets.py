"""app.api.v1.schemas.tickets — DTOs del router `tickets` (1:1 con `api-contract.yaml`)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class Ticket(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    subject: str
    status: str
    priority: str
    domain: str | None = None
    category: str | None = None
    requester_id: uuid.UUID | None = None
    assignee_id: uuid.UUID | None = None
    assignee_email: str | None = None
    sla_due: datetime | None = None
    csat: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TicketCreate(BaseModel):
    subject: str
    body: str
    priority: str | None = None


class TicketUpdate(BaseModel):
    subject: str | None = None
    priority: str | None = None
    category: str | None = None
    csat: int | None = Field(default=None, ge=1, le=5)


class TicketTransitionRequest(BaseModel):
    status: str


class TicketAssignRequest(BaseModel):
    assignee_id: uuid.UUID | None = None
