"""app.domain.ports.repositories — interfaces de repositorio (puertos).

GUIÓN (→ tarea 08)
------------------
Un puerto (``Protocol``/ABC) por agregado de 03. Firmas en tipos de dominio (no SQLAlchemy). Todas las
operaciones son **async**. El aislamiento multi-tenant es responsabilidad del adaptador (filtra por el
``tenant_id`` del contexto); el puerto NO recibe el tenant como parámetro suelto (lo aporta el contexto).

Puertos a definir (métodos típicos ``get/list/add/update`` + los específicos):
  - ``TicketRepository``   → get/list (filtros+orden determinista de 06), add, transition, assign.
  - ``MessageRepository``  → list_by_ticket (orden created_at), add (respeta visibility public|internal).
  - ``ApprovalRepository`` → get, list_pending (cola), decide (idempotente: no-op si ya no-pending).
  - ``AgentRunRepository`` → get, add, update_status (incl. ``failed``), next_run_seq(ticket).
  - ``UserRepository`` / ``TenantRepository`` / ``RoleRepository`` (+ capabilities) → gestión + resolución
    de capacidades efectivas del sujeto (server-side, A1.7).
  - ``RefreshSessionRepository`` → rotación + reuse-detection (revocar familia) + logout.
  - ``NotificationRepository`` → list (orden created desc), mark_read.
  - ``KBRepository`` → upsert_document (idempotente por uc_id), reconciliación de huérfanos, get_by_uc_id.

Contrato: los servicios de dominio (10) dependen de estas interfaces; los adaptadores SQLAlchemy viven en
``app.infra.db.repositories`` (08). Anti-patrón: filtrar tenant en la capa de servicio en vez del repo;
tipos de infra en las firmas.
"""
