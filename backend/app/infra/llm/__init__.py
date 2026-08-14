"""app.infra.llm — puerto LLM + adaptador OpenAI + embeddings.

GUIÓN (→ tarea 09)
------------------
Define el **puerto LLM** (interface en ``app.domain``, adaptador aquí) y provee UN adaptador
concreto: OpenAI (chat vía ``langchain-openai``, con ``with_structured_output`` para la
clasificación tipada) + embeddings (``EMBEDDING_MODEL`` → ``vector(EMBEDDING_DIM)``).

Contrato: el dominio y el grafo hablan con el puerto, no con OpenAI directamente → proveedor
**conmutable** sin tocar negocio. Modelos y claves llegan por config (``.env``), nunca
hardcodeados. Anti-patrón: acoplar el grafo/agente al SDK de un proveedor concreto.
"""
