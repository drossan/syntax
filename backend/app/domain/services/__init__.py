"""app.domain.services — servicios de dominio (lógica de negocio pura).

GUIÓN (→ tarea 10)
------------------
Los servicios orquestan reglas de negocio sobre **entidades de dominio** y **puertos** inyectados
(``app.domain.ports``); NO importan ``app.infra`` ni ``app.api`` (hexagonal). Testeables con mocks de
puertos. Los routers (11/12) los invocan; el HITL del grafo (16) usa ``approval_service``.

  - ``ticket_service``       → máquina de estados + asignación + SLA + auditoría.
  - ``approval_service``     → cola HITL, auto_approve por tenant, aprobar/editar/rechazar.
  - ``rbac_service``         → ``authorize(subject, capability, scope, resource)`` (02).
  - ``notification_service`` → notificaciones in-app.
  - ``classification``       → contrato del clasificador (structured output) que fija Ticket.domain/priority.
  - ``auth_service``         → password reset / invitación (B.3), rotación/reuse-detection del refresh.

Contrato: cada servicio recibe sus puertos por inyección (constructor/deps), nunca instancia adaptadores.
"""
