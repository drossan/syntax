"""app.domain.services.classification — clasificación de tickets (FR-023/024, CU-BE-05 parcial).

`classify()` delega en `ChatModel.classify` (structured output); no parsea prosa ni aplica reglas/regex
propias. **No depende de `ticket_service`**: aplicar el resultado a `Ticket.domain`/`Ticket.priority` es
responsabilidad del llamante (nodo `classify` del grafo, tarea 15), que conoce la secuencia completa.
"""

from pydantic import BaseModel

from app.domain.entities.enums import KbDomain, TicketPriority
from app.domain.errors import PortError, Validation
from app.domain.ports.llm import ChatModel


class Classification(BaseModel):
    """Contrato de clasificación (FR-023).

    `dominio=None` es la señal de "no clasificable con confianza" (FR-024) — no se inventa un campo
    `confidence` que FR-023 no pide; el llamante decide el fallback (retrieval sin filtro de dominio).
    """

    categoria: str
    dominio: KbDomain | None
    prioridad: TicketPriority
    resoluble: bool


async def classify(ticket_text: str, chat_model: ChatModel) -> Classification:
    """Clasifica `ticket_text` vía `chat_model.classify`.

    Fallo del proveedor (timeout, error de API) se propaga envuelto en `PortError`; una salida que no
    valida contra `Classification` se rechaza con `Validation` — nunca se acepta un `Classification` a
    medias.
    """
    try:
        result = await chat_model.classify(ticket_text, Classification)
    except PortError:
        raise
    except Exception as exc:
        raise PortError(f"fallo al clasificar el ticket: {exc}") from exc
    if not isinstance(result, Classification):
        raise Validation(
            "la salida del ChatModel no es una Classification válida",
            code="classification.invalid_output",
        )
    return result
