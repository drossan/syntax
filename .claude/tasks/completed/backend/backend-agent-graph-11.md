---
id: backend-agent-graph-11
package: backend
plan: agent-graph
status: done
priority: 2
depends_on: [backend-agent-graph-09]
estimate: 3h
actual: ~2h
created: 2026-08-27
updated: 2026-08-27
---

# LangSmith tracing mínimo (env config + `agent_run.langsmith_trace_url`)

## Description

Versión **mínima y explícitamente parcial** de la observabilidad LangSmith (agent-graph.md §9),
confirmada dentro de alcance con el owner tras pregunta directa en la fase de plan: variables de
entorno + población de `agent_run.langsmith_trace_url`. Sin dashboards, alerting ni instrumentación
fina — se deja anotado como follow-up explícito para una siguiente iteración, tanto aquí como en el
Registro de cambios del plan.

## Spec

- `app/core/config.py`: `langsmith_tracing: bool = False`, `langsmith_api_key: str = ""`,
  `langsmith_project: str = "syntax"` — mismo criterio que el resto de config LLM (vacío/False por
  defecto, `Settings()` construible sin `.env`).
- `LangGraphAgentRunner` (tareas 08/09): si `langsmith_tracing` está activo, envuelve la invocación del
  grafo (`ainvoke`) con el tracing de LangChain/LangSmith (vía las env vars que la librería respeta —
  `LANGCHAIN_TRACING_V2`/`LANGCHAIN_API_KEY`/`LANGCHAIN_PROJECT`, o el mecanismo equivalente verificado
  contra `langsmith==0.11.0` instalado) y recupera la URL de la traza del run actual
  (`get_current_run_tree()` o el helper equivalente del SDK instalado — **verificar contra el paquete
  real**, no asumir de memoria) para persistirla en `agent_run.langsmith_trace_url`.
- Si `langsmith_tracing=False` (o sin `langsmith_api_key`) → tracing desactivado, el campo queda `None`
  — no bloquea ni degrada el resto del flujo.

## Fuera de alcance

- Dashboards, alerting, instrumentación fina por nodo, cualquier cosa más allá de la URL de la traza en
  `agent_run.langsmith_trace_url`. **Follow-up explícito**: completar la observabilidad real (métricas
  por nodo, alertas de latencia/coste) en una iteración posterior — no en este plan.

## Scenarios (Gherkin)

```gherkin
Feature: Tracing LangSmith mínimo del run del agente

  Scenario: con tracing activo, el run queda trazado
    Given langsmith_tracing=true y una langsmith_api_key configurada
    When se ejecuta un run del agente (trigger o resume)
    Then agent_run.langsmith_trace_url queda poblado con la URL de la traza

  Scenario: sin tracing, el campo queda vacío sin romper el run
    Given langsmith_tracing=false (default)
    When se ejecuta un run del agente
    Then agent_run.langsmith_trace_url es None y el run completa con normalidad

  Scenario: fallo del cliente LangSmith no tumba el run
    Given langsmith_tracing=true pero el servicio LangSmith no responde
    When se ejecuta un run del agente
    Then el run completa igual (best-effort) y langsmith_trace_url queda None, sin propagar el fallo de tracing como error del run

  Scenario: la traza sobrevive al ciclo interrupt→resume
    Given un run que llegó a interrupt con langsmith_trace_url ya poblado tras trigger()
    When se completa resume()
    Then agent_run.langsmith_trace_url sigue siendo una URL válida que enlaza a lo ejecutado antes Y después del interrupt (no se sobrescribe con una traza desconectada)
```

## Provides

- `agent_run.langsmith_trace_url` poblado cuando el tracing está activo — cierra el guión de
  `agent-graph.md` §9 en su versión mínima acordada.

## Definition of Done
- [x] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [x] Cada escenario Gherkin tiene al menos un test (camino feliz + bordes/errores)
- [x] Todos los tests en verde
- [x] Spec cumplida; lo declarado en `Provides` queda realmente disponible para las tareas dependientes
- [x] Lint / format / typecheck OK
- [x] Gate de mutation testing superado (`cosmic-ray`, `break: 80`) — 6.00%
- [x] Gate `sdd-lint` superado (ERROR bloquea, AVISO se reconoce) — limpio
- [x] Gate de `fact-checker` superado (INCORRECTO bloquea; NO VERIFICABLE = aviso a reconocer) — 13/13 VERIFICADO
- [x] **SDD** — sin CU propio (observabilidad transversal); referencia agent-graph.md §9
- [x] Documentación actualizada — tres capas:
  - [x] TSDoc en el código (settings nuevas, punto donde se envuelve el tracing)
  - [x] Doc técnica — nota explícita de "versión mínima, follow-up pendiente" en `agent-graph.md` §9
  - [x] Histórico de la tarea — session log en `.claude/context/backend/backend-agent-graph-11.md`
- [x] Docs de dev / usuario final — `.env.example` con las 3 variables nuevas de LangSmith
