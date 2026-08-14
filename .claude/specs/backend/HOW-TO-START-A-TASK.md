# Cómo arrancar una sesión nueva para una tarea — `backend`

> Package **`backend`** de Syntax: **FastAPI + LangChain/LangGraph/LangSmith +
> Postgres/pgvector**. En esta fase el package es **esqueleto doc-only**: se producen **ficheros
> con su guión** (docstring/comentario que explica qué implementar), **specs** y **scaffolding**
> (docker-compose, Alembic, pyproject) — **NO código de negocio ejecutable**. El usuario implementará
> el código a mano después. Flujo canónico: `docs/guides/task-lifecycle.md`.

> ## 🚦 GATE (doc-only — el TDD estándar NO aplica a estas tareas)
>
> Estas tareas usan el **escape hatch** de la plantilla (`features.tdd` no aplica: "sin código
> testeable → justifica cómo se verifica"). **No** hay Red→Green→Refactor ni gate de mutation.
>
> **Antes de empezar:**
> 1. La tarea está en `.claude/tasks/active/backend/<task-id>.md` con `status: active` y **todas**
>    sus `depends_on` en `done`. Si no → **PARAR y avisar**.
> 2. Estamos en la rama `plan/backend/<name-plan>`. Solo **una** tarea `active` por plan.
>
> **Verificación de una tarea backend (en vez de tests):**
> - **Estructura**: los ficheros/carpetas existen donde el plan dice, con nombres correctos.
> - **Guión por fichero**: cada fichero de esqueleto lleva su bloque-guía — **propósito**, **qué
>   implementar**, **contrato/firma esperada**, **dependencias** (qué importa / qué lo consume),
>   **pasos** y **anti-patrones**. Un fichero de esqueleto sin guión = tarea incompleta.
> - **Specs completas y coherentes**: las specs (rbac, data-model, api-contract, rag-ingestion,
>   agent-graph) están escritas, sin contradicciones entre sí, y verificables por bullets.
> - **Scaffolding válido** donde aplique: `pyproject.toml` parsea; `docker-compose config` valida;
>   el layout de Alembic es correcto. (Los stubs Python que se dejen **deben importar/typechear** si
>   se ejecuta `python -c` o `mypy`, pero **no** implementan lógica.)
>
> **Arquitectura del esqueleto** (hexagonal): dependencia `api → domain ← infra`; el **dominio no
> importa infra**; puertos (interfaces) en `domain/ports`, adaptadores en `infra/`; Pydantic v2;
> handlers `async`; config por entorno (nunca secretos en código). El **guión** de cada fichero debe
> respetar y explicitar esta dirección de dependencias.
>
> **Gate `fact-checker`** (no-negociable) al cierre: no afirmes "la estructura compila / el guión está
> completo" sin haberlo comprobado en la sesión.

## Prompt de arranque (copia y pega)

```
Voy a ejecutar la tarea <task-id> del plan <name-plan> (backend, ESQUELETO doc-only).

Lee en este orden y repórtame en 3-4 líneas el plan que vas a seguir:
1. `.claude/specs/backend/HOW-TO-START-A-TASK.md` (este fichero).
2. `docs/guides/task-lifecycle.md` (flujo canónico).
3. `.claude/plans/active/backend/<name-plan>.md` (contexto, objetivos, orden, dependencias).
4. Las specs aplicables en `.claude/specs/backend/` (ver tabla abajo).
5. `.claude/tasks/active/backend/<task-id>.md` + `.claude/context/backend/<task-id>.md`.

Esta tarea produce ESQUELETO + GUIÓN + SPECS, NO código de negocio. NO escribas implementación.
REGLAS: dependencias hexagonales (dominio no importa infra); cada fichero de esqueleto lleva su
guión (propósito/qué implementar/contrato/dependencias/pasos); specs coherentes; scaffolding que
valida. Commits `<task-id>: <conventional commit>` en la rama del plan.
Al terminar: verificar estructura + guiones + `docker-compose config`/`pyproject` donde aplique;
`fact-checker`; cerrar session log; mover task a completed/ + `[x]` en el plan; siguiente tarea.
```

## Specs aplicables

| Si la tarea crea / toca… | Lee la spec |
|---|---|
| **Toda tarea (SDD)** | `.claude/specs/backend/spec.md` (requisitos EARS) + `.claude/specs/backend/casos-de-uso/` (Gherkin, **único hogar**) |
| Roles / permisos / aislamiento tenant | `.claude/specs/backend/rbac.md` |
| Modelos / entidades / migraciones | `.claude/specs/backend/data-model.md` |
| Routers / schemas / endpoints | `.claude/specs/general/api-contract.md` |
| Ingestión / chunking / pgvector / retriever | `.claude/specs/backend/rag-ingestion.md` |
| Grafo LangGraph / HITL / fases / LangSmith | `.claude/specs/backend/agent-graph.md` |
| Cualquier código (transversal) | `.claude/specs/general/coding-standards.md` |
| Decisiones de arquitectura (por qué) | `.claude/specs/adr/adr-index.md` (MADR) |

> **SDD activo** (`features.sdd: true`). Con código real, el `## Scenarios (Gherkin)` de una tarea **nueva**
> **enlaza** a su caso de uso (`casos-de-uso/CU-BE-*.md`) en vez de copiar escenarios. Las tareas doc-only ya
> completadas **no** se migran. Al cierre corre el gate **`/sdd-lint`** (valida spec EARS · CU Gherkin · ADR MADR).

> **Cuando implementes el backend real** (Python + pytest), este package pasará a TDD: ajusta
> `.claude/task-pipeline.yml` (`stack` a python/pytest y su herramienta de mutation) y endurece
> este HOW-TO con los niveles de test por artefacto (dominio → unit con mocks de puertos; repos/
> endpoints → integración contra Postgres+pgvector en Docker; adapters → suite de contrato).

## Reglas anti-context-bloat

- `grep -n` en vez de leer ficheros completos; delegar barridos amplios a `Explore`.
- No re-leer un fichero recién editado solo para verificar.
