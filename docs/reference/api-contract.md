# Referencia · Contrato de API

**Fuente canónica:** `.claude/specs/general/api-contract.yaml` (OpenAPI 3.1, machine-readable) +
`api-contract.md` (companion). Es la **única fuente de verdad** de la superficie HTTP; el backend
implementa contra él y el frontend deriva tipos + mocks.

## Formato

- **OpenAPI 3.1** (YAML), 32 paths / 38 schemas. El backend (routers) debe generar un `/openapi.json`
  que sea **⊇** al contrato (gate manual "OpenAPI generado ⊇ contrato").
- **Base**: `/api/v1`.

## Convenciones

- **Auth**: access **Bearer** (memoria, TTL corto) + refresh en **cookie httpOnly** (rotación +
  reuse-detection). Endpoints `login/refresh/logout/me` + `password/{forgot,reset,change}`.
- **Autorización**: por capacidad + ámbito (server-side). Deny → **403** con envelope.
- **Envelope de error** (`problem+json`, RFC 9457): `{type, title, status, detail, errors[]}`.
  `title`/`detail` localizables por `Accept-Language`.
- **Paginación**: `page` + `page_size` → `{items, page, page_size, total}`.
- **Orden determinista** por listado: tickets `-updated_at`; `/approvals` `sla_due,confidence`;
  `/notifications` `-created_at`; `/kb/search` `score`.

## Áreas de endpoints

| Área | Endpoints (resumen) |
|---|---|
| Auth | `/auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/me`, `/auth/password/*` |
| Tickets | `GET/POST /tickets`, `GET/PATCH /tickets/{id}`, `/transition`, `/assign` |
| Mensajes | `GET/POST /tickets/{id}/messages`, `POST /messages/{id}/attachments` |
| Flujo-IA | `POST /tickets/{id}/ai-draft`, `GET /agent-runs/{id}`, `GET /approvals`, `/approvals/{id}/{approve,edit,reject}` |
| KB | `GET /kb/search`, `GET /kb/documents`, `/kb/documents/{uc_id}` |
| Admin | `/admin/tenants`, `/admin/users`, `/admin/roles`, `/admin/capabilities`, `/admin/settings` |
| Analytics / Notifs | `GET /analytics/summary`, `GET /notifications`, `PATCH /notifications/{id}/read` |

## Idempotencia del HITL

`POST /approvals/{id}/{approve,edit,reject}` es idempotente: decidir una tarea ya no-`pending` es no-op;
en carrera, la segunda decisión recibe **409** (el grafo se reanuda una sola vez).
