"""app.domain.ports.llm — puerto `ChatModel`, recortado a `classify` (tarea 06 del plan domain-services).

`generate`/`grade` son prematuros sin caller: los descubrirá la tarea 15 (nodo `generate` del grafo,
confianza híbrida) con su primer test — fijar su firma hoy sería adivinar un contrato sin consumidor.
`EmbeddingModel` tampoco nace aquí (sin caller en este plan).

GUIÓN (→ tarea 15, ampliación futura de este mismo puerto)
-----------------------------------------------------------
  - ``generate(messages, ...) -> str`` — redacción del draft (nodo generate de 05).
  - ``grade(...) -> Grade`` — relevancia/suficiencia del contexto (confianza híbrida, 04/05).

GUIÓN (→ tarea 09, adaptador real)
----------------------------------
``app.infra.llm`` implementará este puerto contra un proveedor concreto (OpenAI); el dominio nunca
importa su SDK — solo habla con `ChatModel`, proveedor conmutable sin tocar dominio.

Contrato: firmas en tipos de dominio / Pydantic v2. Anti-patrón: exponer tipos de ``langchain``/``openai``
en las firmas del puerto (acopla el dominio al proveedor).
"""

from typing import Protocol

from pydantic import BaseModel


class ChatModel(Protocol):
    """Puerto de chat/completion del LLM, recortado a `classify` (structured output)."""

    async def classify(self, text: str, schema: type[BaseModel]) -> BaseModel:
        """Clasificación tipada: el proveedor valida la salida contra `schema` (structured output).

        :raises app.domain.errors.PortError: si el proveedor falla (timeout, error de API).
        """
        ...
