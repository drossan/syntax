# Backend · Specs (fuente de verdad)

Las specs son la **fuente de verdad** del backend; viven en `.claude/specs/` y se verifican por bullets.
Este sitio las resume y enlaza a las páginas de referencia sintetizadas.

> **Capa SDD** (`features.sdd`): las **decisiones** de arquitectura viven en los [ADR](/reference/adr)
> (MADR); los **requisitos** en `spec.md` (EARS); los **flujos** en los [casos de uso](/reference/casos-de-uso)
> (Gherkin). Las specs de la tabla de abajo son el **detalle técnico de referencia** que gobierna `spec.md`.

| Spec (canónica) | Resumen | Referencia |
|---|---|---|
| `.claude/specs/backend/spec.md` | **Requisitos EARS** (el QUÉ): user stories + FR/NFR + criterios de éxito + enlaces a casos de uso. | — |
| `.claude/specs/backend/casos-de-uso/` | **10 casos de uso** (Cockburn + Gherkin) — el CÓMO del actor y único hogar del Gherkin de aceptación. | [Casos de uso](/reference/casos-de-uso) |
| `.claude/specs/backend/rbac.md` | Capacidades + ámbito, roles semilla + custom por tenant, visibilidad `public\|internal`, `authorize()`. | [RBAC](/reference/rbac) |
| `.claude/specs/backend/data-model.md` | 18 entidades, enums, ERD, marca RLS, cascadas/retención, `vector(N)` desde config. | [Modelo de datos](/reference/data-model) |
| `.claude/specs/backend/rag-ingestion.md` | Parsing (frontmatter+Trazabilidad), chunking **H2 tolerante**, categorización, upsert idempotente, retrieval+confianza. | [RAG + ingestión](/reference/rag) |
| `.claude/specs/backend/agent-graph.md` | Grafo plano + edges tipados, clasificación structured-output, **HITL** interrupt→checkpoint→resume, LangSmith. | [Agente + HITL](/reference/agent-graph) |
| `.claude/specs/general/api-contract.yaml` | **Contrato OpenAPI 3.1** (fuente única). `api-contract.md` = companion. | [Contrato de API](/reference/api-contract) |

## Coherencia entre specs

- Los **enums** (estado/prioridad de ticket, visibilidad, estado de aprobación, estado de run, dominios KB)
  se definen en `data-model` y se **reusan literal** en `rbac`, `api-contract` y el frontend.
- El **contrato de API** (06) deriva de rbac (02) + data-model (03) + rag (04) + agent-graph (05): es la
  única fuente de verdad de la superficie HTTP.
- La **KB real** (verificada): 17 dominios · 268 casos de uso · 18 index · frontmatter `title/domain/
  package/uc` · ~218 draft / 50 active.
