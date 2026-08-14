"""app.api.v1.routers.analytics — dashboard/resumen (contrato 06).

GUIÓN (→ tarea 12)
------------------
Endpoint (capacidad ``analytics.read``):
  - ``GET /analytics/summary`` → métricas agregadas del tenant (o cross-tenant si Soporte global):
    tickets por estado, aprobaciones pendientes, confianza media, breaches de SLA.

Aislamiento: agregados acotados al tenant salvo ámbito ``global``. Anti-patrón: filtrar en el cliente lo
que debe agregarse server-side; fugar métricas cross-tenant a un cliente.
"""
