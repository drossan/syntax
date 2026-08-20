"""app.api.v1.schemas.common — schemas Pydantic compartidos por todos los routers (api-contract.yaml).

`Page[T]` (paginación genérica) y `Problem` (envelope de error problem+json, RFC 9457) — el shape
exacto del contrato compartido. `Problem` documenta la forma que `app.api.errors` produce a mano (los
handlers construyen el dict directamente por rendimiento; este schema es la referencia OpenAPI/
`response_model` para los routers que quieran declararlo explícitamente).
"""

from pydantic import BaseModel


class Page[T](BaseModel):
    """Página de resultados: `items`/`page`/`page_size`/`total` (contrato, sin campos extra)."""

    items: list[T]
    page: int
    page_size: int
    total: int


class ProblemErrorEntry(BaseModel):
    """Una entrada de `Problem.errors[]` (error de validación por campo)."""

    field: str
    message: str
    code: str


class Problem(BaseModel):
    """Envelope de error `application/problem+json` (RFC 9457). `type` por defecto `about:blank`
    (no publicamos URIs de tipo de problema propias); `instance`/`errors` opcionales."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    errors: list[ProblemErrorEntry] | None = None
