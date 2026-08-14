"""app.workers.sla_scheduler — vencimiento/escalado de SLA (B.2 promovido).

GUIÓN (→ tarea 18)
------------------
Scheduler **mínimo, acotado SOLO a SLA** (no colas generales). Job periódico (APScheduler / arq / loop
asyncio — elegir al implementar; intervalo configurable por env).

Qué implementar (delega en ``ticket_service``/``notification_service`` de 10 + puerto ``clock``):
  - Consulta tickets **no resueltos** con ``sla_due <= now`` (vencido) o dentro del **umbral de aviso**,
    **por tenant** (respeta RLS / ``SET app.tenant_id`` — iterar tenants, no una query cross-tenant ciega).
  - Al vencer: crear ``Notification`` (``sla_breach``/``sla_warning``, in-app) y **escalar** (bump de
    ``priority`` / reasignar según regla); registrar en ``AuditLog``.
  - **Idempotencia**: marca ``sla_breached_at``/estado para **no notificar dos veces** el mismo breach.
  - Cómo se lanza: target ``make`` / servicio opcional en docker-compose (documentar).

Fuera de alcance: horario laboral completo de SLA (diferido); email (stub); colas/workers generales.
Anti-patrón: query cross-tenant que se salte RLS; re-notificar el mismo breach; meter aquí lógica que
pertenece a ``ticket_service``.
"""
