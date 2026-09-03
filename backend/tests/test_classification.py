"""Tests de app.domain.services.classification (tarea backend-domain-services-07).

Nivel unit, con un `ChatModel` fake. Traza a CU-BE-05 (parcial: solo la parte de `classify`).
"""

import pytest
from app.domain.entities.enums import KbDomain, TicketPriority
from app.domain.errors import PortError, Validation
from app.domain.services.classification import Classification, classify


class _FakeChatModel:
    def __init__(self, *, result: object = None, raises: Exception | None = None) -> None:
        self._result = result
        self._raises = raises
        self.received_text: str | None = None

    async def classify(self, text: str, schema: type) -> object:
        self.received_text = text
        if self._raises is not None:
            raise self._raises
        return self._result


async def test_classify_with_recognizable_domain_returns_concrete_kb_domain() -> None:
    """Dominio reconocible: la Classification trae un KbDomain concreto (no None)."""
    expected = Classification(
        categoria="incidencia",
        dominio=KbDomain.forms_and_submissions,
        prioridad=TicketPriority.high,
        resoluble=True,
    )
    chat_model = _FakeChatModel(result=expected)
    result = await classify("no puedo enviar el formulario", chat_model)
    assert result.dominio is KbDomain.forms_and_submissions
    assert result.prioridad is TicketPriority.high
    assert result.resoluble is True
    assert result.categoria == "incidencia"


async def test_classify_with_uncertain_domain_returns_none() -> None:
    """Dominio incierto: dominio=None es la señal de 'no clasificable con confianza' (FR-024)."""
    expected = Classification(
        categoria="consulta general",
        dominio=None,
        prioridad=TicketPriority.normal,
        resoluble=False,
    )
    chat_model = _FakeChatModel(result=expected)
    result = await classify("tengo una duda", chat_model)
    assert result.dominio is None


async def test_classify_propagates_provider_failure_wrapped_in_port_error() -> None:
    """Fallo del ChatModel (timeout/error de proveedor) se propaga envuelto en PortError."""
    chat_model = _FakeChatModel(raises=TimeoutError("provider timed out"))
    with pytest.raises(PortError):
        await classify("texto cualquiera", chat_model)


async def test_classify_does_not_double_wrap_an_existing_port_error() -> None:
    """Si el fake ya lanza PortError, classify() no lo envuelve en un segundo PortError."""
    original = PortError("proveedor caído")
    chat_model = _FakeChatModel(raises=original)
    with pytest.raises(PortError) as exc_info:
        await classify("texto cualquiera", chat_model)
    assert exc_info.value is original


async def test_classify_rejects_malformed_output_instead_of_accepting_it_silently() -> None:
    """Salida que no es una Classification (p.ej. un dict crudo) se rechaza con Validation."""
    chat_model = _FakeChatModel(result={"categoria": "x"})
    with pytest.raises(Validation):
        await classify("texto cualquiera", chat_model)


async def test_classify_rejects_none_output() -> None:
    """Salida None (p.ej. el fake no configurado) también se rechaza, no se acepta como válida."""
    chat_model = _FakeChatModel(result=None)
    with pytest.raises(Validation):
        await classify("texto cualquiera", chat_model)


async def test_classify_sends_the_llm_real_instructions_not_just_the_raw_ticket_text() -> None:
    """Antes de este fix, `classify()` mandaba el texto del ticket TAL CUAL como único prompt -- el LLM
    adivinaba qué significan `categoria`/`dominio`/`prioridad`/`resoluble` sin ninguna guía (reproducido
    en vivo: un ticket sobre "no puedo eliminar una página, está siendo usada en un navigation" salía
    `resoluble=False` pese a que el dominio SÍ se identificaba bien y la KB documenta el caso). El
    prompt real debe explicar qué es cada campo."""
    chat_model = _FakeChatModel(
        result=Classification(
            categoria="incidencia",
            dominio=KbDomain.navigation_and_menus,
            prioridad=TicketPriority.normal,
            resoluble=True,
        )
    )
    await classify("no puedo eliminar una página", chat_model)

    sent = chat_model.received_text
    assert sent is not None
    assert "resoluble" in sent.lower()
    assert "dominio" in sent.lower()


async def test_classify_prompt_criteria_favor_resoluble_true_for_product_error_messages() -> None:
    """El criterio de `resoluble` debe orientarse a "podría responderse con documentación", no a "el
    modelo ya sabe la respuesta" -- un mensaje de error del producto es justo el caso que el clasificador
    infravaloraba antes del fix."""
    chat_model = _FakeChatModel(
        result=Classification(
            categoria="incidencia",
            dominio=KbDomain.navigation_and_menus,
            prioridad=TicketPriority.normal,
            resoluble=True,
        )
    )
    await classify("un mensaje de error del producto", chat_model)

    assert "resoluble" in (chat_model.received_text or "").lower()
    assert "error" in (chat_model.received_text or "").lower()


async def test_classify_prompt_still_contains_the_verbatim_ticket_text() -> None:
    """Las instrucciones no deben sustituir el texto del ticket -- debe seguir viajando íntegro (y en
    una sección delimitada, RN-3 de CU-BE-06: nunca como instrucción del sistema)."""
    chat_model = _FakeChatModel(
        result=Classification(
            categoria="x", dominio=None, prioridad=TicketPriority.normal, resoluble=True
        )
    )
    ticket_text = "un texto de ticket muy específico y reconocible XYZ123"
    await classify(ticket_text, chat_model)

    assert ticket_text in (chat_model.received_text or "")
