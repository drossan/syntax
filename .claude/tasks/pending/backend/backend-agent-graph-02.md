---
id: backend-agent-graph-02
package: backend
plan: agent-graph
status: pending
priority: 1
depends_on: []
estimate: 2h
actual:
created: 2026-08-27
updated: 2026-08-27
---

# `app/rag/confidence.py` — confianza híbrida (similitud + grade)

## Description

Implementa el guión de `app/rag/confidence.py` (ADR-0009): combina la similitud cruda de los chunks
recuperados con el juicio del LLM (`grade.suficiente`) en una única señal `confidence: float`. El
`grade` actúa como **veto**, no como sumando aritmético (decisión de `grilling`): sin contexto
suficiente, la confianza es 0 sin importar cuán alta sea la similitud — nunca se inventa una respuesta.

## Spec

- `compute_confidence(retrieved: list[RankedHit], grade_suficiente: bool) -> float`:
  - Si `grade_suficiente` es `True` y `retrieved` no está vacío → `max(hit.hit.score for hit in
    retrieved)` (similitud **cruda**, `RankedHit.hit.score` — NO `weighted_score`: si llevara ya el
    peso de `estado`, éste se contaría dos veces, `reranker.py` línea 35-38).
  - En cualquier otro caso (incl. `retrieved=[]` con `grade_suficiente=True` — guarda añadida en
    `design-review`) → `0.0`.
- No importa infra; usa `app.rag.reranker.RankedHit` (ya existe, plan `kb-retriever`).
- Puro, sin I/O, sin puertos.

## Fuera de alcance

—

## Scenarios (Gherkin)

```gherkin
Feature: Confianza híbrida del agente

  Scenario: contexto suficiente da la similitud máxima como confianza
    Given una lista de hits recuperados con distintos scores y grade.suficiente=true
    When se calcula la confianza
    Then el resultado es el score CRUDO máximo de los hits (sin el peso de estado)

  Scenario: contexto insuficiente escala con confianza 0
    Given cualquier lista de hits (incluso con scores altos) y grade.suficiente=false
    When se calcula la confianza
    Then el resultado es 0.0

  Scenario: sin hits nunca hay confianza aunque el LLM diga que basta
    Given una lista de hits vacía y grade.suficiente=true
    When se calcula la confianza
    Then el resultado es 0.0, sin lanzar excepción

  Scenario Outline: un solo hit determina la confianza si es el único
    Given una lista con un único hit de score <score> y grade.suficiente=true
    When se calcula la confianza
    Then el resultado es <score>

    Examples:
      | score | resultado |
      | 0.0   | 0.0       |
      | 1.0   | 1.0       |
```

## Provides

- `compute_confidence()` — lo consume el nodo `decide` (tarea 05, vía `grade`/`retrieved` del estado) y
  el runner (tarea 08) para persistir `agent_run.confidence`.

## Definition of Done
- [ ] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [ ] Cada escenario Gherkin tiene al menos un test (camino feliz + bordes/errores)
- [ ] Todos los tests en verde
- [ ] Spec cumplida; lo declarado en `Provides` queda realmente disponible para las tareas dependientes
- [ ] Lint / format / typecheck OK
- [ ] Gate de mutation testing superado (`cosmic-ray`, `break: 80`)
- [ ] Gate `sdd-lint` superado (ERROR bloquea, AVISO se reconoce)
- [ ] Gate de `fact-checker` superado (INCORRECTO bloquea; NO VERIFICABLE = aviso a reconocer)
- [ ] **SDD** — sin CU propio (función pura interna); referencia ADR-0009 en el docstring del módulo
- [ ] Documentación actualizada — tres capas:
  - [ ] TSDoc en el código (docstring de `compute_confidence`, por qué `hit.score` y no `weighted_score`)
  - [ ] Doc técnica — sin cambios adicionales (ADR-0009 ya documenta la decisión)
  - [ ] Histórico de la tarea — session log en `.claude/context/backend/backend-agent-graph-02.md`
- [ ] Docs de dev / usuario final — no aplica
