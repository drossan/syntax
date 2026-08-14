"""app.domain.services.notification_service — notificaciones in-app.

GUIÓN (→ tarea 10)
------------------
Qué implementar (sobre ``NotificationRepository``):
  - **Emitir** notificaciones (03 ``notification_type``): ``approval_requested`` (draft pendiente para
    Soporte), ``ticket_assigned``, ``ticket_reply``, ``sla_warning``/``sla_breach`` (del scheduler 18).
  - **Listar** las del usuario (orden `created_at desc`, 06) y **marcar leídas** (``read_at``).
  - Fase 1: **in-app + polling** (``GET /notifications``). Push/email/webhooks **diferidos** (fuera de
    alcance); el ``email`` port existe solo para reset/invitación (stub).

Anti-patrón: acoplar a un canal externo (email/push) en Fase 1; que fallar una notificación bloquee la
acción de negocio que la disparó (best-effort).
"""
