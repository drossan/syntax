"""app.api.v1.routers.notifications — notificaciones in-app (contrato 06).

GUIÓN (→ tarea 12)
------------------
Endpoints (delegan en ``notification_service`` 10):
  - ``GET /notifications`` → las del usuario; orden ``created_at desc``; filtro ``unread``; paginación.
  - ``PATCH /notifications/{id}/read`` → marca leída (``read_at``).

Fase 1: in-app + polling (sin push/SSE). Anti-patrón: exponer notificaciones de otro usuario/tenant.
"""
