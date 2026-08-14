# Contrato de API (compartido backend ↔ frontend)

> **La fuente única de verdad es [`api-contract.yaml`](./api-contract.yaml)** (OpenAPI 3.1,
> machine-readable). Este `.md` es un **companion**: convenciones y cómo consumirlo. Si algo aquí
> contradice el `.yaml`, **manda el `.yaml`**. Doc-only: define el contrato, no la implementación.

## Por qué OpenAPI-first (no prosa)

Un contrato en prosa haría divergir `contrato ↔ tipos ↔ mocks` sin detección (design-review C1). Con un
OpenAPI real:

- El **backend** (routers 11/12) implementa contra el schema; la guía maestra (19) añade el gate
  **"OpenAPI generado ⊇ contrato"** (el `/openapi.json` que emite FastAPI debe cubrir este contrato).
- El **frontend** (`frontend-…-02`) **genera el cliente tipado** y **valida los mocks MSW** (éxito y
  error) contra este `.yaml`, con su propio gate de conformidad.

## Coherencia con las specs del backend

Los enums y campos del `.yaml` se derivan literal de:

- **rbac (02)**: nombres de capacidades (`ticket.reply`, `approval.decide`, …), `scope` `tenant|global`,
  roles semilla, visibilidad `public|internal`, deny → **403**.
- **data-model (03)**: entidades y enums (`TicketStatus`, `TicketPriority`, `ApprovalStatus`,
  `AgentRunStatus`, `KBDomain` (17), `KBEstado`, `NotificationType`, `UserStatus`, …).
- **rag-ingestion (04)**: `/kb/search` con filtros `domain/package/estado` y orden por `score`; citas.
- **agent-graph (05)**: `ai-draft` → `AgentRun`; cola `/approvals`; `approve|edit|reject` con `resume`;
  `confidence`/`sources`/`langsmith_trace_url`; **409 en doble decisión** (idempotencia del HITL).

## Convenciones comunes

- **Base**: `/api/v1`.
- **Auth**: access token **Bearer** (memoria, TTL corto) + refresh en **cookie httpOnly** (rotación +
  reuse-detection). `/auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/me`; contraseña
  `forgot/reset/change`. SSO/OIDC **reservado Fase 2** (no expuesto).
- **Autorización**: por **capacidad + ámbito** resueltos server-side (nunca por nombre de rol). Deny →
  **403** con envelope; el cliente reconcilia sin mutar estado.
- **Envelope de error** (problem+json, RFC 9457): `{type, title, status, detail, errors[]}`.
  `title`/`detail` **localizables** por `Accept-Language`. El frontend deriva sus mocks de fallo de aquí.
- **Paginación**: `page` (≥1, default 1) + `page_size` (≤100, default 20); respuesta `{items, page,
  page_size, total}`.
- **Orden por defecto determinista**: `tickets` `-updated_at`; **`/approvals`** `sla_due, confidence`;
  `/notifications` `-created_at`; `/kb/search` `score desc`. Paginación estable.
- **Aislamiento multi-tenant**: transversal (app-level + RLS); un recurso fuera del tenant del sujeto
  responde **404** (no revela existencia).

## Fuera de alcance (no expuesto)

- Endpoints de **Fase 2** (nota al desarrollador / visibilidad `developer`).
- **Streaming SSE** del draft (seam `astream`, fase posterior): en Fase 1 el draft se obtiene por
  `GET /agent-runs/{id}` (polling).
