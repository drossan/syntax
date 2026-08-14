---
id: backend-skeleton-foundation-11
package: backend
plan: skeleton-foundation
status: done
priority: 2
depends_on: [backend-skeleton-foundation-06, backend-skeleton-foundation-07, backend-skeleton-foundation-10]
estimate: 3h
actual: 0.75h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# Skeleton routers API — core

## Description

Esqueleto de los routers FastAPI **core** + schemas Pydantic según el contrato (06): auth, tickets,
mensajes, admin (tenants/usuarios/roles/capacidades), KB. Solo esqueleto + guión (firmas, deps de auth/
tenant, delegación a servicios de dominio), sin lógica.

## Spec

- `app/api/v1/routers/auth.py` — `login/refresh/logout/me` (emite JWT + cookie refresh; consume core/security).
- `app/api/v1/routers/tickets.py` + `messages.py` — CRUD, transición, asignación, `messages` con `visibility`, attachments.
- `app/api/v1/routers/admin_tenants.py`, `admin_users.py`, `admin_roles.py` — CRUD + role builder (capacidades→roles por tenant).
- `app/api/v1/routers/kb.py` — `search` (filtros) + `documents/{uc_id}` (delegан a retriever, tarea 14).
- `app/api/v1/schemas/` — DTOs de request/response derivados del contrato; **envelope de error** común.
- Cada endpoint: dependencia de **auth + contexto de tenant + autorización** (rbac_service) y delegación al servicio de dominio.

## Refuerzos (scenario-coverage)

- Endpoints **`POST /auth/password/{forgot,reset,change}`** + invitación al crear usuario (B.3); email = stub del puerto.
- Listados con **orden por defecto determinista** + paginación estable (según contrato 06).

## Fuera de alcance

- Routers de flujo-IA (aprobaciones/draft/notifs/dashboard) → tarea 12. Implementar lógica.

## Scenarios (Gherkin)

<!-- Doc-only. -->
**Verificación (doc-only):**
- Cada endpoint del contrato core (06) tiene su ruta+schema; los DTOs coinciden con el contrato.
- Todos aplican dependencia de auth+tenant+autorización y delegan a servicios de dominio (10), sin lógica embebida.
- El envelope de error común está referenciado.

## Provides

- `app/api/v1/routers/*` (core) + `schemas/*`. El frontend (vía contrato 06) mockea estos endpoints; 12 añade el flujo-IA.

## Definition of Done

- [x] Routers core (auth/tickets/messages/admin_tenants/admin_users/admin_roles/kb) + `schemas/__init__` creados según 06, con guión y deps auth/tenant/autorización. `compileall` OK.
- [x] Delegación a servicios (10) —y al retriever 14 para kb—; sin lógica en el router; envelope problem+json referenciado.
- [x] `Provides` disponible para las dependientes (frontend mockea vía 06; 12 añade flujo-IA).
- [x] Gate de `fact-checker` superado (sonnet): 6/7 VERIFICADO + I5 INCORRECTO (regla "siempre app.domain" demasiado absoluta: kb delega en app.rag) corregido en el guión y re-verificado.
- [x] Histórico en `.claude/context/backend/backend-skeleton-foundation-11.md`.
