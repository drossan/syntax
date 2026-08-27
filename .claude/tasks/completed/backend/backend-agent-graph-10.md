---
id: backend-agent-graph-10
package: backend
plan: agent-graph
status: done
priority: 1
depends_on: [backend-agent-graph-09]
estimate: 3h
actual: ~3h
created: 2026-08-27
updated: 2026-08-27
---

# Wiring: sustituir `StubAgentRunner` por el adaptador real en `app/core/deps.py`

## Description

Última pieza: cablear `LangGraphAgentRunner` (tareas 08/09) en `app/core/deps.py`, en los dos sitios
donde hoy se construye `StubAgentRunner` (`get_agent_service` y `get_approval_service`), sin tocar
`agent_service.py`, `approval_service.py` ni los routers `agent.py`/`approvals.py` (ya reales y ya
testeados contra el stub — deben seguir pasando igual contra el adaptador real, mismo contrato de
puerto). El comportamiento nuevo ya está probado en 08/09; aquí se verifica que el contrato HTTP
completo sigue intacto tras el swap.

## Spec

- `app/core/deps.py`: reemplazar las dos instancias de `StubAgentRunner(...)` por
  `LangGraphAgentRunner(...)` con sus dependencias (`ChatModel` vía `get_chat_model`, `Retriever`
  construido con `get_embedding_model`/`KBIndexWriter` ya existentes, `MessageRepository`,
  `TenantRepository`, `AgentRunRepository`, `settings.agent_confidence_threshold`, `settings.rag_*`).
  Import de `app.infra.agent_runner.stub` se retira si ya no tiene otro consumidor.
- Test de integración HTTP (contra Postgres real, TestClient/httpx): `POST /tickets/{id}/ai-draft` →
  `POST /approvals/{id}/approve` de punta a punta produce un `Message(public)` real — mismo flujo que
  ya cubren 08/09 a nivel de adaptador, aquí a nivel de contrato HTTP completo (routers + DI real).

## Fuera de alcance

- No se modifica ningún router, schema ni servicio de dominio — solo el wiring de `deps.py`.

## Scenarios (Gherkin)

```gherkin
Feature: Swap de StubAgentRunner por el adaptador real

  Scenario: el flujo HTTP completo funciona contra el runner real
    Given el backend arrancado con LangGraphAgentRunner wireado en deps.py
    When se dispara POST /tickets/{id}/ai-draft y se aprueba el draft resultante vía POST /approvals/{id}/approve
    Then se publica un Message(public) real y GET /agent-runs/{id} refleja status=succeeded

  Scenario: el contrato de capacidades no cambia
    Given un subject sin la capacidad agent.trigger
    When intenta POST /tickets/{id}/ai-draft
    Then sigue recibiendo 403, igual que contra el stub (el swap no toca RBAC)

  Scenario: un fallo de construcción de dependencias se detecta al arrancar, no en el primer request
    Given una configuración inválida para get_chat_model (p.ej. llm_provider no soportado)
    When arranca la app
    Then el fallo es visible en el arranque (o el primer smoke-check), no un 500 opaco en el primer POST /tickets/{id}/ai-draft
```

## Provides

- Backend con el flujo IA end-to-end real y accesible por HTTP — cierra el objetivo 4 del plan.

## Definition of Done
- [x] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [x] Cada escenario Gherkin tiene al menos un test (camino feliz + bordes/errores)
- [x] Todos los tests en verde
- [x] Spec cumplida; lo declarado en `Provides` queda realmente disponible para las tareas dependientes
- [x] Lint / format / typecheck OK
- [x] Gate de mutation testing superado (`cosmic-ray`, `break: 80`) — 14.89%
- [x] Gate `sdd-lint` superado (ERROR bloquea, AVISO se reconoce) — limpio
- [x] Gate de `fact-checker` superado (INCORRECTO bloquea; NO VERIFICABLE = aviso a reconocer) — 11/11 VERIFICADO
- [x] **SDD** — sin cambios de spec/CU (wiring puro, comportamiento ya cubierto por CU-BE-05/06 vía 05-09)
- [x] Documentación actualizada — tres capas:
  - [x] TSDoc en el código (comentario en `deps.py` explicando el swap y sus dependencias)
  - [x] Doc técnica — actualizar `agent.py`/`approvals.py` docstrings que hoy dicen "el grafo real no
    existe todavía" (ya no es cierto)
  - [x] Histórico de la tarea — session log en `.claude/context/backend/backend-agent-graph-10.md`
- [x] Docs de dev / usuario final — no aplica
