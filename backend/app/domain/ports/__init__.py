"""app.domain.ports — puertos (interfaces) que la infraestructura implementa.

GUIÓN (→ tareas 08/09/10)
-------------------------
Interfaces (``Protocol``/ABC) que el dominio define y ``app.infra`` implementa (hexagonal). El dominio
NO importa infra; recibe estos puertos por inyección.

  - ``repositories.py`` (→ 08): puertos de repositorio por agregado (ticket, message, user, tenant, role/
    capability, approval, agent_run, notification, kb). Filtran por ``tenant_id`` del contexto.
  - (→ 09) puerto LLM (chat + structured output), puerto de embeddings, puerto de vector store (retrieval
    pgvector), puerto de notificación, puerto de storage (adjuntos), puerto de email (stub Fase 1).

Contrato: tipos de dominio / Pydantic v2 en las firmas, nunca modelos SQLAlchemy ni tipos de infra.
"""
