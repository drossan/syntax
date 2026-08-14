"""app.api.v1 — routers y schemas de la API v1.

GUIÓN
-----
CORE (→ tarea 11): auth, tickets, messages, admin (tenants/usuarios/roles), kb.
FLUJO-IA (→ tarea 12): approvals, disparar draft, fuentes/confianza, escalado,
notificaciones, dashboard.

Cada router: schemas Pydantic v2 request/response alineados 1:1 con el contrato, dependencias
de auth + capacidades (RBAC server-side, ver `.claude/specs/backend/rbac.md`) y el envelope de
error uniforme. Sin lógica de negocio: delega en los servicios de ``app.domain``.
"""
