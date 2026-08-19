"""app.api.v1.schemas.kb — DTOs del router `kb` (1:1 con `api-contract.yaml`)."""

from datetime import datetime

from pydantic import BaseModel


class KBDocument(BaseModel):
    uc_id: str
    domain: str
    package: str
    estado: str
    title: str
    source_url: str
    updated: datetime | None = None


class KBSearchHit(BaseModel):
    uc_id: str
    title: str
    section_type: str
    domain: str
    estado: str
    source_url: str
    score: float
