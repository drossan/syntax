# Arquitectura

## Visión general

Monorepo con dos áreas que se encuentran en el **contrato de API**:

```
frontend (Next.js) ──HTTP──▶ backend (FastAPI) ──▶ Postgres + pgvector
     │                            │
     └── mocks MSW (del contrato) └── LangGraph (agente) · LangSmith (tracing) · OpenAI (LLM/embeddings)
```

- **`backend/`** — FastAPI async, arquitectura **hexagonal**, Postgres/pgvector (negocio + embeddings en
  el mismo Postgres), SQLAlchemy 2 async + Alembic, RBAC multi-tenant, aislamiento app-level **+ RLS**,
  puerto LLM conmutable y tracing LangSmith.
- **`frontend/`** — Next.js 16 (App Router), TS estricto, Tailwind v4, shadcn/ui.

## Hexagonal (backend)

```
app.api  ──▶  app.domain  ◀──  app.infra
(routers)   (servicios+puertos)  (adaptadores: db, llm, vector, langsmith)
```

- **Regla de oro**: `app.domain` **no importa** `app.infra` ni `app.api`. Define **puertos** (interfaces)
  que `app.infra` implementa y `app.api` orquesta. La dirección de dependencias no se invierte nunca.
- **Capas**: `app/core` (config/security/logging/deps), `app/domain` (servicios + puertos + entidades),
  `app/infra` (db/llm/vector/langsmith), `app/api/v1` (routers + schemas), `app/agents` (grafo + HITL),
  `app/rag` (retriever), `app/ingestion` (pipeline KB), `app/workers` (scheduler SLA).

## Multi-tenant y aislamiento

- **Cliente = tenant = dominio**. El personal de Soporte vive en un tenant-sistema `syntax` y actúa
  cross-tenant (ámbito `global`).
- **Aislamiento en profundidad**: (1) **app-level** — los repos filtran por `tenant_id` del contexto;
  (2) **RLS** — políticas Postgres + `SET app.tenant_id` por conexión.
- **KB compartida**: las tablas de la base de conocimiento **no** llevan RLS de tenant (documentación de
  Syntax, común a todos).

::: warning Footgun de RLS
`SET app.tenant_id` sobre un pool asyncpg reutiliza conexiones → posible fuga cross-tenant. Se usa
`SET LOCAL` transaccional / reset en checkin y se **exigen tests de integración** contra Postgres real.
Detalle en la [guía de implementación](/backend/implementation).
:::

## Flujo IA con aprobación humana (HITL)

```
POST /tickets/{id}/ai-draft → runner.run → grafo (classify→retrieve→grade→generate→decide)
   → interrupt (checkpoint Postgres, thread_id=ticket_{id}_run_{n}) → ApprovalTask(pending)
   → cola GET /approvals → POST /approvals/{id}/{approve|edit|reject} → runner.resume
   → Message(visibility=public) + transición del ticket
```

`auto_approve=false` por defecto (por tenant): todo borrador pasa por revisión humana. Detalle en
[Agente + HITL](/reference/agent-graph).

## Decisiones clave

| Decisión | Elección |
|---|---|
| Auth | JWT access (memoria, TTL corto) + refresh en cookie httpOnly (rotación + reuse-detection) |
| Autorización | Por **capacidad + ámbito**, resuelta server-side por request (no desde el JWT) |
| Embeddings | OpenAI `text-embedding-3-small` → `vector(1536)` (dimensión desde config) |
| Retrieval | pgvector coseno + filtros + confianza híbrida (similitud + grade) |
| Agente | Grafo **plano** con edges condicionales tipados (no supervisor por prompt) |
| Persistencia HITL | Checkpointer **Postgres** por `thread_id` = ticket |
