---
id: backend-agent-graph-08
package: backend
plan: agent-graph
status: done
priority: 1
depends_on: [backend-agent-graph-06, backend-agent-graph-07]
estimate: 8h
actual: ~4h
created: 2026-08-27
updated: 2026-08-27
---

# `app/agents/runner.py::trigger/run` — ejecuta hasta interrupt o respond; persiste `AgentRun`

## Description

Primera mitad del adaptador real de `AgentRunner` (ADR-0007, núcleo de riesgo): compila el grafo
(tarea 06) con el checkpointer (tarea 07) y lo invoca desde cero (`trigger`). Cubre el camino
**auto** (sin HITL) end-to-end y el camino que llega a `interrupt()` y queda pendiente. El `resume()`
tras la decisión humana es la tarea 09. Sustituye funcionalmente a `StubAgentRunner`, pero el wiring en
`app/core/deps.py` (swap real) es la tarea 10 — aquí el adaptador se construye y testea de forma
aislada.

## Spec

**Hallazgo de `scenario-coverage` (verificado contra código real, no hipótesis)**: ninguna tarea previa
asignaba (1) quién crea la `ApprovalTask(pending)` al interrumpir — `approval_service.py` (ya real) no
la crea; el nodo `decide` (tarea 05) es explícitamente puro sin puertos — ni (2) cómo se persiste
`confidence`/`sources`/`error`/`escalated`/`finished_at`/`langsmith_trace_url` — `AgentRunRepository`
(`app/domain/ports/repositories.py`) solo expone `update_status(agent_run_id, status)`. Confirmado con
el owner: se cierran los dos AQUÍ, ampliando el alcance de esta tarea (no una tarea nueva).

- **Extensión de puertos** (parte de esta tarea, no de una tarea aparte):
  - `AgentRunRepository` gana un método nuevo, p.ej. `update_result(agent_run_id, *, status,
    confidence=None, sources=None, error=None, escalated=None, finished_at=None,
    langsmith_trace_url=None) -> AgentRun` — `update_status` se conserva tal cual para sus llamantes
    actuales (`StubAgentRunner`/tests existentes no se tocan). Implementar en
    `app/infra/db/repositories/agent_run.py` (adaptador SQL real).
  - El constructor de `LangGraphAgentRunner` añade `ApprovalRepository` a sus dependencias (puerto YA
    completo, `ApprovalRepository.add()` ya existe — no requiere extensión).
