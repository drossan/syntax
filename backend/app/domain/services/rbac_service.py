"""app.domain.services.rbac_service — autorización (materializa rbac.md 02).

GUIÓN (→ tarea 10)
------------------
Qué implementar (sobre ``RoleRepository``/capacidades + contexto de tenant):
  - **``authorize(subject, capability, scope, resource) -> Allow | Deny``**: decide por
    **capacidad + ámbito**, **nunca por el nombre del rol** (02 §7). ``resource`` aporta el
    ``tenant_id``/dueño para validar el ámbito (p.ej. ``ticket.reply`` en ``scope=tenant`` solo aplica a
    tickets de ESE tenant).
  - **Capacidades server-side por request** (A1.7): resueltas desde BD, no del JWT (un cambio/revocación
    surte efecto en la siguiente request).
  - **Fail-closed**: sujeto sin rol → **deny-all**; si no se pueden resolver capacidades → denegar todo
    (nunca abrir por defecto).
  - **Roles custom por tenant** (02 §4): componer roles desde el catálogo con invariantes: no conceder
    ámbito ``global``; no conceder una capacidad que el propio sujeto no posee; tenant-scoped; roles
    ``system`` inmutables.
  - Deny → HTTP 403 con envelope estándar (lo traduce el router 11/12).

Anti-patrón: autorizar por nombre de rol; leer permisos del token; ampliar permisos por defecto.
"""
