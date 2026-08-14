---
id: backend-skeleton-foundation-10
package: backend
plan: skeleton-foundation
status: done
priority: 2
depends_on: [backend-skeleton-foundation-03, backend-skeleton-foundation-07]
estimate: 3h
actual: 1h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# Skeleton servicios de dominio + ports

## Description

Esqueleto de `app/domain/` (servicios + puertos) para la lógica de negocio: tickets, aprobaciones, RBAC,
notificaciones, clasificación. **Depende de data-model (03) y de los puertos, NO de los routers**
(hexagonal: el dominio es el centro). Solo esqueleto + guión.

## Spec

- `app/domain/services/ticket_service.py` — guión: alta/transición de estado (máquina new/open/pending/
  resolved/closed/reopened), asignación, tags/dominio, SLA (`priority`+`sla_due`), auditoría.
- `app/domain/services/approval_service.py` — guión: cola de aprobación, `auto_approve` por tenant
  (default false), aprobar/editar/rechazar, `human_note`, integración con el HITL del grafo (16).
- `app/domain/services/rbac_service.py` — guión: `authorize(subject, capability, scope, resource)` según
  rbac (02); roles custom por tenant.
- `app/domain/services/notification_service.py` — guión: notificaciones in-app persistidas (+ polling).
- `app/domain/services/classification.py` — guión: contrato del clasificador (structured output) que
  fija `Ticket.domain/priority` (consume 05/09).
- `app/domain/ports/` — interfaces que estos servicios requieren (repos, llm, vector, storage, clock).

## Refuerzos (scenario-coverage)

- **Camino feliz completo (A1.1)**: el **draft aprobado/editado** se materializa como
  `Message(visibility=public, author=IA/agente)` + **transición del ticket** (via `approval_service` +
  `ticket_service`). Este eslabón "draft aprobado → mensaje visible al cliente" es de esta tarea (con 16).
- **Password reset / invitación** service (B.3) + **puerto email** (stub, entrega diferida).
- **Límite de disparos de `ai-draft`** por usuario/tenant (B.1) — política en el servicio, aplicada en 12.

## Fuera de alcance

- Implementar la lógica (solo esqueleto + guión). Email (entrega)/canned responses/CSAT UI (diferidos).

## Scenarios (Gherkin)

<!-- Doc-only. -->
**Verificación (doc-only):**
- Los servicios dependen de puertos e entidades (03), no de FastAPI/routers (dirección hexagonal correcta).
- La máquina de estados del ticket y el flujo de aprobación (default require-human) están documentados.
- `rbac_service.authorize` decide por capacidad+ámbito (no por nombre de rol).

## Provides

- `app/domain/services/*` + `app/domain/ports/*`. 11/12 (routers) invocan estos servicios; 16 (HITL) usa `approval_service`.

## Definition of Done

- [x] 6 servicios (ticket/approval/rbac/notification/classification/auth) + `__init__` + 4 puertos (vector/storage/email/clock) creados con guión; hexagonal respetado (0 imports de infra/FastAPI, verificado). `compileall` OK.
- [x] Máquina de estados de ticket (6 estados de 03), aprobación (default `auto_approve=false`, eslabón draft→Message(public) A1.1) y `authorize` (capacidad+ámbito, deny-all) documentados.
- [x] `Provides` disponible para las dependientes (11/12 routers invocan servicios; 16 usa approval_service).
- [x] Gate de `fact-checker` superado (sonnet): 8/8 VERIFICADO.
- [x] Histórico en `.claude/context/backend/backend-skeleton-foundation-10.md`.
