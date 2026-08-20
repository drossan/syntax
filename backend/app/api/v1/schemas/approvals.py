"""app.api.v1.schemas.approvals — DTOs del router `approvals` (1:1 con `api-contract.yaml`)."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class ApprovalTask(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    agent_run_id: uuid.UUID
    status: str
    draft_body: str
    final_body: str | None = None
    human_note: str | None = None
    decided_by: uuid.UUID | None = None
    decided_at: datetime | None = None
    created_at: datetime | None = None


class ApprovalApproveRequest(BaseModel):
    human_note: str | None = None


class ApprovalEditRequest(BaseModel):
    final_body: str
    human_note: str | None = None


class ApprovalRejectRequest(BaseModel):
    human_note: str
