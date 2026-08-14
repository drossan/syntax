---
id: backend-skeleton-foundation-12
package: backend
plan: skeleton-foundation
status: done
priority: 2
depends_on: [backend-skeleton-foundation-06, backend-skeleton-foundation-07, backend-skeleton-foundation-10]
estimate: 3h
actual: 0.5h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# Skeleton routers API — flujo-IA

## Description

Esqueleto de los routers FastAPI del **flujo-IA** + schemas según el contrato (06): disparar draft,
cola de aprobaciones, decisiones, notificaciones, dashboard. Es la superficie que el frontend más
necesita mockear (cola + draft con fuentes/confianza). Solo esqueleto + guión.

## Spec

- `app/api/v1/routers/agent.py` — `POST /tickets/{id}/ai-draft` (dispara el grafo, tarea 15/16),
  `GET /agent-runs/{id}` (confidence/sources/`langsmith_trace_url`).
- `app/api/v1/routers/approvals.py` — `GET /approvals` (cola), `POST /approvals/{id}/{approve|edit|reject}`,
  `human_note`; delega en `approval_service` (10) + HITL (16).
- `app/api/v1/routers/notifications.py` — `GET /notifications`, `PATCH .../read`.
- `app/api/v1/routers/analytics.py` — `GET /analytics/summary`.
- `schemas/` correspondientes (draft, sources, confidence, approval, notification, summary); envelope de error común.

## Refuerzos (scenario-coverage)

- **Rate-limit de `POST /tickets/{id}/ai-draft`** por usuario/tenant (B.1) — cada disparo cuesta llamadas LLM.
- Cola `GET /approvals` con **orden por `sla_due`/confianza** (06); manejo de `AgentRun.failed` (error IA) en la respuesta.

## Fuera de alcance

- Routers core (auth/tickets/admin/kb) → tarea 11. Implementar lógica; endpoints Fase 2 (nota al desarrollador).

## Scenarios (Gherkin)

<!-- Doc-only. -->
**Verificación (doc-only):**
- Los endpoints de flujo-IA de 06 (draft/approvals/agent-runs/notifs/analytics) tienen ruta+schema.
- La respuesta de draft/agent-run expone fuentes+confianza+trace según 05; la cola expone `human_note`.
- Delegación a `approval_service`/grafo; auth+tenant+autorización aplicados; sin lógica en el router.

## Provides

- `app/api/v1/routers/{agent,approvals,notifications,analytics}.py` + schemas. Completa (con 11) la
  superficie del contrato para que el frontend mockee login→ticket→draft→aprobación.

## Definition of Done

- [x] Routers flujo-IA (agent/approvals/notifications/analytics) creados según 06, con guión y deps auth/tenant/autorización. `compileall` OK.
- [x] Draft/agent-run exponen sources+confidence+`langsmith_trace_url`+status(failed); cola orden `sla_due,confidence` con `human_note`; delegación a `approval_service`/HITL (16); 409 doble decisión; rate-limit ai-draft (B.1).
- [x] `Provides` disponible para las dependientes (completa la superficie del contrato con 11).
- [x] Gate de `fact-checker` superado (sonnet): 6/6 VERIFICADO.
- [x] Histórico en `.claude/context/backend/backend-skeleton-foundation-12.md`.