- `class LangGraphAgentRunner(AgentRunner)` (implementa `app.domain.ports.agent_runner.AgentRunner`):
  - Constructor recibe los puertos/config que `build_graph()` necesita (tarea 06) + `TenantRepository`
    (para resolver `auto_approve`, decisión de `grilling` #7) + `AgentRunRepository` +
    `ApprovalRepository` (nuevo, ver arriba). Construye el grafo (barato, sin I/O) en su propio
    `__init__` — no es un singleton de proceso (evita capturar un `MessageRepository` con sesión de una
    request en un objeto de vida más larga, decisión #4).
  - `async def trigger(tenant_id, ticket_id, run_seq, thread_id) -> AgentRun`: resuelve
    `tenant.auto_approve` (`NotFound`/error controlado si el tenant no resuelve — ver escenario de
    borde abajo), compila `build_graph(...).compile(checkpointer=get_checkpointer())`, invoca
    (`ainvoke`) con el estado inicial (`auto_approve` incluido) y `config={"configurable": {"thread_id":
    thread_id}}`.
    - Si el resultado trae `__interrupt__` → **crea la `ApprovalTask(status=pending, draft_body=
      state["draft_response"], ...)` vía `ApprovalRepository.add()`** (mapeo 1:1 interrupt↔ApprovalTask,
      ADR-0007) y persiste `AgentRun` (`update_result(status=running, confidence=..., sources=...)`).
    - Si no hay interrupt (auto o escalado sin HITL) → `update_result(status=succeeded, confidence=...,
      sources=..., escalated=..., finished_at=...)`, sin `ApprovalTask`.
  - **Fallo del LLM a mitad de run** (CU-BE-06 escenario 6): cualquier `PortError` de un nodo →
    `update_result(status=failed, error=str(exc), finished_at=...)`, sin `ApprovalTask` (no se llegó a
    interrupt) — error controlado, nunca la excepción cruda propagada al router.
  - `resume()` de esta tarea es un placeholder que delega en la tarea 09 (no se implementa aquí).

## Fuera de alcance

- `resume()` (Command(resume=), reinicio a mitad de run) — tarea 09.
- Wiring en `app/core/deps.py` (swap de `StubAgentRunner`) — tarea 10.
- Rate-limiting multi-proceso de `ai-draft` — ya resuelto/aceptado en el plan `domain-services`, no se
  toca aquí.

## Scenarios (Gherkin)

Criterios de aceptación (Gherkin) en el caso de uso —
[CU-BE-06 — Draft IA y aprobación HITL](../../../specs/backend/casos-de-uso/CU-BE-06-draft-ia-y-aprobacion-hitl.md),
escenarios cubiertos por esta tarea: "Fallo del LLM deja el sistema consistente" (completo) y la mitad
de "1. El grafo llega a decide con requires_approval=true; llama a interrupt()... crea approval_task"
(la creación del `AgentRun` en estado que permita esa `ApprovalTask`; la reanudación es la tarea 09).

Escenario adicional (borde no cubierto por el CU a este grano):

```gherkin
Feature: Disparo del run del agente (sin HITL / camino auto)

  Scenario: un run auto_approve con confianza suficiente termina en succeeded sin ApprovalTask
    Given un tenant con auto_approve=true y un ticket cuyo contexto recuperado es suficiente
    When se dispara trigger() para ese ticket
    Then el AgentRun resultante queda succeeded, se publicó un mensaje público, y NO se creó ninguna ApprovalTask

  Scenario: un run que llega al interrupt crea la ApprovalTask pendiente
    Given un tenant con auto_approve=false
    When se dispara trigger() para un ticket con contexto suficiente
    Then el AgentRun queda running (o el estado que corresponda a "pendiente de aprobación") Y existe una ApprovalTask(status=pending) ligada a ese agent_run_id con el draft_body correcto

  Scenario: el tenant no resuelve al disparar el run
    Given un tenant_id que TenantRepository.get() no encuentra
    When se dispara trigger() para ese ticket
    Then el AgentRun queda failed con un error controlado, no una excepción cruda

  Scenario: update_result persiste todos los campos del resultado, no solo el status
    Given un run que termina succeeded con confidence, sources y escalated calculados
    When se persiste el resultado
    Then AgentRunRepository.get() devuelve esos mismos valores, no solo el status actualizado
```

## Provides

- `LangGraphAgentRunner.trigger()` — funcional para el camino auto y para dejar un run pendiente de
  aprobación, con su `ApprovalTask` creada. `resume()` lo completa la tarea 09 antes de que el
  adaptador sea sustituible en `deps.py` (tarea 10).
- `AgentRunRepository.update_result(...)` (puerto + adaptador SQL) — lo reutilizan las tareas 09 y 11
  para persistir el resultado del `resume()` y `langsmith_trace_url` respectivamente.

## Definition of Done
- [x] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [x] Cada escenario Gherkin tiene al menos un test (camino feliz + bordes/errores)
- [x] Todos los tests en verde (6 runner + 10 checkpointer + 16 agent_run repo; suite completa exit 0)
- [x] Spec cumplida; lo declarado en `Provides` queda realmente disponible para las tareas dependientes
- [x] Lint / format / typecheck OK
- [x] Gate de mutation testing superado (`cosmic-ray`, `break: 80`) — runner.py 9.52%, agent_run.py 6.12%, checkpointer.py 0.00% (los 3 bajo el umbral 20%)
- [x] Gate `sdd-lint` superado — N/A (enlaza CU sin copiar Gherkin), spot-check sin `[NECESITA ACLARACIÓN`
- [x] Gate de `fact-checker` superado — 12/14 VERIFICADO exacto, 1 con matiz (contención de BD en la propia verificación), 1 INCORRECTO en una cifra de mutation (corregida y re-verificada, sigue bajo el umbral)
- [x] **SDD** — enlaza CU-BE-06 (sin copiar su Gherkin)
- [x] Documentación actualizada — tres capas:
  - [x] TSDoc en el código (`LangGraphAgentRunner`, `trigger`, manejo de fallo del LLM)
  - [x] Doc técnica — `app/agents/runner.py` deja de ser guión
  - [x] Histórico de la tarea — session log en `.claude/context/backend/backend-agent-graph-08.md`
- [x] Docs de dev / usuario final — no aplica
