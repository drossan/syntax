"""app.api.v1.routers.approvals — cola HITL y decisiones (contrato 06).

GUIÓN (→ tarea 12)
------------------
Endpoints (capacidad ``approval.decide``, solo Soporte; delegan en ``approval_service`` 10 + HITL 16):
  - ``GET /approvals`` → cola de ``ApprovalTask`` pendientes; **orden ``sla_due, confidence``** (lo más
    urgente/menos confiable primero); expone ``draft_body``, ``confidence``, ``sources``, ``human_note``.
  - ``POST /approvals/{id}/approve`` → resume → ``Message(public)`` + transición del ticket (A1.1).
  - ``POST /approvals/{id}/edit`` (``final_body``) → resume con texto editado.
  - ``POST /approvals/{id}/reject`` (``human_note`` obligatorio) → resume sin mensaje público.

Idempotencia: decidir una tarea ya no-``pending`` = no-op; en carrera, la 2ª decisión → **409** (un solo
``resume`` sobre el thread). Anti-patrón: reanudar el grafo dos veces; emitir el mensaje público sin decisión.
"""
