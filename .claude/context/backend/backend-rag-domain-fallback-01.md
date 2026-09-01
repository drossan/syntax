# Session log — backend-rag-domain-fallback-01

## 2026-08-31

### TDD

- **`app/rag/retriever.py`**: Red primero (`test_rag_retriever.py`, 7 tests nuevos para
  `embed_query`/`search`) → Green: `Retriever.retrieve()` partido en `embed_query(query)` +
  `search(vector, ...)`, `retrieve()` como envoltorio fino. 19/19 tests en verde (12 preexistentes +
  7 nuevos), sin cambio de comportamiento para los llamantes existentes.
- **`app/agents/nodes/retrieve.py`**: Red primero (`test_node_retrieve.py`, reescrito completo — el
  `_FakeRetriever` anterior solo tenía `.retrieve()`, incompatible con la nueva lógica que llama a
  `embed_query`/`search` por separado) → Green: lógica del fallback incondicional (siempre 2 búsquedas
  cuando `domain is not None`), comparación de `max(hit.score)` con margen estricto (`>`), log
  `structlog` en toda comparación. 18 tests en verde (17 + 1 añadido tras el mutation gate).
- Bug de fixture en el primer intento del test de frontera exacta del margen: `0.55 - 0.50` en float64
  da `0.050000000000000044`, NO `0.05` exacto — el test fallaba por precisión flotante, no por un bug
  real del `>` estricto (que sí es correcto). Corregido con valores exactos en binario (`0.625 - 0.5 ==
  0.125` exacto).
- Plumbing (`graph.py`/`runner.py`/`deps.py`) y `Settings.rag_domain_fallback_margin` (default `0.05`,
  mismo patrón que `agent_confidence_threshold`) añadidos sin incidencias.
- **Fakes de `Retriever` en otros ficheros de test rotos** (`test_graph.py`, `test_runner.py`,
  `test_router_agent.py`, `test_router_tickets.py`): todos tenían solo `.retrieve()`, no
  `embed_query`/`search` — actualizados con ambos métodos (comportamiento idéntico: devuelven los mismos
  hits fijos independientemente de `domain`, así que el fallback nunca se dispara en esos tests, delta=0,
  sin cambio de resultado). `_SpyRetriever` de `test_router_agent.py` movió su captura de `top_k` de
  `retrieve()` a `search()` (el nodo ya no llama a `retrieve()`).
- Suite completa: 1388 tests en verde. `ruff check`/`ruff format --check`/`mypy app` (strict) limpios.

### Mutation testing (cosmic-ray, referencia no verificada — banner de la skill)

- `retrieve.py` (`--module-path` acotado, `test-command` → `test_node_retrieve.py`): primera pasada
  96.88% (1 survivor, `NumberReplacer` mutando el `default=0.0` de `_max_score` a `-1.0`) — indistinguible
  de `0.0` porque los scores reales nunca son negativos (clamp documentado en `app/infra/vector`).
  Añadido un test con un hit real de score `0.0` exacto (válido) que sí distingue ambos valores. Segunda
  pasada: **100%**, 0 survivors.
- `retriever.py`: 95.96% (4 survivors), todos el mismo patrón: el marcador `*,` (keyword-only) en las
  firmas de `__init__`/`retrieve`/`search` mutado a `/,` o `|,` (artefacto de `parso`/`cosmic-ray` sobre
  separadores de parámetros, no una mutación de lógica de negocio real) — **documentados como mutantes
  equivalentes**, no perseguidos: todas las llamadas del repo usan argumentos con nombre, así que el
  cambio de keyword-only a positional-only/regular no tiene ningún efecto observable.
- `cosmic-ray.toml` restaurado a su estado original del repo (`module-path=app/agents/runner.py`) tras
  cada pasada; `session.sqlite` borrado, sin residuos untracked.

### Verificación manual contra el backend real

Script ad-hoc (`classify`→`retrieve`(fijo)→`grade`→`generate`, real OpenAI + Postgres/pgvector, sin
persistir nada) contra los 8 tickets reales de la investigación previa:

- **3 casos rotos → los 3 generan draft ahora.** Dos dispararon el fallback explícitamente
  (`used_fallback=True`, dominios `authoring_and_editor`→sin filtro y `rendering_and_publishing`→sin
  filtro); el tercero clasificó correctamente en esta ejecución (`search_ai_and_llms`, sin necesidad de
  fallback) — consistente con la no-determinismo de `classify()` ya documentado, no un fallo del fix.
- **5 casos que ya funcionaban → los 5 siguen generando draft, con `used_fallback=False` en los 5.**
  Ningún caso correctamente clasificado sufrió degradación — confirma el control de regresión pedido por
  `design-review` #2.

### Gates

- `sdd-lint`: mecánico limpio (sin `[NECESITA ACLARACIÓN`, IDs bien formados, estado MADR válido).
  Semántico (subagente fresco): 1 ERROR (ADR-0019 no referenciado de vuelta desde CU-BE-05/
  agent-graph.md — trazabilidad unidireccional) + 2 AVISOS de disciplina Gherkin (un escenario mezclaba
  2 comportamientos; dos `Given` usaban el nombre literal del setting en vez de un término de negocio).
  Los 3 corregidos: referencias a ADR-0019 añadidas en ambas cabeceras + inline; escenario dividido;
  redacción de los `Given` cambiada a "margen de mejora configurado"; el caso de frontera exacta
  fusionado como fila del `Scenario Outline` existente.
- `fact-checker`: 9/10 VERIFICADO, 1 INCORRECTO (`test_node_retrieve.py` sin formatear tras un test
  añadido DESPUÉS del `ruff format` inicial — el fichero real no coincidía con la afirmación de estar
  limpio). Corregido (`ruff format`) y reverificado: `ruff check`/`ruff format --check` limpios.

## Cierre

- DoD completa. Tarea movida a `completed/`, `status: done`, `[x]` en el plan.
- Ficheros tocados: `backend/app/rag/retriever.py`, `backend/app/agents/nodes/retrieve.py`,
  `backend/app/agents/graph.py`, `backend/app/agents/runner.py`, `backend/app/core/deps.py`,
  `backend/app/core/config.py`, `backend/tests/test_rag_retriever.py`,
  `backend/tests/test_node_retrieve.py`, `backend/tests/test_graph.py`, `backend/tests/test_runner.py`,
  `backend/tests/test_router_agent.py`, `backend/tests/test_router_tickets.py`,
  `.claude/specs/backend/agent-graph.md`, `.claude/specs/backend/casos-de-uso/CU-BE-05-*.md`.
- Última (y única) tarea del plan `rag-domain-fallback` — el plan se cierra a continuación.
- Follow-up para el owner (ya documentado en la investigación previa, no de esta tarea): los 6 huecos
  de contenido real de la KB detectados en la investigación siguen sin resolver — no son un problema de
  código.
