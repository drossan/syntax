# Backend · visión general

FastAPI async + LangChain/LangGraph/LangSmith + Postgres/pgvector, arquitectura **hexagonal**.

## Estado actual: esqueleto doc-only

El backend es hoy un **esqueleto**: la estructura de ficheros completa, un **guión por fichero** (docstring
que dice *qué* implementar) y las **specs** que fijan los contratos. **No hay código de negocio todavía**
— lo construye a mano el owner siguiendo la [guía de implementación](/backend/implementation).

## Estructura (`backend/app/`)

| Paquete | Responsabilidad |
|---|---|
| `core/` | config (settings inyectables), security (JWT/Argon2), logging (+request-id), deps (auth/tenant/autorización) |
| `domain/` | servicios de negocio + **puertos** (interfaces) + entidades — el centro hexagonal |
| `infra/` | adaptadores: `db` (SQLAlchemy+Alembic+RLS), `llm` (OpenAI), `vector` (pgvector), `langsmith` |
| `api/v1/` | routers (core + flujo-IA) + schemas (DTOs del contrato) |
| `agents/` | grafo LangGraph (definición) + checkpointer/HITL |
| `rag/` | retriever (pgvector) + reranker + confianza + citas |
| `ingestion/` | pipeline KB (loader→parser→chunker→embedder→upsert) + CLI |
| `workers/` | scheduler de SLA (acotado solo a SLA) |

`app/main.py` es el app factory (`create_app()`) con `/health` (liveness/readiness: DB + pgvector).

## Comandos (Makefile)

`make install` · `make migrate` · `make ingest` · `make seed` · `make run` · `make lint` · `make typecheck`
· `make test`. Detalle en [Empezar](/getting-started) y en la [guía de implementación](/backend/implementation).

## Specs (fuente de verdad)

Ver [Backend · Specs](/backend/specs): RBAC, modelo de datos, RAG+ingestión, agente+HITL y el contrato de
API. Las specs canónicas viven en `.claude/specs/`.
