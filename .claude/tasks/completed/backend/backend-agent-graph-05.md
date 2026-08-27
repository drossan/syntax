---
id: backend-agent-graph-05
package: backend
plan: agent-graph
status: done
priority: 1
depends_on: [backend-agent-graph-02, backend-agent-graph-03, backend-agent-graph-04]
estimate: 6h
actual: ~3h
created: 2026-08-27
updated: 2026-08-27
---

# `app/agents/state.py` + nodos (`classify/retrieve/grade/generate/decide/trim/respond`)

## Description

Implementa el estado del grafo y los 7 nodos que lo componen (el guión previo de `nodes/__init__.py`
solo listaba 6 — `respond` se añadió al alcance de esta tarea en `design-review`, ajuste 9). Cada nodo
es una **factory-closure** (`make_<nombre>_node(puerto...) -> Callable[[State], Awaitable[State]]`,
decisión de `grilling`): recibe sus puertos por inyección de constructor, sin importar infra
directamente. `build_graph()` (tarea 06) los ensambla; aquí solo se construyen y testean de forma
aislada, con mocks de puertos.

## Spec

- `app/agents/state.py` — `HelpdeskState` (TypedDict), campos: `messages: Annotated[list,
  add_messages]`, `tenant_id: UUID`, `ticket_id: UUID`, `auto_approve: bool` (resuelto una vez por
  `runner.trigger()`, tarea 08 — decisión de `grilling` #7, sin `TenantRepository` en `decide`),
  `classification: Classification | None`, `retrieved: list[RankedHit]`, `grade: Grade | None`,
  `confidence: float | None`, `requires_approval: bool`, `draft_response: str | None`, `human_note: str
  | None`.
- `app/agents/nodes/classify.py` — `make_classify_node(chat_model: ChatModel)`: delega en
  `app.domain.services.classification.classify()` (YA REAL, plan `domain-services`); fija
  `state["classification"]`. **Aislamiento de prompt-injection** (spec §8, hallazgo
  `scenario-coverage`): el texto del ticket se pasa como contenido de un turno de usuario delimitado,
  nunca concatenado al system-prompt — verificar con un test que un ticket con instrucciones embebidas
  ("ignora las instrucciones anteriores...") no cambia el comportamiento del nodo.
- `app/agents/nodes/retrieve.py` — `make_retrieve_node(retriever: Retriever, top_k: int)`: si
  `classification.dominio` es `None` → `retriever.retrieve(query, top_k=top_k, domain=None)`
  (fallback, CU-BE-05 1a); si no, filtra por ese dominio. Fija `state["retrieved"]`.
- `app/agents/nodes/grade.py` — `make_grade_node(chat_model: ChatModel)`: `Grade{suficiente: bool,
  motivo: str}` (SIN `relevante` — ajuste `design-review` #12, sin consumidor real); llama a
  `chat_model.grade(prompt, Grade)` con el contexto recuperado. Fija `state["grade"]` y
  `state["confidence"]` (vía `compute_confidence`, tarea 02).
- `app/agents/nodes/generate.py` — `make_generate_node(chat_model: ChatModel)`: si `state["grade"]` es
  `None` o `grade.suficiente=False` → `draft_response=None`, `human_note=grade.motivo if grade else
  "contexto insuficiente"` (NO genera, CU-BE-05 escenario 3; `grade=None` no debe producir
  `AttributeError`, hallazgo `scenario-coverage`); si no, redacta el draft fiel al contexto **en el
  idioma del ticket** (spec §9, "Refuerzo" nombrado en agent-graph.md §10 — detecta el idioma del texto
  del ticket; la KB está en español, el prompt indica traducir si difiere) y adjunta citas
  (`build_citations`, tarea 03). **Límites de salida** (spec §8, hallazgo `scenario-coverage`): el
  prompt fija un límite de longitud/formato del draft — verificar que una respuesta del LLM que lo
  excede se trunca o se rechaza de forma controlada, no se publica sin límite.
- `app/agents/nodes/decide.py` — `make_decide_node(confidence_threshold: float)`: **puro** (no captura
  ningún puerto, solo el umbral): `requires_approval = (not state["auto_approve"]) or
  (state["confidence"] or 0.0) < confidence_threshold or state["grade"] is None or not
  state["grade"].suficiente`. Si `requires_approval` es `True`, llama a `langgraph.types.interrupt(...)`
  **inline, dentro de este mismo nodo** con el payload de revisión (draft/citas/motivo), y guarda el
  valor de retorno (la decisión del humano tras `Command(resume=)`) en `state["human_decision"]` —
  clarificación de implementación (no cambia el alcance de ficheros ya acordado en el plan): un único
  nodo `decide` concentra el cálculo de `requires_approval` Y la llamada a `interrupt()`, en vez de un
  nodo `interrupt` separado — la durabilidad la da compilar con el checkpointer (tarea 07/08), no la
  estructura del nodo. Edge `decide → respond` es **incondicional**.
- `app/agents/nodes/trim.py` — `make_trim_node(max_tokens: int)`: aplica `trim_messages` sobre
  `state["messages"]` antes de invocar el LLM (recorta hilos largos por reaperturas).
- `app/agents/nodes/respond.py` — `make_respond_node(messages_repo: MessageRepository)`: si
  `requires_approval=False` → publica `Message(visibility=public, is_ai_draft=True,
  body=draft_response, author_id=None)` directo. Si `requires_approval=True` → lee
  `state["human_decision"]` (fijado por `decide` al reanudar): `rejected` → no publica nada, conserva
  `human_note`; `approved`/`edited` → publica con `draft_body`/`final_body` respectivamente. Usa
  `MessageRepository.add()` (puerto YA existente, mismo patrón que `app/api/v1/routers/messages.py`).

## Fuera de alcance

- `app/agents/tools.py` (`@tool`): ningún nodo requiere tools externas.

## Scenarios (Gherkin)

Criterios de aceptación (Gherkin) en el caso de uso — esta tarea implementa, a nivel de nodo/unidad,
los escenarios de:
- [CU-BE-05 — Clasificación y retrieval RAG](../../../specs/backend/casos-de-uso/CU-BE-05-clasificacion-y-retrieval-rag.md)
  (escenarios: clasificación fija dominio, fallback sin filtro, contexto insuficiente escala, draft
  participan ponderados, la respuesta cita sus fuentes).
- [CU-BE-06 — Draft IA y aprobación HITL](../../../specs/backend/casos-de-uso/CU-BE-06-draft-ia-y-aprobacion-hitl.md)
  (escenario "Aprobación emite la respuesta al cliente" y "Edición envía el texto corregido" y
  "Rechazo no publica nada al cliente" — la parte de comportamiento de `respond`, sin la persistencia
  real del checkpointer, que es la tarea 07/08/09).

Además, escenarios de unidad propios de `decide`, `generate` y `trim` (bordes no cubiertos por el CU a
este nivel de grano; los de `trim` y el borde exacto de `decide` son hallazgos de `scenario-coverage` —
ningún escenario los cubría antes):

```gherkin
Feature: Nodo decide — puerta HITL

  Scenario: auto_approve=false siempre exige aprobación
    Given un run con auto_approve=false y confianza por encima del umbral
    When se evalúa decide
    Then requires_approval es true

  Scenario: confianza baja exige aprobación aunque auto_approve sea true
    Given un run con auto_approve=true y confianza por debajo del umbral configurado
    When se evalúa decide
    Then requires_approval es true

  Scenario: confianza suficiente y auto_approve=true no exige aprobación
    Given un run con auto_approve=true, grade.suficiente=true y confianza por encima del umbral
    When se evalúa decide
    Then requires_approval es false

  Scenario: confianza exactamente igual al umbral cuenta como suficiente
    Given auto_approve=true, grade.suficiente=true y confidence == confidence_threshold exactamente
    When se evalúa decide
    Then requires_approval es false

Feature: Nodo generate — bordes

  Scenario: grade ausente no rompe generate
    Given state["grade"] es None (no debería ocurrir por el routing normal, pero el nodo se testea aislado)
    When se invoca generate
    Then no lanza AttributeError; devuelve draft_response=None con un human_note por defecto

  Scenario: generate responde en el idioma del ticket
    Given un ticket redactado en inglés y contexto recuperado en español (KB en español)
    When generate redacta el draft
    Then el draft_response está en inglés, no en español

  Scenario: un draft que excede el límite de salida se controla
    Given una respuesta del LLM que supera el límite de longitud configurado
    When generate la procesa
    Then el draft resultante respeta el límite (truncado o rechazado de forma controlada), nunca se propaga sin límite

Feature: Nodo trim — recorte de hilos largos

  Scenario: un hilo largo se recorta antes de invocar el LLM
    Given state.messages con más mensajes que el límite configurado (max_tokens)
    When se aplica trim
    Then el número de mensajes/tokens resultante respeta el límite, conservando los más recientes

  Scenario: un hilo vacío o de un solo mensaje no falla
    Given state.messages con 0 o 1 mensajes
    When se aplica trim
    Then el estado no cambia y no se lanza excepción
```

## Provides

- `HelpdeskState` — lo consume `build_graph()` (tarea 06).
- 7 factories de nodos (`make_*_node`) — las ensambla `build_graph()` (tarea 06).

## Definition of Done
- [x] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor (excepto `grade.py`, ver nota de desviación en el session log)
- [x] Cada escenario Gherkin tiene al menos un test (camino feliz + bordes/errores)
- [x] Todos los tests en verde (40 passed en la tarea; suite completa `pytest -q` exit 0)
- [x] Spec cumplida; lo declarado en `Provides` queda realmente disponible para las tareas dependientes
- [x] Lint / format / typecheck OK
- [x] Gate de mutation testing superado (`cosmic-ray`, `break: 80`) — 2.13% survivors (3 mutantes equivalentes `is`→`==` sobre enum)
- [x] Gate `sdd-lint` superado — N/A (enlaza CU sin copiar Gherkin), spot-check sin `[NECESITA ACLARACIÓN`
- [x] Gate de `fact-checker` superado — 14/14 VERIFICADO, 0 INCORRECTO
- [x] **SDD** — enlaza CU-BE-05/CU-BE-06 (sin copiar su Gherkin); sin cambios de spec/CU nuevos
- [x] Documentación actualizada — tres capas:
  - [x] TSDoc en el código (cada `make_*_node` documenta puerto, contrato y anti-patrón evitado)
  - [x] Doc técnica — corregido `app/agents/nodes/__init__.py` (7 nodos, incl. `respond`)
  - [x] Histórico de la tarea — session log en `.claude/context/backend/backend-agent-graph-05.md`
- [x] Docs de dev / usuario final — no aplica
