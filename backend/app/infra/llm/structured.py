"""app.infra.llm.structured — helper de salida estructurada (structured output).

Helper interno del adaptador OpenAI (`app.infra.llm.openai_adapter`), NO parte del puerto de dominio
(`app.domain.ports.llm`): envuelve `ChatOpenAI.with_structured_output(schema, method="json_schema")`
(agent-graph.md §4) para que `classify`/`grade` compartan un único punto de mapeo a `PortError`.
"""

from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.domain.errors import PortError


async def structured_output(chat: ChatOpenAI, prompt: str, schema: type[BaseModel]) -> BaseModel:
    """Invoca `chat` forzando salida tipada contra `schema`, envolviendo cualquier fallo en `PortError`.

    Cubre tanto un fallo de transporte (timeout, error de API) como una salida que
    `with_structured_output` no logra mapear al `schema` pedido — ambos llegan aquí como una excepción
    del SDK; el mensaje original se conserva (`from exc`), así que siguen siendo distinguibles.

    :raises app.domain.errors.PortError: fallo del proveedor o salida no conforme al schema.
    """
    structured_chat = chat.with_structured_output(schema, method="json_schema")
    try:
        return await structured_chat.ainvoke(prompt)  # type: ignore[return-value]
    except PortError:
        raise
    except Exception as exc:
        raise PortError(
            f"fallo al obtener salida estructurada de {schema.__name__}: {exc}"
        ) from exc
