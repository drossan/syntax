"""app.infra.llm.openai_adapter — adaptador OpenAI de los puertos LLM/embeddings.

GUIÓN (→ tarea 09)
------------------
Único adaptador concreto en Fase 1 (seam: el puerto permite otros; Anthropic queda fuera de alcance).

Qué implementar:
  - ``OpenAIChatModel`` (implementa ``ChatModel``) sobre ``langchain-openai`` (``ChatOpenAI``). Modelo de
    ``settings.CHAT_MODEL`` (default en ``.env.example`` = ``gpt-4o-mini``; ajustable por entorno — NO
    hardcodear). ``classify`` delega en ``structured.py`` (``with_structured_output``).
  - ``OpenAIEmbeddingModel`` (implementa ``EmbeddingModel``) sobre ``OpenAIEmbeddings`` con
    ``settings.EMBEDDING_MODEL`` → ``vector(settings.EMBEDDING_DIM)``.
  - **Instanciación perezosa**: los clientes se crean al usarse (o vía factory con ``get_settings()``),
    NUNCA en import; la ``OPENAI_API_KEY`` se lee de config, no se valida/crea en import.
  - **Conmutable por env**: ``settings.LLM_PROVIDER`` (default ``openai``) selecciona el adaptador; una
    factory (``get_chat_model()``/``get_embedding_model()``) lo resuelve. (Añadido ``LLM_PROVIDER`` a
    ``.env.example``.)

⚠️ Resiliencia (refuerzo A1.4): **timeout + retry con backoff** y manejo de **429 / caída** del proveedor.
Si el fallo ocurre a mitad del grafo, se propaga como ``AgentRun.failed`` (03) con ``error`` y un mensaje
controlado al usuario — nunca una excepción cruda ni un ticket en estado inconsistente.

Anti-patrón: crear el cliente OpenAI en import; hardcodear modelo/clave; que un 429 tumbe la request sin
retry/estado controlado.
"""
