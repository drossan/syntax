"""app.domain.ports.llm — puertos de LLM y embeddings.

GUIÓN (→ tarea 09)
------------------
Interfaces (``Protocol``/ABC) que el dominio/grafo consumen; los adaptadores concretos viven en
``app.infra.llm``. El negocio habla con estos puertos, NUNCA con el SDK de un proveedor → proveedor
conmutable sin tocar dominio.

  - ``ChatModel`` (async):
      - ``generate(messages, ...) -> str`` — redacción del draft (nodo generate de 05).
      - ``grade(...) -> Grade`` — relevancia/suficiencia del contexto (confianza híbrida, 04/05).
      - ``classify(text, schema) -> BaseModel`` — clasificación tipada (structured output; ver
        ``structured.py``): ``{categoria, dominio 1-de-17, prioridad, resoluble}``.
  - ``EmbeddingModel`` (async):
      - ``embed_documents(list[str]) -> list[vector]`` / ``embed_query(str) -> vector``.
      - Dimensión = ``settings.EMBEDDING_DIM`` (fuente de ``vector(N)``, 03/04); ``model`` identificable
        (para detectar mezclas de modelos).

Contrato: firmas en tipos de dominio / Pydantic v2. Anti-patrón: exponer tipos de ``langchain``/``openai``
en las firmas del puerto (acopla el dominio al proveedor).
"""
