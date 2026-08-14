---
id: backend-skeleton-foundation-17
package: backend
plan: skeleton-foundation
status: done
priority: 3
depends_on: [backend-skeleton-foundation-08, backend-skeleton-foundation-09]
estimate: 2h
actual: 0.3h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# Skeleton seeds / fixtures

## Description

Esqueleto de `app/seeds/` (o `scripts/seed.py`): datos semilla idempotentes para que el owner pueda
**ejercer login→ticket→draft→aprobación a mano** sin insertar datos manualmente. Añadido en design-review
(gap real: con RLS+roles+tenants no hay forma de arrancar sin seeds). Solo esqueleto + guión.

## Spec

- Tenant-sistema `syntax` + un tenant cliente demo; usuarios: uno por rol (support_admin/agent/viewer,
  client_admin/agent/viewer) con password de dev; capacidades + roles semilla (rbac 02).
- Un puñado de tickets de ejemplo en varios estados/prioridades/dominios; algunos mensajes (`public`/`internal`).
- Chunks KB de muestra (o invocar `make ingest` sobre un subconjunto) para que el RAG devuelva algo.
- **Idempotente** (upsert): re-ejecutar no duplica. `make seed` lo invoca. Respetar RLS (`SET app.tenant_id`).

## Fuera de alcance

- Datos de producción; implementar la lógica real (solo esqueleto + guión).

## Scenarios (Gherkin)

<!-- Doc-only. -->
**Verificación (doc-only):**
- El seed cubre tenants + un usuario por rol + capacidades/roles + tickets/mensajes + chunks KB de muestra.
- Es idempotente (upsert) y respeta RLS; `make seed` está cableado.
- Tras el seed, el owner puede ejercer el flujo completo sin insertar datos a mano.

## Provides

- `app/seeds/*` + `make seed`. Habilita el ejercicio manual end-to-end del esqueleto y sirve de referencia de datos para 18.

## Definition of Done

- [x] Seeds idempotentes creados con guión en `app/infra/db/seed.py` (tenants syntax+demo/usuarios 1-por-rol/14 capacidades+6 roles/tickets+mensajes/KB muestra). `compileall` OK.
- [x] Respetan RLS (`SET app.tenant_id`); `make seed` cableado (`python -m app.infra.db.seed`); cubren un usuario por rol.
- [x] `Provides` disponible para las dependientes (habilita ejercicio manual end-to-end; referencia de datos para 18).
- [x] Gate de `fact-checker` superado (sonnet): 7/7 VERIFICADO.
- [x] Histórico en `.claude/context/backend/backend-skeleton-foundation-17.md`.
