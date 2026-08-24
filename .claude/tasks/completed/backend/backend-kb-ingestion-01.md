---
id: backend-kb-ingestion-01
package: backend
plan: kb-ingestion
status: completed
priority: 1
depends_on: []
estimate: 3h
actual: 3h
created: 2026-08-21
updated: 2026-08-21
---

# Puerto `EmbeddingModel` + adaptador OpenAI real + `Settings` LLM/embeddings

## Description

Hoy `Settings` (`app/core/config.py`) no declara `llm_provider`/`openai_api_key`/`chat_model`/
`embedding_model` — `.env.example` los documenta pero se ignoran (`extra="ignore"`). Tampoco existe un
puerto `EmbeddingModel`: `domain/ports/llm.py` fija `ChatModel` (solo `classify`) y su propio docstring
dice explícitamente que embeddings "no nace aquí, sin caller en este plan". `infra/llm/openai_adapter.py`
es GUIÓN puro (0 código). Esta tarea añade los 4 campos a `Settings`, crea el puerto `EmbeddingModel` en
un fichero nuevo (no en `llm.py` — decisión de `design`: partir lectura/escritura o chat/embeddings en
ficheros de puerto separados es el patrón ya usado en este repo, ver `vector.py`/`vectorstore.py`), y
crea `OpenAIEmbeddingModel` real (sobre `langchain-openai==1.5.1`, ya instalado y verificado:
`OpenAIEmbeddings.aembed_documents`).

**Fail-fast de dimensión** (hallazgo de `design-review` del plan): `embedding.vector` es `Vector(1536)`
**literal** en el ORM (`infra/db/models/kb.py`), deliberadamente NO gobernado por `settings.embedding_dim`
(hay un test de drift que lo protege — `tests/test_migration.py`). El adaptador pasa
`dimensions=settings.embedding_dim` a la API de OpenAI, pero antes comprueba
`settings.embedding_dim == EMBEDDING_DIM_LITERAL` (importado de `kb.py`) y aborta con un error claro si
no coincide — nunca deja que el `INSERT` falle a media ingesta.

## Spec

- `.claude/specs/backend/rag-ingestion.md` §5 (Embeddings, ya actualizada tras `design-review`).
- `.claude/specs/backend/casos-de-uso/CU-BE-07-ingestion-de-la-kb.md` (ver nota de alcance abajo).
- `app/core/config.py`: añade a `Settings` — `llm_provider: str = "openai"`, `openai_api_key: str = ""`
  (validación perezosa: no falla en `Settings()`, falla al primer uso real sin clave), `chat_model: str
  = "gpt-4o-mini"`, `embedding_model: str = "text-embedding-3-small"`.
- `domain/ports/embeddings.py` (nuevo): `class EmbeddingModel(Protocol)` — `async def
  embed_documents(self, texts: list[str]) -> list[list[float]]`. Sin `embed_query` (sin caller en este
  plan; lo fijará el retriever). Errores del proveedor se propagan envueltos en `PortError`.
- `infra/llm/openai_adapter.py`: añade `OpenAIEmbeddingModel` (implementa `EmbeddingModel`) sobre
  `OpenAIEmbeddings(model=settings.embedding_model, dimensions=settings.embedding_dim,
  api_key=settings.openai_api_key, max_retries=..., request_timeout=...)`; instanciación perezosa (no en
  import). `get_embedding_model()` — factory conmutable por `settings.llm_provider` (hoy solo `"openai"`
  válido; otro valor → error claro). El fail-fast de dimensión vive en el `__init__`/factory, antes de
  cualquier llamada de red.
- `OpenAIChatModel` (la otra mitad que anticipa el docstring de `openai_adapter.py`) **no** se implementa
  aquí — queda GUIÓN; anótalo en el docstring del módulo para que el plan del grafo del agente no se
  sorprenda con un fichero parcialmente real.

## Fuera de alcance

- `OpenAIChatModel` real (clasificación/generación) — plan del grafo del agente, no este.
- `EmbeddingModel.embed_query` — sin caller en este plan.
- El puerto de escritura de la KB (`KBIndexWriter`) y su adaptador pgvector — tarea `-02`.
- Usar `EmbeddingModel` desde el pipeline de ingestión — tareas `-05`/`-06`.
- Migración de columna para que `embedding.vector` deje de ser literal — fuera de este plan entero.

## Scenarios (Gherkin)

