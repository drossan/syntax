"""app.api.v1.routers.tickets — endpoints de tickets (contrato 06).

GUIÓN (→ tarea 11)
------------------
Endpoints (delegan en ``ticket_service`` de 10; deps auth+tenant+``require_capability``):
  - ``GET /tickets`` (lista; orden por defecto ``-updated_at``; filtros ``status/priority/domain/assignee_id``;
    paginación estable), ``POST /tickets`` (``ticket.create``).
  - ``GET /tickets/{id}`` (``ticket.read``), ``PATCH /tickets/{id}`` (campos editables).
  - ``POST /tickets/{id}/transition`` (``ticket.transition``; 409 si transición inválida),
    ``POST /tickets/{id}/assign`` (``ticket.assign``).

Aislamiento: RLS + filtro app-level; recurso fuera del tenant → 404. Errores problem+json.
Anti-patrón: máquina de estados en el router (vive en ``ticket_service``).
"""
