"""app.api.v1.routers — routers FastAPI (core = tarea 11, flujo-IA = tarea 12).

GUIÓN
-----
Cada router traduce HTTP ↔ dominio: valida con schemas Pydantic (``app.api.v1.schemas``, derivados del
contrato 06), aplica las dependencias de ``app.core.deps`` (auth + ``require_capability``; y **contexto de
tenant salvo en recursos globales** — KB y ``admin_tenants`` son cross-tenant/globales por diseño),
delega en un **servicio de ``app.domain``** (o en el **retriever de ``app.rag``** para ``kb``, tarea 14) y
devuelve el envelope del contrato (incl. problem+json en error). **Sin lógica de negocio en el router.**

CORE (tarea 11): ``auth``, ``tickets``, ``messages``, ``admin_tenants``, ``admin_users``, ``admin_roles``, ``kb``.
FLUJO-IA (tarea 12): ``agent``, ``approvals``, ``notifications``, ``analytics``.

``create_app()`` (07) monta cada ``APIRouter`` bajo ``/api/v1``. El OpenAPI generado debe ser ⊇ al
contrato (gate en 19).
"""
