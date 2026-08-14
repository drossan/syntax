# Syntax — Backend · Guión maestro de implementación

> **Qué es esto.** El backend de este repo es, hoy, un **esqueleto doc-only**: la estructura de ficheros
> completa, un **guión por fichero** (docstring que dice *qué* implementar) y las **specs** que fijan los
> contratos. **No hay código de negocio todavía** — lo construye a mano el owner (práctica de
> LangChain/LangGraph/LangSmith). Esta guía es el **punto de entrada**: en qué orden construir, cómo
> levantar el entorno, cómo encaja cada pieza y qué gates/avisos respetar.
>
> Cada fichero `.py` del esqueleto lleva su GUIÓN. Las decisiones canónicas viven en las **specs**
> (`.claude/specs/`); el ciclo de trabajo, en `docs/guides/task-lifecycle.md`.

## 1. Mapa de specs (fuente de verdad)

| Spec | Fija |
|---|---|
| `.claude/specs/backend/rbac.md` (02) | Capacidades + ámbito, roles semilla + custom por tenant, visibilidad `public\|internal`, `authorize()`. |
| `.claude/specs/backend/data-model.md` (03) | 18 entidades, enums, ERD, marca RLS, cascadas/retención, `vector(N)` desde config. |
| `.claude/specs/backend/rag-ingestion.md` (04) | Parsing (frontmatter+Trazabilidad), chunking **H2 tolerante**, categorización, upsert idempotente, retrieval+confianza. |
| `.claude/specs/backend/agent-graph.md` (05) | Grafo plano + edges tipados, clasificación structured-output, **HITL** interrupt→checkpoint→resume, LangSmith. |
| `.claude/specs/general/api-contract.yaml` (06) | **Contrato OpenAPI 3.1** (fuente única). `api-contract.md` = companion. |

## 2. Orden de build recomendado

Sigue las dependencias (`depends_on` de cada tarea). Bloques (dentro de un bloque se puede paralelizar):

1. **Tooling + specs** (ya hechos): `01` scaffold/tooling · `02`–`06` specs. El contrato `06` es la
   dependencia dura cross-plan (el frontend deriva de él).
2. **Cimientos**: `07` core (`app/core/{config,security,logging,deps}.py` + `app/main.py`) →
   `08` capa DB (`app/infra/db/*` + `alembic/` + RLS) · `09` puerto LLM (`app/infra/llm/*`,
   `app/infra/langsmith/tracing.py`). `08` y `09` cuelgan de `07`.
3. **Dominio**: `10` servicios + puertos (`app/domain/services/*`, `app/domain/ports/*`). Depende de
   data-model + puertos, **no** de routers.
4. **API**: `11` routers core · `12` routers flujo-IA (`app/api/v1/routers/*` + `schemas/`). Contra el
   contrato `06`; delegan en `10`.
5. **RAG**: `13` ingestión (`app/ingestion/*`) · `14` retriever (`app/rag/*`). Cuelgan de `04/08/09`.
6. **Agente**: `15` definición del grafo (`app/agents/{state,graph,tools}.py`, `nodes/*`) → `16`
   checkpointer + HITL (`app/agents/{checkpointer,hitl,runner}.py`). `16` es **el núcleo de riesgo**.
7. **Arranque de datos y SLA**: `17` seeds (`app/infra/db/seed.py`) · `18` scheduler SLA
   (`app/workers/sla_scheduler.py`).

## 3. Cómo levantar el entorno

Todos los comandos desde `backend/` (ver `Makefile` y `.env.example`).

```bash
cp .env.example .env          # rellena secretos (JWT_SECRET, OPENAI_API_KEY, …). NUNCA comitees .env
make install                  # pip-tools: compila e instala requirements*.in → requirements*.txt
docker compose up -d db       # Postgres + pgvector (healthcheck en docker-compose.yml)
make migrate                  # alembic upgrade head — crea tablas + extensión vector + POLÍTICAS RLS (08)
make ingest                   # python -m app.ingestion — puebla KBDocument/Chunk/Embedding (13)
make seed                     # python -m app.infra.db.seed — tenants/roles/usuarios/tickets/KB demo (17)
make run                      # uvicorn app.main:app --reload — API en :8000 (07)
```

- **Variables clave** (`.env.example`): `DATABASE_URL` (asyncpg), `JWT_*`, `LLM_PROVIDER`,
  `OPENAI_API_KEY`, `CHAT_MODEL`, `EMBEDDING_MODEL`, `EMBEDDING_DIM` (=1536), `LANGSMITH_*`, límites B.1.
- **LangSmith**: `LANGSMITH_TRACING=true` + `LANGSMITH_API_KEY` para trazar los runs del grafo (09). Con
  tracing off, el backend funciona igual (degradación limpia).
- **Scheduler de SLA** (18): se lanza como proceso/target aparte (worker acotado solo a SLA); intervalo
  configurable. Definir su arranque al implementar (target `make` o servicio en docker-compose).
- **Calidad**: `make lint` (ruff), `make typecheck` (mypy strict), `make test` (pytest — cuando exista
  código real; hoy doc-only).

## 4. Cómo encaja cada pieza (arquitectura hexagonal)

