"""app.domain — núcleo de negocio: entidades, servicios y PUERTOS.

GUIÓN (→ tarea 10: servicios de dominio + ports)
------------------------------------------------
El corazón hexagonal. **No importa ``app.infra`` ni ``app.api``** (ni SQLAlchemy, ni FastAPI,
ni clientes LLM): solo tipos propios y Pydantic v2. La infraestructura implementa estos
puertos; la API los orquesta.

Qué implementar aquí:
  - Entidades/valores de dominio (ticket, message, user, tenant, role, capability, agent-run…).
  - Servicios de dominio: ticket, approval (HITL), rbac (``authorize()``), notification,
    classification. Reglas de negocio puras, testeables con mocks de puertos.
  - Puertos (interfaces ``Protocol``/ABC): repositorios, puerto LLM, puerto de embeddings,
    puerto de notificación, puerto de vector store. Los adaptadores viven en ``app.infra``.

Contrato: los servicios reciben sus puertos por inyección (constructor/deps), nunca instancian
adaptadores concretos. Anti-patrón: importar infra desde aquí (rompe la hexagonalidad).
"""
