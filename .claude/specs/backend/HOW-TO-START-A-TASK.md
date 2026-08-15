# Cómo arrancar una sesión nueva para una tarea — `backend`

> Package **`backend`** de Syntax: **FastAPI + LangChain/LangGraph/LangSmith + Postgres/pgvector**.
> La fase de **esqueleto doc-only** (plan `skeleton-foundation`) está **completada**: existen los ficheros
> con su guión + specs + scaffolding. A partir de aquí el package **implementa código real con TDD**
> (`stack.packages.backend`: `pytest` + `cosmic-ray`, activado 2026-08-14). Flujo canónico:
> `docs/guides/task-lifecycle.md`. El **qué/cómo/por qué** de cada tarea sale de la capa SDD: `spec.md`
> (EARS) · `casos-de-uso/CU-BE-*` (Gherkin) · ADR.

> ## ⛔ PRECONDICIÓN dura (antes de la primera tarea TDD)
>
> El backend **aún no ejecuta**: `requirements.txt` es **stub** y las deps (`langgraph`/`langchain`/…)
> **no están instaladas** (no verificado que compile). Antes de escribir el primer test:
> 1. **Compilar el lockfile** (`requirements.in` → `requirements.txt`, pip-tools) e **instalar** en el venv.
> 2. **Pinar y verificar** el surface real de LangGraph/LangChain (`interrupt()`/`Command(resume=)`/
>    `with_structured_output`) contra el paquete instalado — las specs (`agent-graph.md`) lo marcan como pendiente.
> 3. `docker compose up` (Postgres+pgvector) y `.env` (OpenAI + LangSmith).
>
> Orden y detalle: `backend/IMPLEMENTATION-GUIDE.md`. **Sin esto, `make test` no corre.**

> ## 🚦 GATE TDD — IMPERATIVO, NO NEGOCIABLE (preset `full`)
>
> 1. La tarea está en `.claude/tasks/active/backend/<task-id>.md` con `status: active` y **todas** sus
>    `depends_on` en `done`. Si no → **PARAR y avisar**.
> 2. Estamos en la rama `plan/backend/<name-plan>` (nunca integración ni `main`). Solo **una** tarea `active` por plan.
> 3. **Test rojo ANTES de la implementación** (Red). Los tests salen **1:1 del `## Scenarios`** de la
>    tarea, que con SDD **enlaza** a su `casos-de-uso/CU-BE-*.md` (cada `Then` es un assert). Niveles por artefacto:
>
>    | Artefacto | Nivel de test |
>    |---|---|
>    | Servicio / lógica de dominio | **unit** con **mocks de puertos** (sin infra) |
>    | Repos / routers-endpoints | **integración** contra Postgres+pgvector en Docker |
>    | Adapters (LLM / embeddings / storage) | **suite de contrato** del puerto |
>    | **RLS** (aislamiento tenant) y **HITL / checkpointer** | **integración OBLIGATORIA** (footgun `SET app.tenant_id` en pool async; resume tras reinicio del proceso) |
>
>    Flujo IA end-to-end (`classify→retrieve→grade→generate→HITL`) → integración; e2e fuera del gate por tarea.
> 4. Green (mínimo para pasar) → Refactor. **Arquitectura hexagonal**: `api → domain ← infra`; el
>    **dominio no importa infra**; puertos (interfaces) en `domain/ports`, adaptadores en `infra/`;
>    Pydantic v2; handlers `async`; **settings inyectables** (sin efectos en import); **cero secretos en código**.
> 5. Cierre — **toda** la DoD: `make test` (pytest) verde · **ruff + mypy strict** · **gate de mutation
>    `cosmic-ray` (`break: 80`)** sobre los ficheros tocados (survivor por debajo = assert/escenario que falta) ·
>    documentación en tres capas (docstrings + doc técnica/specs/ADR + session log).
> 6. **Gate `/sdd-lint`** (SDD): valida los artefactos (spec EARS · CU Gherkin · ADR MADR) — tras `mutation`,
>    antes de `fact-checker`; un ERROR bloquea.
> 7. **Gate `fact-checker`** (no-negociable): tras mutation/sdd-lint y antes de commit/resumen. `INCORRECTO`
>    bloquea; `NO VERIFICABLE` = aviso a reconocer; `VERIFICADO` pasa.

## Prompt de arranque (copia y pega)

```
Voy a ejecutar la tarea <task-id> del plan <name-plan> (backend, CÓDIGO REAL, TDD).

Lee en este orden y repórtame en 3-4 líneas el plan que vas a seguir:
1. `.claude/specs/backend/HOW-TO-START-A-TASK.md` (este fichero) — incl. la PRECONDICIÓN dura.
2. `docs/guides/task-lifecycle.md` (flujo canónico).
3. `.claude/plans/active/backend/<name-plan>.md` (contexto, objetivos, orden, dependencias).
4. Las specs aplicables + el caso de uso enlazado (tabla abajo): `spec.md` + `casos-de-uso/CU-BE-*`.
5. `.claude/tasks/active/backend/<task-id>.md` + `.claude/context/backend/<task-id>.md`.

Ejecuta con el ciclo TDD. REGLAS ESTRICTAS:
- GATE TDD: status active + depends_on done; rama del plan; test rojo ANTES (1:1 desde el CU enlazado).
- Hexagonal (dominio no importa infra); RLS y HITL con integración OBLIGATORIA; mypy strict + ruff; cero secretos.
- Commits `<task-id>: <conventional commit>` en la rama del plan.
Al terminar: `make test` verde + ruff/mypy + gate cosmic-ray(break:80) + `/sdd-lint` + `fact-checker`;
docs 3 capas; cerrar session log; mover task a completed/ + `[x]` en el plan; siguiente tarea.
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
| Cualquier test (transversal) | `.claude/specs/general/testing.md` |
| Cualquier código (transversal) | `.claude/specs/general/coding-standards.md` |
| Decisiones de arquitectura (por qué) | `.claude/specs/adr/adr-index.md` (MADR) |

> **SDD activo** (`features.sdd: true`). Con código real, el `## Scenarios (Gherkin)` de una tarea **nueva**
> **enlaza** a su caso de uso (`casos-de-uso/CU-BE-*.md`) en vez de copiar escenarios. Las tareas doc-only ya
> completadas **no** se migran. Al cierre corre el gate **`/sdd-lint`** (valida spec EARS · CU Gherkin · ADR MADR).

## Reglas anti-context-bloat

- `grep -n` en vez de leer ficheros completos; delegar barridos amplios a `Explore`.
- No re-leer un fichero recién editado solo para verificar.
