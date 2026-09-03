"""app.domain.services.classification — clasificación de tickets (FR-023/024, CU-BE-05 parcial).

`classify()` delega en `ChatModel.classify` (structured output); no parsea prosa ni aplica reglas/regex
propias. **No depende de `ticket_service`**: aplicar el resultado a `Ticket.domain`/`Ticket.priority` es
responsabilidad del llamante (nodo `classify` del grafo, tarea 15), que conoce la secuencia completa.
"""

from pydantic import BaseModel

from app.domain.entities.enums import KbDomain, TicketPriority
from app.domain.errors import PortError, Validation
from app.domain.ports.llm import ChatModel

_DOMAINS = ", ".join(domain.value for domain in KbDomain)
_PRIORITIES = ", ".join(priority.value for priority in TicketPriority)


class Classification(BaseModel):
    """Contrato de clasificación (FR-023).

    `dominio=None` es la señal de "no clasificable con confianza" (FR-024) — no se inventa un campo
    `confidence` que FR-023 no pide; el llamante decide el fallback (retrieval sin filtro de dominio).
    """

    categoria: str
    dominio: KbDomain | None
    prioridad: TicketPriority
    resoluble: bool


def _build_prompt(ticket_text: str) -> str:
    """Instrucciones reales para el clasificador — antes de este fix, `classify()` mandaba
    `ticket_text` tal cual como único prompt: el LLM adivinaba qué significa cada campo sin ninguna
    guía (reproducido en vivo: un ticket de producto legítimo, con dominio identificable y respuesta en
    la KB, salía `resoluble=False`). `TICKET` viaja en su propia sección, tratado como dato — nunca
    como instrucción (RN-3 de CU-BE-06, mismo patrón que `generate.py`/`grade.py`)."""
    return (
        "Clasifica el siguiente ticket de soporte de Griddo (CMS headless). Devuelve exactamente los "
        "4 campos pedidos.\n\n"
        "- categoria: una etiqueta breve y libre que resuma el tipo de problema.\n"
        f"- dominio: el área de la documentación más relacionada, una de: {_DOMAINS}. Usa null SOLO "
        "si el ticket es tan ambiguo que ningún dominio encaja con confianza razonable.\n"
        f"- prioridad: una de {_PRIORITIES}, según el impacto descrito.\n"
        "- resoluble: true si el ticket describe un problema o duda sobre el uso o comportamiento del "
        "producto que EN PRINCIPIO podría responderse con la documentación — aunque tú no conozcas la "
        "respuesta ahora mismo; un paso posterior con acceso a la documentación real decide si hay "
        "contexto suficiente. Un mensaje de error del producto (aunque no sepas la causa) es SIEMPRE "
        "resoluble=true. Usa resoluble=false solo si el ticket es spam, un saludo sin pregunta, o pide "
        "algo que ningún manual de producto podría cubrir (una promesa comercial, por ejemplo).\n\n"
        f"TICKET:\n{ticket_text}"
    )


async def classify(ticket_text: str, chat_model: ChatModel) -> Classification:
    """Clasifica `ticket_text` vía `chat_model.classify`, con instrucciones reales (`_build_prompt`).

    Fallo del proveedor (timeout, error de API) se propaga envuelto en `PortError`; una salida que no
    valida contra `Classification` se rechaza con `Validation` — nunca se acepta un `Classification` a
    medias.
    """
    try:
        result = await chat_model.classify(_build_prompt(ticket_text), Classification)
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
