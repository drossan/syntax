"""app.api.v1.schemas.messages — DTOs del router `messages` (1:1 con `api-contract.yaml`)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class Message(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    author_id: uuid.UUID | None = None
    visibility: str
    is_ai_draft: bool = False
    body: str
    created_at: datetime | None = None


class MessageCreate(BaseModel):
    body: str = Field(min_length=1)
    visibility: str


class Attachment(BaseModel):
    id: uuid.UUID
    message_id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
