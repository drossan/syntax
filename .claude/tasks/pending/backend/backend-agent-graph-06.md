---
id: backend-agent-graph-06
package: backend
plan: agent-graph
status: pending
priority: 1
depends_on: [backend-agent-graph-05]
estimate: 3h
actual:
created: 2026-08-27
updated: 2026-08-27
---

# `app/agents/graph.py` — `build_graph()`, grafo COMPLETO, edges condicionales tipados

## Description

Ensambla los 7 nodos de la tarea 05 en un `StateGraph[HelpdeskState]` **plano** con edges condicionales
que leen campos tipados del estado (ADR-0008) — nunca texto libre del LLM. Construye el grafo COMPLETO
`classify → retrieve → grade → generate → decide → respond` (decisión de `grilling` #1: `respond` e
`interrupt()` viven en el grafo desde esta tarea, no se añaden por fuera en 08/09). **NO compila con
checkpointer todavía** — eso es la tarea 07 (construir el `PostgresSaver`) + la tarea 08 (compilar
grafo+checkpointer e invocar). `build_graph()` devuelve el `StateGraph` sin compilar (o compilado sin
`checkpointer`, según convenga para los tests de routing de esta tarea).

## Spec

- `build_graph(chat_model: ChatModel, retriever: Retriever, messages_repo: MessageRepository, *,
  top_k: int, confidence_threshold: float, trim_max_tokens: int) -> StateGraph[HelpdeskState]`: registra
  los 7 nodos (tarea 05) y los edges:
  - `classify → retrieve` siempre.
  - `retrieve → grade` siempre.
  - `grade → generate` siempre (edge condicional dentro de `generate`, no aquí: `generate` decide
    internamente si redacta o solo prepara `human_note`, tarea 05).
  - `generate → decide` siempre.
  - `decide → respond` incondicional (la rama HITL vs auto la resuelve `respond` leyendo
    `state["requires_approval"]`/`state["human_decision"]`, tarea 05).
  - `respond → END`.
  - Edge condicional real y tipado de este grafo: **`classify.resoluble=False` → salta directo a
    `respond`** (escalado sin `generate`, CU-BE-05 extensión 1b) — lee `state["classification"].resoluble`.
- `trim` se invoca antes de `classify` (recorta `state["messages"]` en hilos largos por reaperturas).
- Tests de routing: compilar el grafo con `langgraph.checkpoint.memory.InMemorySaver` **SOLO en tests**
  (ADR-0007 prohíbe `MemorySaver` en producción; aquí es un checkpointer de prueba que permite observar
  que `interrupt()` se alcanza, sin implicar persistencia real — eso lo verifica la tarea 07/08/09).

## Fuera de alcance

- Streaming SSE / `astream` token-a-token (seam, no Fase 1).
- Compilación con `PostgresSaver` real (tarea 07/08).

## Scenarios (Gherkin)

Criterios de aceptación (Gherkin) en el caso de uso — esta tarea verifica el **routing end-to-end** de
[CU-BE-05 — Clasificación y retrieval RAG](../../../specs/backend/casos-de-uso/CU-BE-05-clasificacion-y-retrieval-rag.md)
(los 5 escenarios: dominio fija el filtro, fallback sin dominio, contexto insuficiente escala, draft
participan ponderados, la respuesta cita fuentes) a través del grafo compilado completo (con
checkpointer de prueba en memoria).

Escenario adicional de routing puro (no cubierto por el CU a este nivel):

```gherkin
Feature: Routing del grafo del agente

  Scenario: ticket no resoluble salta generate y escala directo
    Given classification.resoluble=false tras el nodo classify
    When se invoca el grafo
    Then el grafo llega a respond sin haber pasado por generate

  Scenario Outline: combinación de señales produce el routing esperado
    Given classification.resoluble=<resoluble>, grade.suficiente=<suficiente> y auto_approve=<auto>
    When se invoca el grafo hasta el final o hasta un interrupt
    Then el resultado es <resultado>

    Examples:
      | resoluble | suficiente | auto  | resultado                          |
      | false     | -          | -     | escalado sin draft                 |
      | true      | false      | -     | escalado con human_note, sin draft |
      | true      | true       | false | interrupt (pendiente de aprobación)|
      | true      | true       | true  | respuesta automática publicada     |
```

Hallazgos de `scenario-coverage` (errores/estado a nivel de grafo compilado, no cubiertos antes):

```gherkin
Feature: Propagación de errores y trim a nivel de grafo

  Scenario: un fallo de un puerto (p.ej. Retriever caído) se propaga sin ser engullido por LangGraph
    Given un Retriever que lanza PortError al invocarse
    When se invoca el grafo compilado
    Then la excepción llega al llamante (runner, tarea 08) sin que LangGraph la silencie o la transforme en un estado parcial inconsistente

  Scenario: un hilo con 0 o 1 mensajes no rompe el grafo al pasar por trim
    Given un HelpdeskState inicial con 0 o 1 mensajes en state.messages
    When se invoca el grafo completo
    Then el grafo progresa con normalidad hasta classify sin lanzar excepción en el paso de trim
```

## Provides

- `build_graph()` — lo consume `runner.py` (tarea 08), que lo compila con el checkpointer real
  (tarea 07) e invoca.

## Definition of Done
- [ ] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [ ] Cada escenario Gherkin tiene al menos un test (camino feliz + bordes/errores)
- [ ] Todos los tests en verde
- [ ] Spec cumplida; lo declarado en `Provides` queda realmente disponible para las tareas dependientes
- [ ] Lint / format / typecheck OK
- [ ] Gate de mutation testing superado (`cosmic-ray`, `break: 80`)
- [ ] Gate `sdd-lint` superado (ERROR bloquea, AVISO se reconoce)
- [ ] Gate de `fact-checker` superado (INCORRECTO bloquea; NO VERIFICABLE = aviso a reconocer)
- [ ] **SDD** — enlaza CU-BE-05 (sin copiar su Gherkin); sin cambios de spec/CU nuevos
- [ ] Documentación actualizada — tres capas:
  - [ ] TSDoc en el código (`build_graph`, cada edge condicional documenta qué campo tipado lee)
  - [ ] Doc técnica — `app/agents/__init__.py` (el diagrama de módulo, hoy guión, refleja el grafo real)
  - [ ] Histórico de la tarea — session log en `.claude/context/backend/backend-agent-graph-06.md`
- [ ] Docs de dev / usuario final — no aplica
