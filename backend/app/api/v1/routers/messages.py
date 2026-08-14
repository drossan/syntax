"""app.api.v1.routers.messages — mensajes y adjuntos (contrato 06).

GUIÓN (→ tarea 11)
------------------
Endpoints (delegan en ``ticket_service``/servicios de 10 + puerto storage):
  - ``GET /tickets/{id}/messages`` (hilo, orden ``created_at asc``; los ``internal`` solo a sujetos con
    ``note.internal.read`` — filtro de visibilidad server-side).
  - ``POST /tickets/{id}/messages`` (``public`` requiere ``ticket.reply``; ``internal`` requiere
    ``note.internal.write``).
  - ``POST /messages/{id}/attachments`` (multipart; puerto storage, binario fuera de Postgres).

Anti-patrón: renderizar/servir mensajes ``internal`` a quien no tiene la capacidad; lógica en el router.
"""
