---
id: backend-agent-graph-04
package: backend
plan: agent-graph
status: pending
priority: 1
depends_on: []
estimate: 3h
actual:
created: 2026-08-27
updated: 2026-08-27
---

# Extender `ChatModel` (`generate`/`grade`) + `structured.py` + `OpenAIChatModel` completo

## Description

`app/domain/ports/llm.py` recortó `ChatModel` a solo `classify` porque `generate`/`grade` no tenían
caller (plan `domain-services`, tarea 06). Este plan (agent-graph) es su primer consumidor real: los
nodos `grade`/`generate` (tarea 05) necesitan estos dos métodos. Esta tarea los añade al puerto e
implementa `OpenAIChatModel`, hoy pura guión en `app/infra/llm/openai_adapter.py`, con las tres
operaciones (`classify` ya definida por el puerto, `grade`, `generate`).

## Spec

- `app/domain/ports/llm.py` — `ChatModel` (Protocol) gana:
  - `async def grade(self, prompt: str, schema: type[BaseModel]) -> BaseModel` — structured output
    genérico, mismo patrón que `classify` (reutilizable si en el futuro hay más salidas tipadas).
  - `async def generate(self, prompt: str) -> str` — texto libre (el draft), sin schema.
  - Ambos documentan `:raises app.domain.errors.PortError:` igual que `classify`.
- `app/infra/llm/structured.py` — helper interno del adaptador (NO parte del puerto de dominio):
  `async def structured_output(chat: ChatOpenAI, prompt: str, schema: type[BaseModel]) -> BaseModel`,
  envuelve `chat.with_structured_output(schema, method="json_schema").ainvoke(prompt)`.
- `app/infra/llm/openai_adapter.py` — `OpenAIChatModel(ChatModel)`:
  - Cliente `ChatOpenAI` perezoso (mismo patrón que `OpenAIEmbeddingModel._get_client`, sin validar
    `openai_api_key` en `__init__`), modelo de `settings.chat_model`.
  - `classify(text, schema)` → `structured_output(...)`.
  - `grade(prompt, schema)` → `structured_output(...)`.
  - `generate(prompt)` → `chat.ainvoke(prompt)`, devuelve `.content` como `str`.
  - Cualquier excepción del SDK se envuelve en `PortError` (mismo criterio que
    `OpenAIEmbeddingModel.embed_query`).
- `get_chat_model(settings: Settings) -> ChatModel` — factory conmutable por `settings.llm_provider`,
  mismo criterio que `get_embedding_model`.
- Tests: contrato a nivel unit, **mockeando** el cliente `ChatOpenAI`/`with_structured_output` (sin red
  real) — mismo criterio que ya sigue `OpenAIEmbeddingModel` con `OpenAIEmbeddings`.

## Fuera de alcance

- `app/agents/tools.py` (`@tool`): ningún nodo de Fase 1 requiere tools externas — no se toca en esta
  tarea ni en ninguna otra del plan.

## Scenarios (Gherkin)

```gherkin
Feature: Adaptador OpenAI del puerto ChatModel

  Scenario: classify delega en structured output
    Given un texto de ticket y un schema Classification
    When se llama a OpenAIChatModel.classify
    Then el cliente OpenAI recibe la petición con with_structured_output(schema) y se devuelve una instancia validada

  Scenario: grade delega en structured output
    Given un prompt de evaluación y un schema Grade
    When se llama a OpenAIChatModel.grade
    Then el cliente OpenAI recibe la petición con with_structured_output(schema) y se devuelve una instancia validada

  Scenario: generate devuelve texto libre
    Given un prompt de redacción
    When se llama a OpenAIChatModel.generate
    Then se devuelve el contenido de texto de la respuesta del modelo

  Scenario: fallo del proveedor se envuelve en PortError
    Given que el cliente OpenAI lanza una excepción (timeout, error de API)
    When se llama a classify, grade o generate
    Then la excepción se propaga como app.domain.errors.PortError, nunca la excepción cruda del SDK

  Scenario: una salida que no valida contra el schema también es PortError
    Given que el modelo devuelve algo que with_structured_output no puede mapear al schema pedido
    When se llama a classify o grade
    Then el fallo de validación se envuelve en PortError, distinguible en el mensaje de un fallo de red/API

  Scenario: la inicialización es perezosa, sin openai_api_key configurada
    Given Settings() sin openai_api_key
    When se construye OpenAIChatModel
    Then la construcción no falla; el fallo (si lo hay) ocurre solo al primer uso real (classify/grade/generate)

  Scenario: get_chat_model solo soporta el proveedor configurado
    Given settings.llm_provider distinto de "openai"
    When se llama a get_chat_model
    Then se lanza PortError con el proveedor no soportado
```

## Provides

- `ChatModel.grade`/`ChatModel.generate` (puerto extendido) — los consumen los nodos `grade`/`generate`
  (tarea 05).
- `OpenAIChatModel` + `get_chat_model()` — adaptador real inyectable en `app/core/deps.py` (tarea 10).

## Definition of Done
- [ ] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [ ] Cada escenario Gherkin tiene al menos un test (camino feliz + bordes/errores)
- [ ] Todos los tests en verde
- [ ] Spec cumplida; lo declarado en `Provides` queda realmente disponible para las tareas dependientes
- [ ] Lint / format / typecheck OK
- [ ] Gate de mutation testing superado (`cosmic-ray`, `break: 80`)
- [ ] Gate `sdd-lint` superado (ERROR bloquea, AVISO se reconoce)
- [ ] Gate de `fact-checker` superado (INCORRECTO bloquea; NO VERIFICABLE = aviso a reconocer)
- [ ] **SDD** — sin CU propio (adaptador/puerto interno); referencia agent-graph.md §4/§9 en docstrings
- [ ] Documentación actualizada — tres capas:
  - [ ] TSDoc en el código (`ChatModel.grade`/`generate`, `OpenAIChatModel`, `structured_output`)
  - [ ] Doc técnica — actualizar el docstring de `openai_adapter.py` (ya no es "solo la mitad real")
  - [ ] Histórico de la tarea — session log en `.claude/context/backend/backend-agent-graph-04.md`
- [ ] Docs de dev / usuario final — no aplica (sin superficie HTTP nueva)