```
HTTP → app.api.v1.routers ──delegan──▶ app.domain.services ──usan──▶ app.domain.ports (interfaces)
          (schemas 06)         │                                          ▲
          deps: auth+tenant+   │                                          │ implementan
          require_capability   │                                app.infra.{db,llm,vector,langsmith}
          (app.core.deps)      │
                               └── flujo-IA (ai-draft/approvals) ──▶ app.agents.runner
                                        │
   app.agents.graph (plano, edges tipados)                app.rag (retriever/confidence/citations)
   classify→retrieve→grade→generate→decide→[auto|HITL]→respond          ▲
        │            │                                                   │ usa
        │            └───────── retrieve usa ─────────────────────────────┘
        └── HITL (app.agents.hitl): interrupt → PostgresSaver (thread_id=ticket_{id}_run_{n})
                → endpoint approvals (12) → Command(resume) → Message(public) + transición ticket
```

- **Regla de oro**: `app.domain` **no importa** `app.infra` ni `app.api`. La dirección de dependencias
  no se invierte (verificado en el esqueleto).
- **Ciclo HITL end-to-end** (el corazón del producto): `POST /tickets/{id}/ai-draft` → `runner.run` →
  grafo hasta `interrupt` → `ApprovalTask(pending)` → cola `GET /approvals` → `POST /approvals/{id}/
  {approve|edit|reject}` → `runner.resume` (`Command(resume=)`) → `Message(visibility=public)` +
  transición del ticket (A1.1). `auto_approve=false` por defecto.

## 5. Gate manual: "OpenAPI generado ⊇ contrato"

El contrato `api-contract.yaml` (06) es la fuente única. Al implementar los routers (11/12), el
`/openapi.json` que **genera FastAPI** debe **cubrir** (⊇) ese contrato: mismos paths, métodos, códigos y
schemas (puede añadir, no quitar/renombrar). Compararlos es un **gate manual** antes de dar por buenos los
routers. El frontend (`frontend-…-02`) hace su propio gate: genera tipos + valida los mocks MSW contra el
`.yaml`. (No hay `openapi-spec-validator` instalado → considerar añadirlo al lockfile para un gate formal.)

## 6. Avisos de riesgo consolidados

1. **RLS footgun** (`app/infra/db/session.py`): `SET app.tenant_id` en un pool asyncpg **reutiliza
   conexiones** → fuga cross-tenant si no se resetea. Usar `SET LOCAL` transaccional o `RESET` en checkin;
   aislamiento primario **app-level** en los repos. **Exige tests de integración contra Postgres real** (un
   mock no lo caza).
2. **HITL / checkpointer** (`app/agents/{checkpointer,hitl}.py`): el estado vive **solo** en el checkpoint
   Postgres → reanudar tras reinicio; doble decisión = **409 idempotente** (resume una sola vez);
   `thread_id=ticket_{id}_run_{n}` (run nuevo por reapertura, no reutilizar checkpoint obsoleto).
3. **Dimensión del vector** (`EMBEDDING_DIM`): cambiarla obliga a **re-embeber todo el corpus** + migrar
   `vector(N)` + reconstruir el índice pgvector. No es cambio en caliente.
4. **Prompt-injection** (`app/agents/nodes/{classify,generate}.py`): el contenido del ticket es **input no
   confiable** → aislarlo del system-prompt, no ejecutar instrucciones embebidas; riesgo máximo con
   `auto_approve=true`.
5. **Fallo del LLM a mitad de run** → `AgentRun.failed` + `error`, checkpoint consistente, error controlado
   al usuario; timeout/retry/backoff + 429 en el adaptador (09).
6. **Conformidad de API LangGraph/LangChain**: el `requirements.txt` es un stub (deps sin compilar); las
   APIs objetivo (`interrupt()`, `with_structured_output`, `PostgresSaver`, `add_messages`,
   `trim_messages`, `@tool`) se **pinan/verifican al implementar** (las demos usan variantes antiguas).

## 7. Checklist de "esqueleto seguible"

- [x] Layout hexagonal completo (`app/{api,core,domain,infra,agents,rag,ingestion,workers}`), 79 módulos
  con guión.
- [x] Specs coherentes entre sí (02–06) y con la KB real (17 dominios · 268 UC · 218 draft/50 active).
- [x] Contrato OpenAPI 3.1 machine-readable (`api-contract.yaml`, 32 paths / 38 schemas, `$ref` resueltos).
- [x] Tooling que valida: `docker compose config` OK; `pyproject`/ruff/mypy strict; `compileall` de todo `app/`.
- [x] `Makefile` con `install/migrate/ingest/seed/run/lint/typecheck/test`.
- [x] Seeds que habilitan ejercer **login→ticket→draft→aprobación** sin datos a mano.
- [x] `/health` con split liveness/readiness (comprueba DB + pgvector).
- [ ] *(al implementar)* Tests de integración RLS + HITL; gate OpenAPI ⊇ contrato; compilar el lockfile.

## 8. Referencias

- Specs: `.claude/specs/backend/` y `.claude/specs/general/`.
- Plan y tareas: `.claude/plans/completed/backend/skeleton-foundation.md`,
  `.claude/tasks/completed/backend/backend-skeleton-foundation-*.md`.
- Ciclo de trabajo: `docs/guides/task-lifecycle.md`. Documentación del proyecto: `docs/`.
