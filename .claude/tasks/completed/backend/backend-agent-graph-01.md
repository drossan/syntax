---
id: backend-agent-graph-01
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

# Fix precondición: `psycopg[binary]`, `agent_confidence_threshold`, smoke-test de superficie LangGraph/LangChain

## Description

Este plan asumía (por el aviso de `HOW-TO-START-A-TASK.md`) que las deps LangGraph/LangChain no estaban
instaladas. Verificado en la sesión de planificación: **sí lo están** (`requirements.txt` compilado,
`.venv` con `langgraph==1.2.11` et al.) y el surface real (`interrupt()`, `Command(resume=)`,
`with_structured_output`, `StateGraph.compile`) coincide con el objetivo de `agent-graph.md`. Lo único
roto es `psycopg` (sin wrapper binario) — bloquea `AsyncPostgresSaver`, necesario para la tarea 07. Esta
tarea deja el terreno listo: dependencia arreglada, config nueva, y un test de regresión que blinda ese
surface verificado ante futuros bumps de dependencia.

## Spec

- `requirements.in`: añadir `psycopg[binary]` (ya es dependencia transitiva de
  `langgraph-checkpoint-postgres`; esto fija la variante binaria en vez del wrapper C ausente — no es
  una librería nueva). Recompilar `requirements.txt` (`pip-compile`) y reinstalar en `.venv`.
- `app/core/config.py`: añadir `agent_confidence_threshold: float` (`Field(default=..., ge=0.0,
  le=1.0)`), con docstring que declare explícitamente que el default es de arranque y se calibra con
  datos reales (ADR-0009: "el umbral concreto se calibra al implementar" — no hay corpus de referencia
  todavía, igual criterio que documentó `rag_estado_weight`).
- Test de regresión de superficie (p.ej. `tests/test_agent_stack_surface.py`): importa
  `langgraph.types.interrupt`/`Command`, `langgraph.checkpoint.postgres.aio.AsyncPostgresSaver`,
  `langgraph.graph.StateGraph`, `langchain_openai.ChatOpenAI.with_structured_output`, y asserta las
  firmas verificadas en esta sesión (dinámico, `resume=`, `checkpointer=`, `method='json_schema'`) —
  para que un futuro `pip-compile` que cambie el surface rompa aquí, no a medio implementar un nodo.

## Fuera de alcance

—

## Scenarios (Gherkin)

```gherkin
Feature: Precondición del stack LangGraph/LangChain

  Scenario: psycopg importa con el wrapper binario
    Given psycopg[binary] instalado en el entorno del proyecto
    When se importa AsyncPostgresSaver de langgraph.checkpoint.postgres.aio
    Then la importación no lanza ImportError

  Scenario: la superficie de LangGraph/LangChain verificada queda blindada
    Given el paquete langgraph/langchain instalado y pinado en requirements.txt
    When se inspeccionan las firmas de interrupt, Command, StateGraph.compile y with_structured_output
    Then coinciden con el surface asumido por la spec (interrupt dinámico, Command(resume=), compile(checkpointer=), method='json_schema')

  Scenario: agent_confidence_threshold tiene un default calibrable
    Given Settings() construible sin .env
    When se lee settings.agent_confidence_threshold
    Then es un float entre 0.0 y 1.0 con un default documentado como pendiente de calibración real

  Scenario Outline: agent_confidence_threshold valida sus límites
    Given AGENT_CONFIDENCE_THRESHOLD=<valor>
    When se construye Settings()
    Then <resultado>

    Examples:
      | valor | resultado        |
      | 0.0   | se acepta        |
      | 1.0   | se acepta        |
      | 1.1   | ValidationError  |
      | -0.1  | ValidationError  |
```

## Provides

- `psycopg[binary]` instalado y funcional — desbloquea `AsyncPostgresSaver` (tarea 07).
- `settings.agent_confidence_threshold` — lo consume el nodo `decide` (tarea 05) y `confidence.py` no
  lo usa directamente (recibe el umbral ya resuelto en `decide`), pero SÍ lo lee `runner.trigger()`
  (tarea 08) para pasarlo al grafo.
- Test de regresión de superficie — corre en cada `make test`; protege el resto del plan de un bump
  silencioso de LangGraph/LangChain.

## Definition of Done
- [x] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [x] Cada escenario Gherkin tiene al menos un test (camino feliz + bordes/errores)
- [x] Todos los tests en verde (83 passed en los ficheros de la tarea; suite completa `pytest -q` exit 0)
- [x] Spec cumplida; lo declarado en `Provides` queda realmente disponible para las tareas dependientes
- [x] Lint / format / typecheck OK (`ruff check` + `ruff format --check` + `mypy --strict` limpios)
- [x] Gate de mutation testing superado (`cosmic-ray`, `break: 80`) — 76 jobs, 2 survivors (2.63%), `cr-rate --fail-over 20` exit 0
- [x] Gate `sdd-lint` superado — N/A (no toca spec/CU/ADR), spot-check sin `[NECESITA ACLARACIÓN` abiertos
- [x] Gate de `fact-checker` superado — 14/15 VERIFICADO, 1 NO VERIFICABLE (mutation, reconocido), 0 INCORRECTO
- [x] **SDD** — sin cambios de spec/CU (esta tarea es infra/config; no toca `spec.md` ni ningún CU)
- [x] Documentación actualizada — tres capas:
  - [x] TSDoc en el código (docstring del nuevo campo de Settings y del test de regresión)
  - [x] Doc técnica — nota en `requirements.in` sobre por qué `psycopg[binary]`
  - [x] Histórico de la tarea — session log en `.claude/context/backend/backend-agent-graph-01.md`
- [x] Docs de dev / usuario final donde aplique (`.env.example` documentado con `AGENT_CONFIDENCE_THRESHOLD`)
