---
id: backend-rag-domain-fallback-01
package: backend
plan: rag-domain-fallback
status: active
priority: 1
depends_on: []
estimate: 4h
actual:
issue:
created: 2026-08-31
updated: 2026-08-31
---

# Fallback de retrieval por dominio equivocado, incondicional cuando hay dominio asignado

## Description

Investigación en vivo (backend real, Postgres): 3 de 9 tickets con draft vacío son fallos de
clasificación de dominio recuperables por código — el documento correcto existe en la KB, pero
`retrieve` (`app/agents/nodes/retrieve.py`) solo cae a "sin filtro de dominio" cuando
`classification.dominio is None` (CU-BE-05 1a), nunca cuando el dominio SÍ se asignó pero está
equivocado (CU-BE-05 1c, nueva). Diseño completo, con el trade-off de latencia vs. recall justificado,
en [ADR-0019](../../../specs/adr/0019-fallback-de-dominio-por-relevancia-baja-en-retrieval.md).

## Spec

- **`app/rag/retriever.py`**: partir `Retriever.retrieve()` en dos métodos públicos —
  `embed_query(query: str) -> list[float]` y
  `search(vector: list[float], *, top_k: int, domain=None, package=None, estado=None) -> list[RankedHit]`
  (misma firma/comportamiento que hoy, solo separando el paso de embeber del de buscar). `retrieve()` se
  convierte en un envoltorio fino: `vector = await self.embed_query(query); return await
  self.search(vector, top_k=top_k, domain=domain, package=package, estado=estado)`. Sin cambio de
  comportamiento para los llamantes existentes (`PgVectorStore`, tests).
- **`app/core/config.py`**: nuevo `Settings.rag_domain_fallback_margin: float = Field(default=0.05,
  ge=0.0)`, con docstring en el mismo estilo que `agent_confidence_threshold` (default sin calibrar, se
  revisa cuando exista telemetría real).
- **`app/agents/nodes/retrieve.py`** (`make_retrieve_node`): nueva firma
  `make_retrieve_node(retriever: Retriever, top_k: int, domain_fallback_margin: float) -> NodeFn`. Lógica:
  1. `vector = await retriever.embed_query(query)`.
  2. `filtered = await retriever.search(vector, top_k=top_k, domain=domain)`.
  3. Si `domain is None` → `state["retrieved"] = filtered` (comportamiento actual intacto, sin segunda
     búsqueda — cubre CU-BE-05 1a).
  4. Si `domain is not None` → SIEMPRE ejecutar `unfiltered = await retriever.search(vector, top_k=top_k,
     domain=None)` (incondicional, no gateado por el score filtrado — ver ADR-0019, el caso real con
     score 0.611 lo exige). Comparar `max(hit.score for hit in filtered)` (o `0.0` si `filtered` está
     vacío) contra `max(hit.score for hit in unfiltered)` (score CRUDO, no `weighted_score`, mismo
     criterio que `compute_confidence`). Si `max_unfiltered - max_filtered > domain_fallback_margin` →
     `state["retrieved"] = unfiltered`; si no → `state["retrieved"] = filtered`. Sin merge/dedup entre
     ambas listas.
  5. Log `structlog` nivel `info` en TODA comparación (paso 4, tanto si se usa el fallback como si no):
     `ticket_id`, dominio original (`classification.dominio`), `max_score` filtrado, `max_score` sin
     filtro, y si se usó el fallback (`bool`).
- **`app/agents/graph.py`** (`build_graph`): nuevo parámetro `domain_fallback_margin: float`, pasado a
  `make_retrieve_node`.
- **`app/agents/runner.py`** (`LangGraphAgentRunner.__init__`): nuevo parámetro
  `domain_fallback_margin: float`, pasado a `build_graph()`.
- **`app/core/deps.py`** (`_get_agent_runner`): pasa `domain_fallback_margin=settings.
  rag_domain_fallback_margin`.
