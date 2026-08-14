"""app.infra.db.seed — seeds/fixtures idempotentes (entry-point ``python -m app.infra.db.seed``).

GUIÓN (→ tarea 17; objetivo de ``make seed``)
---------------------------------------------
Datos semilla para **ejercer login→ticket→draft→aprobación a mano** sin insertar datos manualmente
(gap real: con RLS+roles+tenants no hay forma de arrancar sin seeds).

Qué sembrar (idempotente, **upsert**; re-ejecutar no duplica):
  - **Capacidades + roles semilla** (rbac 02): las 14 capacidades y los 6 roles de sistema
    (support_admin/agent/viewer, client_admin/agent/viewer) con su matriz rol×capacidad.
  - **Tenants**: el tenant-sistema ``syntax`` + un tenant cliente demo.
  - **Usuarios**: **uno por rol** (6) con password de dev (Argon2); estado ``active``.
  - **Tickets de ejemplo** en varios estados/prioridades/dominios + algunos ``Message`` (``public`` e
    ``internal``); opcional un ``AgentRun``/``ApprovalTask`` de muestra para ver la cola HITL.
  - **KB de muestra**: unos ``KBChunk``/``Embedding`` (o invocar ``make ingest`` sobre un subconjunto) para
    que el RAG devuelva algo.

**RLS**: al insertar filas de negocio, fijar el contexto (``SET app.tenant_id``) por tenant (respeta las
políticas 08). Idempotencia por claves naturales (slug de tenant, email de usuario, uc_id de KB, name de rol).

Estructura: ``if __name__ == "__main__": raise SystemExit(main())`` para ``python -m app.infra.db.seed``.
Anti-patrón: datos de producción; seeds no idempotentes; saltarse RLS insertando sin contexto de tenant.
"""
