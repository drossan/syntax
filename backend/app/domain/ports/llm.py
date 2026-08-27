"""app.domain.ports.llm — puerto `ChatModel` (tarea backend-agent-graph-04, agent-graph.md §4/§9).

`generate`/`grade` los añade el primer caller real: los nodos `grade`/`generate` del grafo del agente
(tarea 05, confianza híbrida de agent-graph.md §5). `EmbeddingModel` sigue sin nacer aquí (sin caller en
este plan).

``app.infra.llm`` implementa este puerto contra un proveedor concreto (OpenAI); el dominio nunca importa
su SDK — solo habla con `ChatModel`, proveedor conmutable sin tocar dominio.

Contrato: firmas en tipos de dominio / Pydantic v2. Anti-patrón: exponer tipos de ``langchain``/``openai``
en las firmas del puerto (acopla el dominio al proveedor).
"""

from typing import Protocol

from pydantic import BaseModel


class ChatModel(Protocol):
    """Puerto de chat/completion del LLM: clasificación y evaluación tipadas + generación de texto libre."""

    async def classify(self, text: str, schema: type[BaseModel]) -> BaseModel:
        """Clasificación tipada: el proveedor valida la salida contra `schema` (structured output).

        :raises app.domain.errors.PortError: si el proveedor falla (timeout, error de API).
        """
        ...

    async def grade(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
        """Evaluación tipada (relevancia/suficiencia del contexto recuperado) — mismo patrón de
        structured output que `classify`, reutilizable para cualquier salida tipada futura.

        :raises app.domain.errors.PortError: si el proveedor falla (timeout, error de API).
        """
        ...

    async def generate(self, prompt: str) -> str:
        """Generación de texto libre (el draft de respuesta), sin schema.

        :raises app.domain.errors.PortError: si el proveedor falla (timeout, error de API).
        """
        ...
