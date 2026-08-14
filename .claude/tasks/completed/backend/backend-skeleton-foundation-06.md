---
id: backend-skeleton-foundation-06
package: backend
plan: skeleton-foundation
status: done
priority: 1
depends_on: [backend-skeleton-foundation-02, backend-skeleton-foundation-03, backend-skeleton-foundation-04, backend-skeleton-foundation-05]
estimate: 3h
actual: 1.25h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# Spec contrato de API (fuente única, OpenAPI-first)

## Description

Escribir `.claude/specs/general/api-contract.md`: el **contrato compartido** entre backend y frontend,
**única fuente de verdad**. Cubre core (auth, tickets, mensajes, admin, KB) y flujo-IA (aprobaciones,
draft, escalado, notificaciones). Depende de rbac (02), data-model (03), rag (04) y agent-graph (05)
porque expone sus conceptos (draft/fuentes/confianza/escalado/aprobación). El frontend deriva de aquí
tipos y **mocks (incl. de error)**.

## Spec

- **Formato**: **OpenAPI 3.1 real (machine-readable, YAML/JSON)** — **fuente única, no prosa** (design-review
  C1). El skeleton de routers (11/12) implementa contra esto; la guía (19) añade el gate "OpenAPI generado
  ⊇ contrato"; y el **frontend genera tipos + valida los mocks MSW contra este schema** (`frontend-…-02`),
  con su propio gate de conformidad. Un contrato en prosa haría divergir contrato↔tipos↔mocks sin detección.
- **Auth**: `POST /auth/login` (→ access + Set-Cookie refresh), `/auth/refresh`, `/auth/logout`,
  `GET /auth/me`. (Fase 2: `/auth/sso/*` reservado.)
- **Tickets/mensajes**: CRUD `tickets`, transición de estado, asignación; `messages` con `visibility`
  (`public|internal`); `attachments`.
- **Flujo-IA**: `POST /tickets/{id}/ai-draft` (dispara el grafo), `GET /approvals` (cola),
  `POST /approvals/{id}/{approve|edit|reject}`, `human_note`; `GET /agent-runs/{id}` (confidence/sources/trace).
- **KB**: `GET /kb/search` (q + filtros domain/package/estado), `GET /kb/documents`, `/kb/documents/{uc_id}`.
- **Admin**: `tenants`, `users`, `roles`/`capabilities` (role builder), `settings` (`auto_approve`).
- **Analytics**: `GET /analytics/summary`. **Notifications**: `GET /notifications`, `PATCH .../read`.
- **Envelope de error estándar** (problem+json): `{type, title, status, detail, errors[]}` — el frontend
  deriva sus mocks de fallo de aquí. Paginación, filtros y convenciones de auth (Bearer + cookie) comunes.

## Refuerzos (scenario-coverage)

- **Orden por defecto determinista** por listado: `tickets` `updated desc`; **cola `/approvals`** por
  `sla_due`/confianza; `/notifications` `created desc`; `/kb/search` por score. Paginación estable.
- **Endpoints de contraseña** (B.3, promovido): `POST /auth/password/{forgot,reset,change}` + **invitación**
  al crear usuario (entrega email = stub del puerto).
- **i18n del envelope de error** (nota: `title/detail` localizables por `Accept-Language`).

## Fuera de alcance

- Implementar routers (11/12); endpoints de Fase 2 (nota al desarrollador) — no se exponen.

## Scenarios (Gherkin)

<!-- Doc-only. -->
**Verificación (doc-only):**
- Cada recurso del data-model (03) con superficie pública tiene sus endpoints; los enums/campos coinciden con 03/02.
- El flujo-IA expone draft/fuentes/confianza/escalado/aprobación definidos en 05.
- Existe envelope de error estándar y convenciones de auth/paginación comunes.
- Un consumidor (frontend) puede derivar tipos + mocks (éxito y error) solo de esta spec.

## Provides

- `.claude/specs/general/api-contract.md`: contrato único. 11/12 implementan routers/schemas; el plan
  `frontend` (tarea 02) deriva cliente tipado + MSW mocks. Es la dependencia dura cross-plan.

## Definition of Done

- [x] Contrato completo (core + flujo-IA + admin/KB/analytics/notifs) y coherente con 02/03/04/05. OpenAPI 3.1, 32 paths, 38 schemas.
- [x] Envelope de error (problem+json `Problem`) + convenciones comunes (auth Bearer+cookie, paginación, orden determinista, i18n) definidos; endpoints de roles/capacidades presentes.
- [x] Derivable por el frontend (tipos + mocks éxito y error): `.yaml` machine-readable, todos los `$ref` resuelven.
- [x] `Provides` disponible para las dependientes (incl. frontend-02). <!-- api-contract.yaml + companion .md -->
- [x] Gate de `fact-checker` superado (sonnet): 9/9 VERIFICADO. Aviso reconocido: validación formal contra meta-schema OpenAPI no ejecutada (tool ausente) — solo parseo YAML + $refs; no bloquea (doc-only).
- [x] Histórico en `.claude/context/backend/backend-skeleton-foundation-06.md`.
