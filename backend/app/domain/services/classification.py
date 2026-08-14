"""app.domain.services.classification — contrato del clasificador de tickets.

GUIÓN (→ tarea 10; consume el puerto LLM 09 y alimenta el grafo 05)
------------------------------------------------------------------
Qué implementar (sobre ``ChatModel.classify`` con structured output):
  - Schema Pydantic ``Classification{ categoria: str, dominio: KBDomain(1-de-17), prioridad:
    TicketPriority, resoluble: bool }`` (03 enums).
  - ``classify(ticket_text) -> Classification`` usando ``with_structured_output`` (no parseo de strings).
  - Fija ``Ticket.domain`` y ``Ticket.priority`` (via ``ticket_service``); el ``dominio`` **filtra el
    retrieval** (04/05).
  - **No clasificable con confianza** (dominio incierto) → fallback: baja confianza → el grafo recupera
    **sin filtro de dominio** (05); no forzar un dominio equivocado.

Anti-patrón: clasificar por reglas/regex frágiles o parseando prosa del LLM; forzar 1-de-17 cuando la
confianza es baja.
"""
