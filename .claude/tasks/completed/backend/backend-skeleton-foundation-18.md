---
id: backend-skeleton-foundation-18
package: backend
plan: skeleton-foundation
status: done
priority: 3
depends_on: [backend-skeleton-foundation-03, backend-skeleton-foundation-10]
estimate: 2h
actual: 0.3h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# Skeleton scheduler de SLA (B.2 promovido)

## Description

Esqueleto de `app/workers/sla_scheduler.py`: un **scheduler mínimo** que revisa periódicamente los
tickets con `sla_due` vencido/inminente y **notifica/escala**. Promovido desde scenario-coverage (B.2).
Reintroduce un worker **acotado solo a SLA** (no colas generales). Solo esqueleto + guión.

## Spec

- Job periódico (APScheduler / arq / loop asyncio) que consulta tickets **no resueltos** con
  `sla_due <= now` (o dentro de umbral de aviso), **por tenant** (respeta RLS / `SET app.tenant_id`).
- Acción al vencer: crear `Notification` (in-app) y **escalar** (bump de `priority` / reasignar según regla);
  registrar en `AuditLog`.
- **Idempotencia**: marca `sla_breached_at`/estado para **no notificar dos veces** el mismo breach.
- Config del intervalo; cómo se lanza (target `make` / servicio opcional en docker-compose).
- Usa `ticket_service`/`notification_service` (10); no implementa política de horario laboral (diferida).

## Fuera de alcance

- Política/horario laboral completo de SLA; email (entrega diferida, stub); colas/workers generales
  (este scheduler es **solo** para SLA); tiempo real. Implementar la lógica (solo esqueleto + guión).

## Scenarios (Gherkin)

<!-- Doc-only. -->
**Verificación (doc-only):**
- El scheduler consulta tickets no resueltos con `sla_due` vencido/inminente, por tenant, respetando RLS.
- Al vencer genera Notification + escalado y lo audita; es **idempotente** (no re-notifica el mismo breach).
- El guión indica intervalo configurable y cómo lanzarlo; delega en servicios de dominio (10).

## Provides

- `app/workers/sla_scheduler.py` + guión + target de arranque. Cierra el hueco B.2 (SLA sin cómputo).

## Definition of Done

- [x] Scheduler creado con guión (`app/workers/sla_scheduler.py` + `__init__`): consulta, escalado, notificación, auditoría, idempotencia. `compileall` OK.
- [x] Respeta tenancy/RLS (`SET app.tenant_id`, iterar tenants); intervalo configurable; delega en 10; no re-notifica el mismo breach (`sla_breached_at`).
- [x] `Provides` disponible para las dependientes (cierra B.2; worker acotado solo a SLA).
- [x] Gate de `fact-checker` superado (sonnet): 6/6 VERIFICADO.
- [x] Histórico en `.claude/context/backend/backend-skeleton-foundation-18.md`.
