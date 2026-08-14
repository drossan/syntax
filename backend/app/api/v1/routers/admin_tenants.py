"""app.api.v1.routers.admin_tenants — gestión de tenants (contrato 06).

GUIÓN (→ tarea 11)
------------------
Endpoints (capacidad ``tenant.manage``, solo Soporte/global; delegan en servicios de 10):
  - ``GET /admin/tenants`` (lista paginada), ``POST /admin/tenants`` (crear).
  - (patch/soft-disable por ``status`` según necesidad; hard-delete no — 03 §7 RESTRICT).

Anti-patrón: permitir gestión cross-tenant a un cliente; hard-borrar tenants.
"""
