# Syntax

Helpdesk con IA generativa para el producto **Syntax**. Objetivo: mejorar la experiencia del
usuario y la eficiencia del equipo de soporte respondiendo con IA (RAG sobre la documentación) bajo
**aprobación humana**, con gestión de tickets real y **multi-tenant** (cliente = dominio).

## Método de trabajo

**Spec-Driven Design + TDD**, orquestado por el plugin `task-pipeline`. La referencia canónica del
flujo (estados, ramas, gates, DoD, checkpoints) es **`docs/guides/task-lifecycle.md`** — respétala.

@.claude/honesty-rules.md

## Paquetes

| Package | Qué es | Cómo se trabaja |
|---|---|---|
| `frontend/` | Next.js 16 (App Router) + TS estricto + Tailwind v4 + shadcn/ui | **Código real, TDD**. Ver `.claude/specs/frontend/HOW-TO-START-A-TASK.md`. |
| `backend/` | FastAPI + LangChain/LangGraph/LangSmith + Postgres/pgvector | **Esqueleto doc-only** (ficheros + guión + specs, sin código de negocio) en esta fase. Ver `.claude/specs/backend/HOW-TO-START-A-TASK.md`. |

Front y back se encuentran en el **contrato de API compartido**:
`.claude/specs/general/api-contract.md` (lo define el backend, lo consume el frontend vía mocks MSW).

## Config del pipeline

`.claude/task-pipeline.yml` → `mode: full`, `stack: typescript/pnpm/vitest/stryker` (el único
package que corre tests aquí es `frontend`; `backend` es doc-only). Los checkpoints humanos
(`grilling`, aprobación del plan) no se saltan.

## Estructura de trabajo (convención task-pipeline)

- Planes: `.claude/plans/<estado>/<package>/<name-plan>.md`
- Tareas: `.claude/tasks/<estado>/<package>/<task-id>.md` (`<task-id> = <package>-<name-plan>-<nn>`)
- Session logs: `.claude/context/<package>/<task-id>.md`
- Specs: `.claude/specs/<package>/` y `.claude/specs/general/`
