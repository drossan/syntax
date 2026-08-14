"""app.domain.services.ticket_service — ciclo de vida del ticket.

GUIÓN (→ tarea 10)
------------------
Qué implementar (reglas puras sobre ``TicketRepository`` + ``clock`` + auditoría):
  - **Alta**: crear ticket (estado inicial ``new``); el primer mensaje del solicitante es ``public``.
  - **Máquina de estados** (03 ``ticket_status``): transiciones válidas entre
    ``new → open → pending → resolved → closed`` y ``resolved/closed → reopened → open``. Rechazar
    transiciones inválidas (→ 409 en el router 11). Registrar cada transición en ``AuditLog``.
  - **Asignación**: set/clear ``assignee_id`` (capacidad ``ticket.assign``).
  - **Clasificación**: aplicar ``domain``/``priority`` que fija el clasificador (05/`classification.py`).
  - **SLA**: derivar ``sla_due`` de ``priority`` al crear/reabrir (política de 18); el vencimiento/escalado
    lo computa el scheduler (18), aquí solo se modelan ``priority``+``sla_due``.
  - **CSAT**: registrar ``csat`` (1–5) al resolver/cerrar.

**Camino feliz (A1.1)**: cuando ``approval_service`` aprueba/edita un draft, ESTE servicio ejecuta la
transición del ticket asociada (p.ej. → ``pending``/``resolved``) coordinado con la emisión del
``Message(public)``.

Anti-patrón: transiciones sin validar la máquina de estados; mutar estado sin auditar; importar infra.
"""
