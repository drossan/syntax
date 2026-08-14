# Syntax — Backend

Backend del helpdesk con IA generativa de **Syntax**: FastAPI (async) + LangChain/LangGraph/LangSmith
+ Postgres/pgvector. Multi-tenant (cliente = dominio), RAG sobre la documentación de Syntax con
**aprobación humana** (HITL) del draft generado.

> **Estado: esqueleto doc-only.** Este package está en fase de **estructura + guión + specs**, sin
> código de negocio ejecutable. Cada fichero de esqueleto lleva un bloque-guía (propósito, qué
> implementar, contrato, dependencias, pasos, anti-patrones). El código real lo escribe el owner a
> mano después. Flujo de trabajo: `docs/guides/task-lifecycle.md`.

## Arquitectura (hexagonal)

Dependencia `api → domain ← infra`. **El dominio no importa infra.** Puertos (interfaces) en
`app/domain`, adaptadores en `app/infra`. Pydantic v2, handlers `async`, config por entorno.

```
app/
├── core/        # config (BaseSettings), security, logging + request-id, deps        · tarea 07
├── api/v1/      # routers + schemas HTTP (core: 11 · flujo-IA: 12)                    · tareas 11, 12
├── domain/      # servicios de dominio + PUERTOS (ticket, approval, rbac, …)          · tarea 10
├── infra/
│   ├── db/          # SQLAlchemy, session, repos, Alembic, políticas RLS              · tarea 08
│   ├── vector/      # adaptador pgvector (almacén de embeddings)                      · tareas 13, 14
│   ├── llm/         # puerto LLM + adaptador OpenAI + embeddings                      · tarea 09
│   └── langsmith/   # tracing/observabilidad                                          · tarea 09
├── agents/      # grafo LangGraph: definición (15) + checkpointer/HITL (16)           · tareas 15, 16
├── ingestion/   # pipeline de ingestión de la KB (loader/parser/chunker/embedder)     · tarea 13
└── rag/         # retriever pgvector + confianza híbrida + citas                      · tarea 14
```

## Requisitos

- Python 3.12+
- Docker + Docker Compose (para Postgres+pgvector)
- `make`

## Puesta en marcha (local)

```bash
cp .env.example .env          # rellena OPENAI_API_KEY, JWT_SECRET, …
make venv                     # crea .venv
make install                  # compila (pip-tools) e instala deps de desarrollo
docker compose up -d db       # Postgres 16 + pgvector con healthcheck
make migrate                  # aplica migraciones Alembic (incl. RLS)          · disponible tras la tarea 08
make seed                     # tenant demo + roles + KB de muestra              · disponible tras la tarea 17
make ingest                   # ingesta la KB real (idempotente)                 · disponible tras la tarea 13
make run                      # levanta la API (http://localhost:8000)           · disponible tras la tarea 07
```

O el stack completo en contenedores:

```bash
docker compose up --build     # `db` (sano) + `api`
```

`GET /health` comprueba conexión a DB + disponibilidad de la extensión pgvector (tarea 07).

## Calidad

```bash
make lint        # ruff (lint + format check)
make typecheck   # mypy strict
make test        # pytest (cuando exista código real)
```

## Configuración

Toda la config llega por entorno vía `pydantic-settings` (ver `.env.example`). Nunca se hornean
secretos en la imagen ni se leen en tiempo de import. La **dimensión del vector** (`EMBEDDING_DIM`)
es la fuente de la columna `vector(N)`: cambiarla implica re-embed de la KB.

## Especificaciones

Los contratos que fijan este backend viven en `.claude/specs/backend/` (`rbac`, `data-model`,
`rag-ingestion`, `agent-graph`) y `.claude/specs/general/api-contract.md` (única fuente de verdad de
la API, OpenAPI-first). El **guión maestro** de construcción es `IMPLEMENTATION-GUIDE.md` (tarea 19).