- **`tests/test_node_retrieve.py`**: extender `_FakeRetriever` para exponer `embed_query`/`search` por
  separado, devolver listas de hits distintas según `domain` (parametrizable en el constructor), y
  registrar el HISTORIAL de llamadas a `search` (no solo la última) — necesario para verificar que se
  llama exactamente una o dos veces según el caso.
- **`tests/test_rag_retriever.py`**: tests del refactor `embed_query`/`search`; `retrieve()` sigue
  pasando sus tests actuales sin cambios (verifica que el envoltorio no rompe nada).

## Fuera de alcance

- Corregir `ticket.domain`/`ticket.priority` persistidos — siguen siendo los de `classify`, aunque el
  retrieval haya caído a sin-filtro.
- Resolver los 6 huecos de contenido real de la KB encontrados en la investigación — no es un problema
  de código, es contenido que falta escribir.
- Mezclar/deduplicar ambas listas de hits (filtrada + sin filtro).
- Cualquier cambio a `grade.py`/`confidence.py`/`decide.py`.
- Recalibrar `agent_confidence_threshold` u otros umbrales ya existentes.
- Añadir un campo de telemetría explícito en el esquema (`agent_run.domain_fallback` o similar) — el
  `domain` de las citas en `sources` + el log nuevo ya dan visibilidad suficiente (ver ADR-0019).
- Cachear/mitigar el coste de la segunda consulta ANN a Postgres — aceptado como coste permanente (ver
  "Riesgo operacional agravado" en ADR-0019); no se optimiza en esta tarea.

## Scenarios (Gherkin)

Criterios de aceptación (Gherkin) en el caso de uso:
- [CU-BE-05 — Clasificación y retrieval RAG](../../../specs/backend/casos-de-uso/CU-BE-05-clasificacion-y-retrieval-rag.md)
  — extensión 1c y los 8 escenarios que la desarrollan (desde "El dominio asignado pero equivocado no
  bloquea el retrieval de la respuesta correcta" hasta "Toda comparación con dominio asignado se
  registra, dispare o no el fallback"), endurecidos con `scenario-coverage` (8 huecos incorporados:
  `filtered` vacío, ambas búsquedas vacías, frontera exacta del margen, sensibilidad al valor
  configurado, fallo de la segunda búsqueda, reutilización del vector de `embed_query`, máximo una
  búsqueda sin dominio, y el log en toda comparación).

## Provides

—

## Definition of Done

- [ ] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [ ] Cada escenario Gherkin tiene al menos un test (camino feliz + bordes/errores)
- [ ] Todos los tests en verde
- [ ] Spec cumplida
- [ ] Lint / format / typecheck OK (`ruff check`, `ruff format --check`, `mypy app` strict)
- [ ] Gate de mutation testing superado con `cosmic-ray` (referencia no verificada, banner de la skill
      `mutation`, `break: 80`)
- [ ] Gate `sdd-lint` superado — CU-BE-05/agent-graph.md/ADR-0019 sin ERROR de formato/completitud
- [ ] Gate de `fact-checker` superado — afirmaciones de la sesión verificadas
- [ ] Verificación manual contra el backend real (no solo tests):
  - [ ] Los 3 casos reales documentados en el plan generan draft tras el fix (re-triggerar el agente)
  - [ ] Control de regresión (`design-review` #2): los 5 tickets de la muestra que ya generaban draft
        correcto siguen generándolo, con citas que no empeoran
- [ ] Documentación actualizada:
  - [ ] TSDoc/docstrings en `retrieve.py`, `retriever.py`, `graph.py`, `runner.py`, `deps.py`,
        `config.py` donde cambie la firma o se añada el nuevo `Settings`
  - [ ] Histórico de la tarea — session log en
        `.claude/context/backend/backend-rag-domain-fallback-01.md`
- [ ] Docs de dev / usuario final + `pnpm changeset` donde aplique (N/A — backend no usa changesets)