Fuente única (SDD): `CU-BE-07-ingestion-de-la-kb.md`. Esta tarea es infraestructura de puerto+adaptador
(nace sin caller directo en un escenario de usuario del CU — lo consumirá `-05`/`-06`); no cubre
ningún escenario del CU 1:1 todavía. Cubre, a nivel de **suite de contrato del puerto** (mismo criterio
que `HOW-TO-START-A-TASK.md`), con `aembed_documents` parcheado a nivel de SDK (`monkeypatch`, sin red
real — patrón nuevo en este repo, decisión de `grilling`):

```gherkin
Feature: Adaptador OpenAI de embeddings

  Scenario: Embeber documentos delega en el proveedor con la dimensión configurada
    Given un EmbeddingModel OpenAI con settings.embedding_dim igual a la dimensión literal del ORM
    When se embeben N textos
    Then se llama al proveedor con esos N textos y dimensions=settings.embedding_dim, devolviendo N vectores

  Scenario: Dimensión de config desalineada con la columna aborta antes de llamar al proveedor
    Given settings.embedding_dim distinto de EMBEDDING_DIM_LITERAL
    When se intenta construir/usar el EmbeddingModel
    Then se lanza un error claro (fail-fast) sin ninguna llamada de red

  Scenario: Fallo del proveedor se propaga envuelto en PortError
    Given un proveedor que lanza (timeout / 429 / error de API)
    When se llama a embed_documents
    Then la excepción se propaga envuelta en PortError

  Scenario: get_embedding_model con proveedor no soportado falla claro
    Given settings.llm_provider distinto de "openai"
    When se resuelve el EmbeddingModel vía la factory
    Then se lanza un error explícito (no un adaptador silenciosamente incorrecto)

  Scenario: get_embedding_model("openai") devuelve un adaptador operativo
    Given settings.llm_provider == "openai"
    When se resuelve el EmbeddingModel vía la factory
    Then el objeto devuelto implementa embed_documents y delega en el proveedor configurado

  Scenario: Importar el módulo no instancia ningún cliente ni valida nada
    Given ningún Settings construido todavía
    When se importa app.infra.llm.openai_adapter
    Then no se crea ningún cliente OpenAI ni se lanza ninguna excepción

  Scenario: openai_api_key vacía falla claro al primer uso real, no al construir Settings
    Given Settings() con openai_api_key="" (default)
    When se llama a embed_documents
    Then falla con un error claro (no una excepción cruda del SDK); Settings() en sí no había lanzado nada

  Scenario: El proveedor devuelve un número de vectores distinto al de textos enviados
    Given un proveedor (fake) que devuelve N-1 vectores para N textos
    When se llama a embed_documents
    Then se detecta el desajuste y se lanza un error claro (no un resultado desalineado en silencio)

  Scenario Outline: Fronteras del número de textos a embeber
    Given una lista de <n> textos
    When se llama a embed_documents
    Then <resultado>

    Examples:
      | n | resultado                                          |
      | 0 | lista vacía, sin llamar al proveedor                |
      | 1 | una llamada al proveedor, un vector devuelto        |
```

## Provides

- `EmbeddingModel` (Protocol, `domain/ports/embeddings.py`).
- `OpenAIEmbeddingModel` + `get_embedding_model()` (`infra/llm/openai_adapter.py`), con el fail-fast de
  dimensión ya aplicado.
- `Settings.llm_provider`/`openai_api_key`/`chat_model`/`embedding_model`.
- Consumido por la tarea `-05` (embedder).

## Definition of Done

- [x] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [x] Cada escenario tiene al menos un test (camino feliz + bordes/errores)
- [x] Todos los tests en verde (`make test`) — 771 passed
- [x] Spec cumplida; `Provides` disponible para `-05`
- [x] `ruff check` + `ruff format --check` + `mypy` strict OK
- [x] Gate de mutation `cosmic-ray` (`break: 80`, referencia no verificada en este plugin) sobre
  `embeddings.py`/`openai_adapter.py`/los campos nuevos de `config.py` — 0.00% supervivencia (36/36 KILLED)
- [x] Gate `/sdd-lint` superado (spec/CU tocados en esta tarea) — 0 ERROR, 5 AVISO (1 corregido, 4 reconocidos)
- [x] Gate de `fact-checker` superado (INCORRECTO bloquea) — 8/8 VERIFICADO
- [x] Documentación — docstrings (por qué el fail-fast, por qué `EmbeddingModel` en fichero propio, por
  qué `OpenAIChatModel` queda fuera) + session log
