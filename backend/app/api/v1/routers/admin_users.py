"""app.api.v1.routers.admin_users — gestión/invitación de usuarios (contrato 06).

GUIÓN (→ tarea 11)
------------------
Endpoints (capacidad ``user.manage``; cliente acotado a su tenant; delegan en ``auth_service``/servicios 10):
  - ``GET /admin/users`` (lista del tenant), ``POST /admin/users`` (crear/invitar → estado ``invited`` +
    AuthToken invitación, email stub).
  - ``PATCH /admin/users/{id}`` (status —soft-delete=``disabled``—, roles).

Anti-patrón: gestionar usuarios de otro tenant sin ámbito ``global``; hard-borrar (usar ``status``).
"""
