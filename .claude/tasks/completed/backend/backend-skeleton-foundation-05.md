---
id: backend-skeleton-foundation-05
package: backend
plan: skeleton-foundation
status: done
priority: 1
depends_on: [backend-skeleton-foundation-04]
estimate: 3h
actual: 1h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# Spec agente LangGraph + HITL + fases + LangSmith

## Description

Escribir `.claude/specs/backend/agent-graph.md`: el diseño del agente. Es el **núcleo de riesgo** del
producto (aprobación humana asíncrona), así que va con **detalle alto**. Recoge los patrones útiles de
las tres demos y descarta sus anti-patrones. Fuente para el skeleton del grafo (15) y del checkpointer/
HITL (16).

## Spec

- **Grafo PLANO con edges condicionales tipados** (NO supervisor por prompt): `classify → retrieve →
  grade → generate → (decide) → [auto | HITL] → respond`. Nada de routing por texto libre.
- **Clasificación con `with_structured_output`** (Pydantic): `{categoria, dominio (1 de 17), prioridad,
  resoluble}`. El `dominio` **filtra el retrieval** (recuperar solo de ese dominio + vecinos). Fija
  también `Ticket.domain/priority` (ver 03).
- **Estado** (`add_messages` + campos de dominio): `messages`, `tenant_id`, `ticket_id`, `classification`,
  `retrieved`, `confidence`, `requires_approval`, `draft_response`, `human_note`.
- **`trim_messages`** para ventana de contexto en hilos largos.
- **Confianza híbrida** (de 04): similitud + nodo `grade` (relevancia+suficiencia) → decide auto vs
  escalado; contexto insuficiente → **nota al humano** (`human_note`).
- **HITL asíncrono (detalle)**: `interrupt` antes de `respond`; el estado se checkpointéa en Postgres
  (`PostgresSaver`, `thread_id`=ticket); un **endpoint de aprobación** (ver 06/12) inyecta la decisión y
  hace `resume`. Documentar: reanudar tras **reinicio del servidor** a mitad de run, **ediciones
  concurrentes** del estado, y el mapeo `interrupt ↔ ApprovalTask`.
- **Fases**: `auto_approve=false` por defecto (por tenant); Fase 2 (nota al desarrollador) **fuera**.
- **Tools tipadas** (`@tool` con args tipados) con **toolset acotado por tenant** (mínimo privilegio), si
  el nodo lo requiere. **Settings inyectables** (sin validar config/crear credenciales en el import).
- **LangSmith**: tracing de todo el grafo (`langsmith_trace_url` en `AgentRun`). Seam `astream` para
  streaming SSE del draft (Fase posterior).

## Refuerzos (scenario-coverage)

- **Prompt injection**: el contenido del ticket es **input no confiable** → aislarlo del system-prompt, no
  ejecutar instrucciones embebidas, límites de salida; **riesgo elevado con `auto_approve=true`** (documentar).
- **Ticket no clasificable** en los 17 dominios: baja confianza de clasificación → **fallback** (retrieval
  sin filtro de dominio), no forzar un dominio equivocado.
- **Idioma de respuesta**: responder en el idioma del ticket (detección o locale de tenant/usuario); KB en español.
- **Fallo del LLM a mitad de run** → `AgentRun.failed` + error controlado al usuario; checkpoint consistente.
- **Re-draft tras reopen** → run nuevo (`thread_id` con secuencia), `AgentRun` previo superado (A1.2).

## Fuera de alcance

- Implementar el grafo (eso es 15/16); nota al desarrollador y KB de código (Fase 2); streaming SSE (seam).

## Scenarios (Gherkin)

<!-- Doc-only. -->
**Verificación (doc-only):**
- El grafo es plano con edges tipados; la clasificación usa structured output, no parseo de strings.
- El `dominio` clasificado se usa como filtro del retrieval.
- El modelo HITL describe interrupt→checkpoint Postgres→endpoint→resume, con reinicio y concurrencia.
- Los campos del estado coinciden con `AgentRun`/`Ticket`/`ApprovalTask` de 03.

## Provides

- `.claude/specs/backend/agent-graph.md`: nodos, estado, confianza, modelo HITL asíncrono, tools, tracing.
  15 implementa la definición del grafo; 16 el checkpointer+HITL; 06 expone los endpoints del flujo-IA.

## Definition of Done

- [x] Spec creada con detalle alto del HITL (interrupt→checkpoint Postgres→endpoint→resume; reinicio a mitad de run; ediciones concurrentes/doble decisión 409; mapeo interrupt↔ApprovalTask).
- [x] Grafo plano + edges condicionales tipados + clasificación `with_structured_output` + filtro por dominio documentados.
- [x] Coherente con 03 (estado↔AgentRun/Ticket/ApprovalTask, verificado) y 04 (confianza híbrida similitud+grade, filtro dominio).
- [x] `Provides` disponible para las dependientes.
- [x] Gate de `fact-checker` superado (sonnet): 8/8 VERIFICADO (incl. C8: spec honesta, sin afirmar surface de API no verificado).
- [x] Histórico en `.claude/context/backend/backend-skeleton-foundation-05.md`.
