# Índice de ADR

> Índice de las decisiones de arquitectura (MADR 4.0.0) de Syntax. Capa **SDD** (`features.sdd`).
>
> **Numeración**: `NNNN-titulo.md` desde **`0001`**, ancho fijo de **4 dígitos** (preserva el orden
> lexicográfico). El **estado de cada fila es el de su ADR** (`proposed` / `accepted` / `rejected` /
> `deprecated` / `superseded`). Las decisiones **0001–0012** se **tomaron el 2026-08-11** (`grilling` +
> `design-review` de los planes) y se **materializaron como ADR** el 2026-08-14 al activar la capa SDD;
> **0013** (arranque de Fase 2) se decidió el 2026-08-14 y se materializó al arrancar `plan/backend/executable-foundation`.

| #    | Título                                                              | Estado   | Fecha      |
|------|--------------------------------------------------------------------|----------|------------|
| [0001](./0001-monorepo-pnpm-y-stack-poliglota.md) | Monorepo pnpm + stack poligloto por-package + git flow dev→main | accepted | 2026-08-11 |
| [0002](./0002-contrato-openapi-first.md) | Contrato de API OpenAPI-first como única fuente de verdad | accepted | 2026-08-11 |
| [0003](./0003-frontend-spa-client-rendered.md) | Frontend SPA client-rendered con access token en memoria | accepted | 2026-08-11 |
| [0004](./0004-auth-jwt-access-memoria-refresh-cookie-rotacion.md) | Auth JWT: access en memoria + refresh cookie httpOnly con rotación | accepted | 2026-08-11 |
| [0005](./0005-rbac-por-capacidad-y-ambito.md) | RBAC por capacidad + ámbito con roles custom por tenant | accepted | 2026-08-11 |
| [0006](./0006-aislamiento-multi-tenant-app-level-mas-rls.md) | Aislamiento multi-tenant app-level + RLS día 1 (KB global sin RLS) | accepted | 2026-08-11 |
| [0007](./0007-hitl-asincrono-postgressaver-checkpointer.md) | HITL asíncrono sobre API con checkpointer PostgresSaver | accepted | 2026-08-11 |
| [0008](./0008-grafo-langgraph-plano-edges-tipados.md) | Grafo LangGraph plano con edges condicionales tipados | accepted | 2026-08-11 |
| [0009](./0009-confianza-hibrida-y-auto-approve-por-tenant.md) | Confianza híbrida → auto vs escalado; auto_approve=false por tenant | accepted | 2026-08-11 |
| [0010](./0010-rag-pgvector-chunking-h2-tolerante-estado-peso.md) | RAG: pgvector + dimensión config + chunking H2 tolerante + peso `estado` | accepted | 2026-08-11 |
| [0011](./0011-entrega-draft-por-polling-no-sse-fase-1.md) | Entrega del draft por polling (no streaming SSE en Fase 1) | accepted | 2026-08-11 |
| [0012](./0012-backend-fase-1-doc-only-fase-2-diferida.md) | Backend Fase 1 doc-only; Fase 2 diferida | superseded (0013) | 2026-08-11 |
| [0013](./0013-arranque-fase-2-backend-codigo-real.md) | Arranque de Fase 2 del backend (código real, TDD) | accepted | 2026-08-14 |
