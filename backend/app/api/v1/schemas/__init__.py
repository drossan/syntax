"""app.api.v1.schemas — DTOs Pydantic v2 de request/response (derivados del contrato 06).

GUIÓN (→ tareas 11 core y 12 flujo-IA)
--------------------------------------
Un schema por request/response de ``api-contract.yaml`` (06), **1:1 con el contrato** (mismos campos,
enums y envelope). Agrupar por recurso (auth, tickets, messages, admin, kb; y flujo-IA: agent/approvals/
notifications/analytics).

Piezas comunes:
  - ``Problem`` (envelope de error problem+json: ``type/title/status/detail/errors[]``).
  - ``Page`` (paginación: ``items/page/page_size/total``).
  - Enums reusados de 03/06 (TicketStatus, TicketPriority, MessageVisibility, ApprovalStatus,
    AgentRunStatus, KBDomain(17), KBEstado, NotificationType, …).

El OpenAPI que FastAPI genera de estos schemas debe ser ⊇ al contrato 06 (gate en 19). Anti-patrón:
DTOs que divergen del contrato; exponer modelos SQLAlchemy como response.
"""
