---
id: backend-skeleton-foundation-09
package: backend
plan: skeleton-foundation
status: done
priority: 2
depends_on: [backend-skeleton-foundation-07]
estimate: 2h
actual: 0.5h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# Skeleton puerto LLM + embeddings + LangSmith

## Description

Esqueleto de `app/infra/llm/` y `app/infra/langsmith/`: puerto de proveedor LLM con **un adaptador
(OpenAI)**, puerto de embeddings, y la configuración de tracing LangSmith (que ninguna demo tenía). Solo
esqueleto + guión.

## Spec

- `app/domain/ports/llm.py` — interfaces `ChatModel` (chat/grade/generate) y `EmbeddingModel`.
- `app/infra/llm/openai_adapter.py` — adaptador OpenAI (chat `gpt-4o`/`4.1` default + `text-embedding-3-small`);
  guión: instanciación perezosa, sin credenciales en import, conmutable por env (`LLM_PROVIDER`).
- `app/infra/llm/structured.py` — helper de `with_structured_output` (Pydantic) para el clasificador (usa 05).
- `app/infra/langsmith/tracing.py` — guión de activación (`LANGCHAIN_TRACING_V2`, project, tags), y cómo
  se obtiene `langsmith_trace_url` para `AgentRun` (03).

## Refuerzos (scenario-coverage)

- **Timeout / retry / backoff** y manejo de **429 / caída** del proveedor; el fallo a mitad de grafo se
  propaga como `AgentRun.failed` (03) con error controlado al usuario (A1.4).

## Fuera de alcance

- Adaptador Anthropic (seam: el puerto lo permite, no se implementa ahora). Implementar llamadas reales.

## Scenarios (Gherkin)

<!-- Doc-only. -->
**Verificación (doc-only):**
- Existe un puerto LLM + puerto embeddings; el adaptador OpenAI es el único, conmutable por env.
- El helper de structured output existe para el clasificador de 05.
- El guión de LangSmith describe activación y obtención de `trace_url`.
- Nada crea credenciales/valida config en el import.

## Provides

- Puertos `llm`/`embeddings` + adaptador OpenAI + structured-output + tracing LangSmith. 13 (embeddings),
  14 (grade), 15 (generate/classify) cuelgan de estos puertos.

## Definition of Done

- [x] Puertos (`llm.py`: ChatModel+EmbeddingModel) + adaptador OpenAI + `structured.py` + `tracing.py` creados con guión; conmutable por `LLM_PROVIDER` (añadido a `.env.example`). `compileall` OK.
- [x] Sin efectos en import (guión lo prohíbe); `langsmith_trace_url` documentado hacia `AgentRun` (03).
- [x] `Provides` disponible para las dependientes (13 embeddings, 14 grade, 15 generate/classify).
- [x] Gate de `fact-checker` superado (sonnet): 8/8 VERIFICADO.
- [x] Histórico en `.claude/context/backend/backend-skeleton-foundation-09.md`.
