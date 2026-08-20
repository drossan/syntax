"""app.api.v1.schemas.notifications — DTOs del router `notifications` (1:1 con `api-contract.yaml`)."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class Notification(BaseModel):
    id: uuid.UUID
    type: str
    payload: dict[str, Any]
    read_at: datetime | None = None
    created_at: datetime | None = None
