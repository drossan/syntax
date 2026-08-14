"""app.api.v1.routers.admin_roles — roles/capacidades + role builder (contrato 06).

GUIÓN (→ tarea 11)
------------------
Endpoints (capacidad ``role.manage``; delegan en ``rbac_service`` de 10):
  - ``GET /admin/capabilities`` (catálogo para el role builder).
  - ``GET /admin/roles`` (semilla del sistema + custom del tenant), ``POST /admin/roles`` (crear rol
    custom), ``PATCH/DELETE /admin/roles/{id}`` (roles ``system`` inmutables → 403/409).

Invariantes fail-closed (02 §4, validadas en el servicio): no capacidades de ámbito ``global``; no
conceder lo que el sujeto no posee; rol tenant-scoped. Anti-patrón: validar invariantes solo en el router.
"""
