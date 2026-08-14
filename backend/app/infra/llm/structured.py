"""app.infra.llm.structured — helper de salida estructurada (structured output).

GUIÓN (→ tarea 09; lo consume el clasificador de 05)
----------------------------------------------------
Envuelve ``ChatModel.with_structured_output(schema)`` (LangChain) para forzar salida **tipada** (Pydantic)
en vez de parsear strings. Lo usa el nodo ``classify`` del grafo (05):
``Classification{ categoria, dominio (1-de-17), prioridad, resoluble }``.

Qué implementar:
  - ``structured(chat_model, schema: type[BaseModel]) -> Runnable`` que devuelve instancias validadas del
    ``schema``; reintento/validación si el modelo no cumple el esquema.

⚠️ Nota de conformidad de API (igual que agent-graph 05): ``with_structured_output`` es la API **objetivo**
de LangChain; las deps LLM aún **no están instaladas/compiladas** → el nombre/firma exactos se **pinan y
verifican al implementar** (05/15). No verificado contra paquete instalado.

Anti-patrón: parsear la clasificación desde texto libre; devolver dicts sin validar contra el schema.
"""
