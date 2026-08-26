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
    """1:1 con el `KBSearchHit` de `api-contract.yaml`.

    `snippet` estaba **declarado en el contrato y renderizado por el front** desde `routers-core`, pero
    faltaba aquí: un drift que no se notaba solo porque el adaptador era un stub que devolvía `[]`. Con
    datos reales, cada tarjeta habría pintado un snippet vacío. La guardia contrato↔OpenAPI de `-07`
    existe para que no vuelva a pasar.
    """

    uc_id: str
    title: str
    section_type: str
    domain: str
    estado: str
    source_url: str
    score: float
    snippet: str = ""
