# 0012. Backend Fase 1 doc-only (esqueleto + specs + guión); Fase 2 diferida

- **Estado**: accepted
- **Fecha**: 2026-08-11
- **Decisores**: Owner (backend como práctica de LangChain/LangGraph a implementar a mano).

## Contexto y planteamiento del problema

El backend es también un **ejercicio de aprendizaje** de LangChain/LangGraph/LangSmith que el owner quiere
**construir a mano**. A la vez, el frontend necesita un **contrato estable** ya. ¿Se implementa el código de
negocio del backend ahora, o se produce primero el **esqueleto navegable + specs** que fije contratos y
guíe la construcción manual? ¿Qué entra en Fase 1 y qué se difiere?

## Decision drivers

- El owner implementará el backend a mano (valor pedagógico) → no auto-generar la lógica.
- El frontend depende de un contrato estable, no de la implementación.
- Acotar Fase 1 para no arrastrar features de Fase 2 a medio hacer.

## Opciones consideradas

- **Opción 1** — Backend **doc-only** en Fase 1: estructura hexagonal completa + **guión por fichero** +
  **specs** (rbac/data-model/api-contract/rag/agent) + scaffolding que valida; **sin código de negocio**.
  Fase 2 (SSO/OIDC, nota al desarrollador/visibilidad `developer`) **diferida por completo**.
- **Opción 2** — Implementar el backend real ya (código de negocio ejecutable).
- **Opción 3** — Sin backend: mockear todo indefinidamente en el frontend.

## Resultado de la decisión

Elegida: **Opción 1**. El plan `skeleton-foundation` produjo el **esqueleto** (layout hexagonal, un fichero
guión por pieza), las **specs** que fijan los contratos y el scaffolding (docker-compose pgvector, Alembic,
pyproject, Makefile). **Sin TDD ni gate de mutation** (escape hatch doc-only); verificación = estructura +
guiones + specs coherentes + scaffolding que valida + `fact-checker`. **Fase 2 diferida**: SSO/OIDC (hueco
en auth), nota al desarrollador / KB de código / visibilidad `developer`, streaming SSE
([[0011-entrega-draft-por-polling-no-sse-fase-1]]). Al implementar el backend real pasará a TDD (ajustar
`stack` a python/pytest en `task-pipeline.yml`).

### Confirmación

`backend/IMPLEMENTATION-GUIDE.md` (orden de build, gate "OpenAPI generado ⊇ contrato"); plan
`skeleton-foundation` cerrado 19/19 (2026-08-13, `fact-checker` por tarea); `task-pipeline.yml`
`stack.packages.backend` (`test-runner: none` hasta que haya código).

## Consecuencias

- **Buenas**: contrato estable ya; el owner aprende implementando; Fase 1 acotada y coherente.
- **Malas / coste**: el backend **no ejecuta** todavía (el frontend consume mocks MSW); huecos explícitos
  (SSO, GDPR/retención) a resolver antes de producción.

## Pros y contras de las opciones

- **Opción 1**: 👍 contrato firme + valor pedagógico + alcance acotado · 👎 backend no ejecutable aún.
- **Opción 2**: 👍 sistema real end-to-end · 👎 anula el ejercicio manual; más tiempo antes del contrato.
- **Opción 3**: 👍 cero backend · 👎 el contrato nunca se valida contra una implementación real.
