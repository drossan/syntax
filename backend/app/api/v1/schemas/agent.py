"""app.api.v1.schemas.agent — DTOs del router `agent` (1:1 con `api-contract.yaml`).

`AgentRun` no expone `tenant_id` ni `langgraph_thread_id` (fuera del contrato — detalle interno del
checkpointer, 15/16); `sources` es siempre una lista (nunca `null`), aunque el dominio la modele como
`list[dict] | None` (JSONB sin filas todavía).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel


class Citation(BaseModel):
    uc_id: str
    title: str
    section_type: str
    source_url: str
    score: float


class AgentRun(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    run_seq: int
    status: str
    confidence: float | None = None
    escalated: bool
    sources: list[Citation] = []
    error: str | None = None
    langsmith_trace_url: str | None = None
    created_at: datetime | None = None
    finished_at: datetime | None = None
