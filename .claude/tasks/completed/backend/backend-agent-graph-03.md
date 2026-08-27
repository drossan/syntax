---
id: backend-agent-graph-03
package: backend
plan: agent-graph
status: done
priority: 1
depends_on: []
estimate: 2h
actual: ~1h
created: 2026-08-27
updated: 2026-08-27
---

# `app/rag/citations.py` — construcción de citas de las fuentes

## Description

Implementa el guión de `app/rag/citations.py`: a partir de los hits usados en la respuesta, construye
la lista de citas que viaja a `agent_run.sources` (JSONB) y que el router `agent.py` ya deserializa
como `Citation(**source)`. Deduplica por `(uc_id, section_type)` — **no** reutiliza
`app.rag.dedup.dedup_by_uc_id`: ese módulo documenta explícitamente que su único consumidor es el
camino HTTP (colapsa a un hit por `uc_id`, perdiendo qué secciones se usaron); las citas del agente
necesitan trazar cada sección citada, no solo el documento.

## Spec

- `build_citations(hits: list[RankedHit]) -> list[dict[str, Any]]`: por cada `RankedHit`, produce
  `{"uc_id": ..., "title": ..., "section_type": ..., "source_url": ..., "score": ...}` — mismos campos
  que `app/api/v1/schemas/agent.py::Citation`. `score` = `weighted_score` (relevancia mostrada al
  usuario, consistente con lo que ya expone `KBSearchHit.score` en el camino HTTP).
- Dedup por `(uc_id, section_type)`: conserva la **primera** aparición de cada par (la entrada ya viene
  ordenada por relevancia desde `rerank`), descarta repeticiones exactas de la misma sección.
- Puro, sin I/O, sin puertos.
- `list[dict]` (no un modelo Pydantic nuevo) porque el consumidor directo es `agent_run.sources`
  (`list[dict[str, Any]]` en `AgentRun`, business.py:99) — evita un tipo intermedio sin más uso que
  serializar.

## Fuera de alcance

—

## Scenarios (Gherkin)

```gherkin
Feature: Construcción de citas del agente

  Scenario: cada hit se convierte en una cita trazable
    Given un hit recuperado con uc_id, title, section_type, source_url y score conocidos
    When se construyen las citas
    Then la cita resultante incluye esos 5 campos con los valores del hit

  Scenario: no se citan dos veces la misma sección del mismo documento
    Given dos hits con el mismo uc_id y section_type pero distinto chunk_id
    When se construyen las citas
    Then solo aparece una cita para ese par (uc_id, section_type)

  Scenario: secciones distintas del mismo documento sí se citan por separado
    Given dos hits con el mismo uc_id pero distinto section_type
    When se construyen las citas
    Then aparecen dos citas, una por cada section_type

  Scenario: sin hits no hay citas
    Given una lista de hits vacía
    When se construyen las citas
    Then el resultado es una lista vacía

  Scenario: tres o más duplicados exactos se colapsan en una sola cita
    Given tres hits con el mismo uc_id y el mismo section_type
    When se construyen las citas
    Then solo aparece una cita para ese par (uc_id, section_type), no dos

  Scenario: el dedup descarta, no reordena
    Given hits en orden [A(uc1,intro,score=0.9), B(uc2,intro,score=0.8), C(uc1,intro,score=0.7 — duplicado de A, no contiguo)]
    When se construyen las citas
    Then el resultado es [cita_de_A, cita_de_B] en ese orden exacto, sin cita para C
```

## Provides

- `build_citations()` — lo consume el nodo `generate` (tarea 05) para poblar `state.retrieved`/las
  citas del draft, y el runner (tarea 08) para persistir `agent_run.sources`.

## Definition of Done
- [x] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [x] Cada escenario Gherkin tiene al menos un test (camino feliz + bordes/errores)
- [x] Todos los tests en verde (7 passed en la tarea; suite completa `pytest -q` exit 0)
- [x] Spec cumplida; lo declarado en `Provides` queda realmente disponible para las tareas dependientes
- [x] Lint / format / typecheck OK
- [x] Gate de mutation testing superado (`cosmic-ray`, `break: 80`) — 0.00% survivors (2ª vuelta, tras reforzar el test de dedup en medio de la lista)
- [x] Gate `sdd-lint` superado — N/A (sin CU propio), CU-BE-05 escenario 5 verificado por conteo real
- [x] Gate de `fact-checker` superado — 10/10 VERIFICADO, 0 INCORRECTO
- [x] **SDD** — sin CU propio (función pura interna); referencia CU-BE-05 escenario 5 en el docstring
- [x] Documentación actualizada — tres capas:
  - [x] TSDoc en el código (docstring de `build_citations`, por qué no reutiliza `dedup_by_uc_id`)
  - [x] Doc técnica — sin cambios adicionales
  - [x] Histórico de la tarea — session log en `.claude/context/backend/backend-agent-graph-03.md`
- [x] Docs de dev / usuario final — no aplica
