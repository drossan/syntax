---
id: backend-agent-graph-09
package: backend
plan: agent-graph
status: done
priority: 1
depends_on: [backend-agent-graph-08]
estimate: 6h
actual: ~3h
created: 2026-08-27
updated: 2026-08-27
---

# `app/agents/hitl.py` + `runner.py::resume` — `Command(resume=)`, reinicio a mitad de run, fallo consistente

## Description

Segunda mitad del adaptador real de `AgentRunner` — el **núcleo de riesgo** (ADR-0007): reanudar un run
interrumpido tras la decisión humana, sobreviviendo a un reinicio del proceso, sin reanudar dos veces.
`approval_service.decide()` (YA REAL, plan `domain-services`) ya hace el CAS
`pending→decidida` y llama a `agent_runner.resume(agent_run_id, outcome)` **una sola vez** tras un CAS
exitoso — esta tarea implementa el lado que realmente reanuda el grafo.

## Spec

- `app/agents/hitl.py`: helpers de traducción `ApprovalOutcome` (puerto `agent_runner.py`, ya existe) →
  el payload de `Command(resume=...)` que el nodo `decide` espera recibir como retorno de `interrupt()`
  (tarea 05) — mapea `approved`/`edited`/`rejected` + `final_body`/`human_note`.
- `LangGraphAgentRunner.resume(agent_run_id, outcome)` (completa la tarea 08):
  - Resuelve `thread_id` desde `agent_run_id` vía `AgentRunRepository.get()` (el puerto ya deja claro
    que ESTE adaptador, no `approval_service`, traduce `agent_run_id → thread_id` — ver docstring de
    `agent_runner.py`).
  - Compila el MISMO grafo (tarea 06) con el checkpointer (tarea 07) — **una instancia nueva del
    runner/checkpointer sirve igual**: el estado vive solo en Postgres, no en memoria (ADR-0007).
  - `ainvoke(Command(resume=<payload de hitl.py>), config={"configurable": {"thread_id": thread_id}})`
    sobre el grafo compilado — reanuda desde el checkpoint, sin re-ejecutar nodos completados.
  - Tras reanudar: `AgentRun → succeeded` (o el estado que corresponda tras `respond`).
- Tests de integración (Postgres real, obligatorio — HITL es tabla de la tarea 07):
  1. **Aprobación/edición/rechazo**: cada decisión reanuda y `respond` (tarea 05) publica lo esperado.
  2. **Reinicio a mitad de run**: `trigger()` con un runner/checkpointer, DESCARTAR esa instancia
     (simula fin de proceso), crear un runner/checkpointer **nuevo** apuntando a la misma Postgres, y
     `resume()` con él — el grafo reanuda desde el checkpoint sin re-ejecutar `classify`/`retrieve`/
     `grade`/`generate` (verificable con un spy/contador de invocaciones al `ChatModel`/`Retriever` que
     no debe incrementar en el resume).
  3. **Fallo del LLM en `resume` (extensión, no en el CU pero simétrica a `trigger`)**: si `respond`
     falla tras reanudar, `AgentRun → failed` con error controlado, no una excepción cruda (usa
     `AgentRunRepository.update_result`, tarea 08).
  4. **`resume()` con `agent_run_id` inexistente** (hallazgo `scenario-coverage`): dato corrupto o
     desincronizado → error controlado (`NotFound`), no una excepción cruda del `AgentRunRepository`.
  5. **Defensa en profundidad — `resume()` sobre un thread sin interrupt pendiente** (hallazgo
     `scenario-coverage`): aunque la garantía real de "no reanudar dos veces" la da el CAS de
     `approval_service` (fuera de alcance de esta tarea, ver abajo), documentar y testear qué hace
     **este adaptador concretamente** si de todos modos se le llama en ese estado (p.ej. el propio
     `ainvoke(Command(resume=...))` de LangGraph sobre un grafo ya terminado — verificar el
     comportamiento real, no asumirlo).
  6. **Re-draft tras reopen** (CU/spec §6, "Refuerzo" nombrado en agent-graph.md §10, hallazgo
     `scenario-coverage`): un `AgentRun` superado (`run_seq=n`) no interfiere con el run activo tras
     reabrir el ticket (`run_seq=n+1`, `thread_id` nuevo) — una decisión tardía asociada al thread
     superado no reanuda ni afecta al run activo.

## Fuera de alcance

- Wiring en `app/core/deps.py` (swap de `StubAgentRunner`) — tarea 10.
- La garantía de "doble decisión = 409, no reanuda dos veces" YA la da el CAS de
  `approval_service.decide_if_pending` (plan `domain-services`) — esta tarea NO reimplementa esa
  garantía, solo confía en que `resume()` nunca se llama dos veces para el mismo `agent_run_id` tras un
  CAS fallido (lo verifica un test de integración que llama a `approval_service.decide()` dos veces
  seguidas, no `runner.resume()` directamente).

## Scenarios (Gherkin)

Criterios de aceptación (Gherkin) en el caso de uso —
[CU-BE-06 — Draft IA y aprobación HITL](../../../specs/backend/casos-de-uso/CU-BE-06-draft-ia-y-aprobacion-hitl.md),
escenarios: "Aprobación emite la respuesta al cliente", "Edición envía el texto corregido", "Rechazo no
publica nada al cliente", "Doble decisión es idempotente", "Reinicio a mitad de run reanuda desde el
checkpoint".

Escenarios adicionales (`scenario-coverage`, bordes no cubiertos por el CU a este grano):

```gherkin
Feature: Bordes de la reanudación HITL

  Scenario: resume sobre un agent_run_id inexistente falla controlado
    Given un agent_run_id que AgentRunRepository.get() no encuentra
    When se llama a resume() con ese id
    Then se lanza NotFound (o el error de dominio equivalente), nunca una excepción cruda del driver

  Scenario: un run superado tras reopen no interfiere con el run activo
    Given un ticket con un AgentRun run_seq=n ya superado (thread_id_n) y un AgentRun run_seq=n+1 activo (thread_id_n+1)
    When llega una decisión tardía asociada al thread_id_n
    Then no reanuda el thread_id_n+1 ni lo afecta de ninguna forma
```

## Provides

- `LangGraphAgentRunner` completo (`trigger` + `resume`) — sustituye funcionalmente a
  `StubAgentRunner`; el wiring real en `deps.py` es la tarea 10.

## Definition of Done
- [x] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [x] Cada escenario Gherkin tiene al menos un test (camino feliz + bordes/errores)
- [x] Todos los tests en verde (16 en la tarea; suite completa `pytest -q` exit 0)
- [x] Spec cumplida; lo declarado en `Provides` queda realmente disponible para las tareas dependientes
- [x] Lint / format / typecheck OK
- [x] Gate de mutation testing superado (`cosmic-ray`, `break: 80`) — 8.82% survivors (mutantes equivalentes)
- [x] Gate `sdd-lint` superado — N/A (enlaza CU sin copiar Gherkin), spot-check sin `[NECESITA ACLARACIÓN`
- [x] Gate de `fact-checker` superado — 11/11 VERIFICADO, 0 INCORRECTO
- [x] **SDD** — enlaza CU-BE-06 (sin copiar su Gherkin)
- [x] Documentación actualizada — tres capas:
  - [x] TSDoc en el código (`hitl.py`, `resume`, la prueba de reinicio documentada como garantía real)
  - [x] Doc técnica — ADR-0007 cierra su "Confirmación" real
  - [x] Histórico de la tarea — session log en `.claude/context/backend/backend-agent-graph-09.md`
- [x] Docs de dev / usuario final — no aplica
