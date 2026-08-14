---
layout: home

hero:
  name: Syntax
  text: Helpdesk con IA generativa
  tagline: RAG sobre la documentación de Syntax, bajo aprobación humana, multi-tenant.
  actions:
    - theme: brand
      text: Empezar
      link: /getting-started
    - theme: alt
      text: Arquitectura
      link: /architecture
    - theme: alt
      text: Guía de implementación
      link: /backend/implementation

features:
  - title: RAG + aprobación humana (HITL)
    details: El agente redacta un borrador citando la KB; un humano lo aprueba, edita o rechaza antes de enviarlo al cliente.
  - title: Multi-tenant con RLS
    details: Cliente = dominio. Aislamiento en profundidad — app-level en los repos + Row Level Security en Postgres. KB compartida sin RLS.
  - title: RBAC por capacidades
    details: Autorización por capacidad + ámbito (tenant/global), roles semilla y roles custom por tenant. Nunca por nombre de rol.
  - title: Grafo LangGraph tipado
    details: Grafo plano con edges condicionales, clasificación con structured output y checkpointer Postgres para el HITL asíncrono.
---

## Qué es esto

**Syntax** es un helpdesk con IA generativa para el producto **Syntax**: responde a los tickets de
soporte con IA (RAG sobre la documentación) **bajo aprobación humana**, con gestión de tickets real y
**multi-tenant** (cada cliente es un dominio).

El repositorio es un **monorepo** con dos áreas:

- **`backend/`** — FastAPI async + LangChain/LangGraph/LangSmith + Postgres/pgvector. Hoy es un
  **esqueleto doc-only** (estructura + guión por fichero + specs); el código de negocio lo implementa el
  owner siguiendo la [guía de implementación](/backend/implementation).
- **`frontend/`** — Next.js 16 + TypeScript + Tailwind + shadcn/ui. Consume el
  [contrato de API](/reference/api-contract) compartido.

Ambos se encuentran en el **contrato de API** (OpenAPI 3.1), única fuente de verdad que el backend define
y el frontend consume.

> **Fuente de verdad.** Las decisiones canónicas viven en las **specs** (`.claude/specs/`). Este sitio es
> una síntesis navegable que resume y **apunta** a esas specs; ante cualquier duda, manda la spec.
