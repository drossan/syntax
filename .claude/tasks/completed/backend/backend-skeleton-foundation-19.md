---
id: backend-skeleton-foundation-19
package: backend
plan: skeleton-foundation
status: done
priority: 3
depends_on: [backend-skeleton-foundation-01, backend-skeleton-foundation-02, backend-skeleton-foundation-03, backend-skeleton-foundation-04, backend-skeleton-foundation-05, backend-skeleton-foundation-06, backend-skeleton-foundation-07, backend-skeleton-foundation-08, backend-skeleton-foundation-09, backend-skeleton-foundation-10, backend-skeleton-foundation-11, backend-skeleton-foundation-12, backend-skeleton-foundation-13, backend-skeleton-foundation-14, backend-skeleton-foundation-15, backend-skeleton-foundation-16, backend-skeleton-foundation-17, backend-skeleton-foundation-18]
estimate: 2h
actual: 0.5h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# Guión maestro de implementación (IMPLEMENTATION-GUIDE.md)

## Description

Escribir `backend/IMPLEMENTATION-GUIDE.md`: el **guión maestro** que ata todo. Es el entregable clave
para el owner: en qué **orden** construir de verdad, cómo **levantar** el entorno, cómo **encaja** cada
pieza, y los **gates** manuales. Consolida los guiones por fichero de todas las tareas.

## Spec

- **Orden de build recomendado** (specs → core/DB → LLM → dominio → routers → ingestión/RAG → grafo →
  seeds → scheduler SLA), con dependencias y qué se puede paralelizar.
- **Cómo levantar**: `docker-compose up db`, migraciones Alembic, `make ingest`, `make seed`, `make run`;
  variables de `.env`; activar LangSmith; lanzar el scheduler de SLA.
- **Cómo encaja cada pieza**: mapa API↔servicios↔dominio↔infra↔grafo↔RAG; el ciclo HITL end-to-end
  (incl. draft aprobado → `Message(public)` + transición).
- **Gate manual "OpenAPI generado ⊇ contrato"**: comparar el OpenAPI que FastAPI genera con el contrato (06).
- **Avisos de riesgo** consolidados: footgun RLS (`SET app.tenant_id` + tests de integración), HITL/
  checkpointer (resume tras reinicio), dimensión vector (coste re-embed), prompt-injection, fallo LLM.
- Checklist final de "esqueleto seguible": estructura + guiones + specs + `docker-compose config` + seeds.

## Fuera de alcance

- Implementar el código (el guión describe cómo hacerlo, no lo hace).

## Scenarios (Gherkin)

<!-- Doc-only. -->
**Verificación (doc-only):**
- La guía cubre orden de build (incl. scheduler SLA), cómo levantar, cómo encaja cada pieza y los gates/avisos.
- Referencia correctamente cada spec/tarea (rutas válidas) y el gate de conformidad OpenAPI.
- Un dev puede seguirla para implementar el backend sin releer todo el plan.

## Provides

- `backend/IMPLEMENTATION-GUIDE.md`: el punto de entrada para construir el backend real. Cierra el plan.

## Definition of Done

- [x] Guía creada (`backend/IMPLEMENTATION-GUIDE.md`) con orden de build, arranque, mapa hexagonal, gate OpenAPI y 6 avisos de riesgo consolidados.
- [x] Referencias a specs/tareas/ficheros válidas (verificadas); checklist de "esqueleto seguible".
- [x] Gate de `fact-checker` superado (sonnet): 8/8 VERIFICADO.
- [x] Histórico en `.claude/context/backend/backend-skeleton-foundation-19.md`.
