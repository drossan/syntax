---
id: backend-skeleton-foundation-16
package: backend
plan: skeleton-foundation
status: done
priority: 3
depends_on: [backend-skeleton-foundation-15, backend-skeleton-foundation-08]
estimate: 3h
actual: 0.6h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# Skeleton grafo de agentes — checkpointer + HITL

## Description

Esqueleto de la parte de **persistencia y aprobación humana** del grafo: checkpointer Postgres + el ciclo
`interrupt → endpoint de aprobación → resume`. **Es el núcleo de riesgo del producto** (aprobación
asíncrona), así que el guión debe ser exhaustivo. Solo esqueleto + guión.

## Spec

- `app/agents/checkpointer.py` — guión de `PostgresSaver` (`langgraph-checkpoint-postgres`), `thread_id`=ticket,
  compartición del pool/engine (08).
- `app/agents/hitl.py` — guión del ciclo: `interrupt` antes de `respond`; el estado queda checkpointeado;
  el endpoint de aprobación (12) inyecta la decisión y hace `resume`. Documentar explícitamente:
  - **reanudar tras reinicio del servidor** a mitad de run (reconstruir desde el checkpoint por `thread_id`);
  - **ediciones concurrentes** del estado (bloqueo/optimistic, quién gana);
  - **mapeo `interrupt ↔ ApprovalTask`** (03) y el caso `auto_approve=true`.
- `app/agents/runner.py` — guión de `run(ticket)` / `resume(ticket, decision)` que usan los servicios (10) y LangSmith (09).

## Refuerzos (scenario-coverage)

- Al hacer `resume`, **persistir el draft aprobado/editado** como `Message(public)` + **transición del ticket** (A1.1, con 10).
- **Idempotencia de doble decisión**: guard si la `ApprovalTask` ya está en estado terminal (approved/rejected).
- **Run-por-reapertura**: `thread_id` con secuencia; no reutilizar un checkpoint obsoleto (A1.2).

## Fuera de alcance

- Streaming SSE del draft (seam `astream`). Implementar la lógica real. Nota al desarrollador (Fase 2).

## Scenarios (Gherkin)

<!-- Doc-only. -->
**Verificación (doc-only):**
- El guión describe `PostgresSaver` con `thread_id`=ticket y el ciclo interrupt→endpoint→resume.
- Cubre explícitamente reinicio a mitad de run, ediciones concurrentes y el mapeo interrupt↔ApprovalTask.
- `runner` expone `run`/`resume` integrados con approval_service (10) y tracing (09).

## Provides

- `app/agents/{checkpointer,hitl,runner}.py`. 12 (`approvals`/`ai-draft`) invoca `run`/`resume`; cierra el flujo HITL end-to-end.

## Definition of Done

- [x] Checkpointer (PostgresSaver, thread_id=ticket_{id}_run_{n}) + HITL + runner (run/resume) creados con guión exhaustivo del ciclo asíncrono. `compileall` OK.
- [x] Reinicio a mitad de run (reanuda desde checkpoint), concurrencia/doble decisión (409 idempotente) y mapeo interrupt↔ApprovalTask + auto_approve documentados.
- [x] `Provides` disponible para las dependientes (12 invoca run/resume; cierra el HITL end-to-end).
- [x] Gate de `fact-checker` superado (sonnet): 8/8 VERIFICADO.
- [x] Histórico en `.claude/context/backend/backend-skeleton-foundation-16.md`.
