"""app.infra — adaptadores de infraestructura (driven).

Implementaciones concretas de los puertos definidos en ``app.domain``: persistencia,
almacén de vectores, LLM/embeddings y tracing. **Depende del dominio, nunca al revés.**

Subpaquetes:
  - ``db``        → Postgres/SQLAlchemy async, Alembic, RLS            · tarea 08
  - ``vector``    → adaptador pgvector (almacén de embeddings)         · tareas 13, 14
  - ``llm``       → puerto LLM + adaptador OpenAI + embeddings         · tarea 09
  - ``langsmith`` → tracing/observabilidad de LangSmith               · tarea 09
"""
