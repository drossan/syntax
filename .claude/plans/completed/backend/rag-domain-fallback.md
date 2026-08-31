---
id: backend-rag-domain-fallback
package: backend
status: completed
branch: plan/backend/rag-domain-fallback
issue:
created: 2026-08-31
updated: 2026-08-31
---

# Fallback de retrieval cuando el dominio clasificado da baja relevancia

## Contexto y problema

Investigación en vivo (backend real, Postgres `backend-db-1`) sobre por qué el 66.7% de los drafts de
IA salen vacíos (10 de 15 `approval_task`). Reclasifiqué + reejecuté retrieval (con y sin filtro de
dominio) para 9 de los 10 tickets con draft vacío, usando el texto real del primer mensaje.

**Hallazgo verificado (no hipótesis)**: 3 de 9 (33%) son fallos de clasificación de dominio, no huecos
de contenido — la respuesta correcta SÍ existe en la KB, pero vive en un dominio distinto del que
`classify` asignó, y `retrieve.py` (`app/agents/nodes/retrieve.py:18-20`) solo cae a "sin filtro" cuando
`classification.dominio is None` — nunca cuando el dominio SÍ se asignó pero está equivocado:

| Ticket | Dominio asignado | Score con filtro | Doc real (dominio correcto) | Score sin filtro |
|---|---|---|---|---|
| "¿Quién puede editar o publicar una página?" | `authoring_and_editor` | 0.611 | UC-API-002 (`identity-and-permissions`) | 0.717 |
| "Página en pending" | `rendering_and_publishing` | 0.466 | UC-AX-005 (`authoring-and-editor`) / UC-API-034/035 (`sites-domains-instances`) | 0.630 |
| "Sistema de embeddings en API" | `rendering_and_publishing` | 0.384 | UC-API-130 (`search-ai-and-llms`) | 0.548 |

En los 6 casos restantes, el score sin filtro NO mejora — ahí sí es hueco real de contenido de la KB
(fuera de alcance de este plan: no se puede arreglar con código).

**Causa de fondo**: no es ruido aleatorio del LLM clasificador — en los 3 casos fallidos, el término
clave de la pregunta ("publicar") vive repartido en al menos 3 dominios distintos de los 17
(`rendering-and-publishing`, `authoring-and-editor`, `sites-domains-instances`). El clasificador elige
un dominio plausible por el nombre, pero no el que realmente contiene el documento — frontera de
taxonomía ambigua, sistemática.

`agent-graph.md` §4 y `CU-BE-05` (escenario 1a) ya documentan un fallback "sin filtro de dominio", pero
**solo para `dominio=None`** (ticket no clasificable). El caso encontrado — dominio asignado con
aparente confianza, pero equivocado — no está cubierto por la spec actual: es una decisión de diseño
nueva, no una corrección de bug sobre un comportamiento ya especificado.

**Dato matemático de partida** (no una suposición): una búsqueda sin filtro de dominio sobre el corpus
completo NUNCA puede dar un `max(score)` peor que la misma búsqueda filtrada a un subconjunto de ese
corpus — el filtro solo puede empatar o perder. Confirmado en los 9 casos probados (la diferencia nunca
fue negativa).

## Objetivos

1. **Cuando hay dominio asignado, reintentar SIEMPRE sin filtro y usar ese resultado si mejora
   significativamente sobre el filtrado** (`design-review` #1: el reintento es incondicional, no
   gateado por "score bajo" — el caso real de la tabla, score filtrado 0.611, ya está POR ENCIMA de
   `agent_confidence_threshold=0.6`; gatear el reintento por un umbral de score habría dejado ese caso
   sin arreglar) — sin tocar el juicio cualitativo de `grade.py` (ya acierta en los 6 casos de hueco
   real) ni la persistencia de `ticket.domain`.
   - *Criterio de éxito*: los 3 casos reales documentados arriba generan draft tras el fix, verificado
     re-triggerando el agente contra el backend real.

## Alcance y fuera de alcance

### Dentro del alcance
- **Dónde vive la lógica**: en el nodo `retrieve` (`app/agents/nodes/retrieve.py`), NO en
  `Retriever.retrieve()` (`app/rag/retriever.py`). El propio docstring de `Retriever` ya documenta que
  tiene DOS llamantes con semánticas distintas (el nodo del agente y el adaptador HTTP de `/kb/search`,
  ADR-0018) — un fallback silencioso de dominio es una política **específica del agente**; el camino
  HTTP, donde un humano elige explícitamente un filtro de dominio en el panel, debe seguir
  respetándolo literalmente, sin overrides.
- **Trigger**: tras la búsqueda filtrada por dominio, si `domain is not None`, reintentar con
  `domain=None`. Comparar `max(hit.score)` (score CRUDO, no `weighted_score` — mismo criterio que
  `compute_confidence`, para no contar el peso de `estado` dos veces) de ambos resultados. Si el
  resultado sin filtro mejora por más de un margen configurable, se usa ESE resultado completo (no se
  mezclan ambas listas — mantiene el criterio ya existente de "sin dedup" del nodo, ADR-0018 D3a).
- **Nuevo `Settings.rag_domain_fallback_margin`** (`app/core/config.py`), mismo patrón que
  `agent_confidence_threshold`: `float`, default sin calibrar (candidato inicial `0.05`, el mismo que
  usé para distinguir los 3 casos reales de los 6 huecos genuinos en la investigación), documentado como
  "se revisa cuando exista telemetría real" — no es una constante interna tipo `AGENT_TOP_K` porque,
  igual que `agent_confidence_threshold`, es un umbral de negocio calibrable con datos, no una elección
  estructural fija. **`grilling`: default confirmado `0.05`** — separa limpio los 3 fallos reales
  (mejoras +0.106/+0.164/+0.164) de los 6 sin mejora (máx 0.0137).
- **Plumbing**: threading del nuevo valor exactamente igual que `top_k`/`confidence_threshold` hoy:
  `deps.py` → `LangGraphAgentRunner.__init__` → `build_graph()` → `make_retrieve_node()`.
- **`grilling`**: se evita la doble llamada a `embed_query` (OpenAI) — no es coste raro de un caso de
  fallo, es coste permanente en el 100% de los tickets clasificados con dominio (latencia añadida a cada
  run, no solo a los que fallan). Se refactoriza `Retriever` (`app/rag/retriever.py`) partiendo
  `retrieve()` en dos métodos públicos: `embed_query(query) -> list[float]` y
  `search(vector, *, top_k, domain=None, package=None, estado=None) -> list[RankedHit]`; `retrieve()`
  queda como envoltorio fino de ambos (mismo comportamiento, sin cambio para los llamantes existentes —
  camino HTTP y tests). El nodo `retrieve` del agente usa los dos métodos sueltos para reutilizar el
  mismo vector en la segunda búsqueda (sin filtro) cuando hace falta comparar.
- Extender `.claude/specs/backend/agent-graph.md` §4 y `CU-BE-05` con la nueva extensión (dominio
  asignado pero de baja relevancia retrospectiva → fallback ampliado).
- **Nuevo ADR** (`grilling`: ADR nuevo, no extender ADR-0009 — decisión distinguible con su propio
  trade-off de latencia vs. recall; ADR-0009 se referencia, no se reabre) — `0019` libre en `main`,
  documentando la decisión, con referencia a ADR-0009 (confianza híbrida) y ADR-0018 (separación
  agente/HTTP en `Retriever`). Sección "Consecuencias" debe incluir explícitamente, estilo ADR-0018
  ("Mala, aceptada"):
  - (`design-review` #4) `ticket.domain` puede quedar persistido distinto del dominio real de las citas
    en `agent_run.sources` cuando se usa el fallback — sin señal consultable salvo comparar manualmente
    o grepear el log nuevo; puede confundir analítica por dominio futura.
  - (`design-review` #5) esta decisión AGRAVA el riesgo ya escrito sin mitigar en ADR-0018 ("el umbral
    de 50.000 chunks no tiene alarma, se cruzará en silencio"): añade una segunda query completa por
    cada ticket clasificado con dominio, el 100% de los runs, para siempre — duplicando exactamente el
    coste que dejará de ser gratis el día que se cruce ese umbral.
- **`grilling` + `design-review` #3**: log `structlog` nivel `info` en TODA comparación (siempre que hay
  dominio asignado y se ejecuta la segunda búsqueda), no solo cuando el margen se supera — si solo
  loguea "cuando se dispara", los casos límite (deltas 0.03-0.04, justo bajo `0.05`) nunca se ven, y sin
  ellos no se puede calibrar el margen después. Campos: `ticket_id`, dominio original de `classify`,
  `max_score` filtrado, `max_score` sin filtro, y si el fallback se usó o no — visibilidad de producción
  para calibrar `rag_domain_fallback_margin` más adelante, sin abrir ninguna superficie nueva de datos
  persistidos (mismo patrón que ADR-0015, observabilidad vía `structlog` + `request-id`).

### Fuera de alcance
- Corregir `ticket.domain`/`ticket.priority` persistidos — siguen siendo los de `classify`, aunque el
  retrieval haya caído a sin-filtro.
- Resolver los 6 huecos de contenido real de la KB encontrados en la investigación — no es un problema
  de código, es contenido que falta escribir.
- Mezclar/deduplicar ambas listas de hits (filtrada + sin filtro).
- Cualquier cambio a `grade.py`/`confidence.py`/`decide.py`.
- Recalibrar `agent_confidence_threshold` u otros umbrales ya existentes.
- **`grilling`**: añadir un campo explícito de telemetría (p.ej. `agent_run.domain_fallback: bool`) —
  el propio `domain` de cada cita en `sources` ya permite inferir el fallback indirectamente (si las
  citas no coinciden con `ticket.domain`); una migración de esquema para un caso de uso de telemetría
  futura, no pedido todavía, se descarta por ahora.

## Recursos externos

- `.claude/specs/backend/agent-graph.md` §4-§5 — fuente de verdad del diseño del grafo.
- `.claude/specs/backend/casos-de-uso/CU-BE-05-clasificacion-y-retrieval-rag.md` — escenarios 1/1a.
- `app/agents/nodes/retrieve.py`, `app/rag/retriever.py`, `app/rag/confidence.py`,
  `app/rag/reranker.py` — código real a tocar/consultar.
- `app/core/deps.py` (`AGENT_TOP_K`, `_get_agent_runner`), `app/agents/graph.py`, `app/agents/runner.py`
  — plumbing existente, mismo patrón a replicar.
- `tests/test_node_retrieve.py` — tests existentes del nodo, patrón `_FakeRetriever`.
- ADR-0009 (confianza híbrida), ADR-0010 (rag pgvector), ADR-0018 (retrieval HTTP vs agente).

## Estimación global

- **Tareas totales**: 1 (cambio cohesivo de un solo commit lógico; puede crecer en `design-review`/
  `scenario-coverage`).
- **Esfuerzo estimado**: 0.5-1 sesión.
- **Recursos**: sin dependencias nuevas.

## Criterios de calidad y verificación

- TDD sobre `test_node_retrieve.py`: casos con `domain` asignado + score bajo → segunda llamada con
  `domain=None`; mejora significativa → usa el resultado sin filtro; sin mejora → mantiene el filtrado;
  `domain=None` desde el inicio → sin segunda llamada (comportamiento actual intacto).
- `pytest` + mutation gate (cosmic-ray, referencia no verificada, banner de la skill `mutation`).
- Verificación manual contra el backend real: reejecutar los 3 casos reales documentados arriba
  (re-triggerar el agente sobre esos tickets o equivalentes) y confirmar que ahora sí generan draft.
- **`design-review` #2 — control de regresión, no solo de arreglo**: dado que `unfiltered ≥ filtered`
  siempre (matemático), es plausible que el fallback sustituya un resultado ya bueno por uno de dominio
  incorrecto en un ticket que hoy SÍ genera draft correcto. Re-triggerar también los 5 tickets de la
  muestra de 15 `approval_task` que ya generaban draft con el dominio filtrado tal cual, y confirmar que
  las citas resultantes no empeoran (mismo dominio o `grade` sigue aceptando el contexto).

## Tasks

- [x] `backend-rag-domain-fallback-01` (P1) — Fallback de retrieval por baja relevancia con dominio asignado  · depends_on: —

## Registro de cambios del plan

- 2026-08-31: creado, a partir de una investigación en vivo pedida por el owner ("mira antes" de decidir
  si abrir el plan) — 9/10 tickets con draft vacío reclasificados y re-retrieved contra el backend real,
  3 confirmados como fallo de filtro de dominio recuperable por código, 6 como hueco real de contenido.
- 2026-08-31: refinado con `grilling` (4 preguntas, 4 decisiones):
  1. Optimizar la doble llamada a `embed_query` — SÍ, refactorizar `Retriever` en `embed_query()` +
     `search()` (revierte mi recomendación inicial de "aceptar el coste tal cual"; el owner señaló que
     el coste es permanente en el 100% de tickets clasificados, no un caso raro).
  2. `rag_domain_fallback_margin` default — `0.05`, confirmado el recomendado.
  3. Campo de telemetría explícito en el esquema — NO, se descarta (recomendado, `domain` de las citas
     ya permite inferirlo).
  4. ADR nuevo vs extender ADR-0009 — ADR nuevo (recomendado).
  5. Log `structlog` al disparar el fallback — SÍ (recomendado), visibilidad para calibrar el margen.
- 2026-08-31: revisado con `design-review` (subagente fresco, modelo caído a inherit —
  `models.design-review: claude-opus-4-8` no es un alias válido). 5 hallazgos, ninguno exige rehacer el
  diseño de fondo; los 5 aceptados sin discrepancia:
  1. Corregida la redacción de "Objetivos" — el reintento es incondicional (siempre que hay dominio),
     no gateado por "score bajo"; el propio caso de la tabla (0.611, ya sobre el umbral de confianza
     0.6) lo demuestra.
  2. Añadido a "Criterios de verificación": re-triggerar también los 5 tickets que ya generaban draft
     correcto, para descartar que el fallback sustituya silenciosamente un resultado ya bueno.
  3. El log pasa a emitirse en TODA comparación (gane o no el margen), no solo cuando se dispara —
     si no, los casos límite nunca se ven y no sirve para calibrar.
  4. ADR-0019 documentará explícitamente la divergencia `ticket.domain` vs. dominio real de las citas
     como consecuencia aceptada.
  5. ADR-0019 referenciará el riesgo sin mitigar de ADR-0018 (50.000 chunks sin alarma), agravado por
     esta decisión (doble query en el 100% de los runs).
- 2026-08-31: escrito ADR-0019 (accepted) y tarea `backend-rag-domain-fallback-01`; extendidos
  `agent-graph.md` §4 y CU-BE-05 (extensión 1c, 3 escenarios base).
- 2026-08-31: endurecido con `scenario-coverage` (subagente QA fresco). (A) 8 huecos dentro de alcance,
  todos incorporados al Gherkin de CU-BE-05: `filtered` vacío (evita `ValueError` de `max()`), ambas
  búsquedas vacías, frontera exacta `delta == margin` (off-by-one del `>` estricto), sensibilidad al
  valor configurado del margen (Outline), fallo de la segunda búsqueda no enmascarado, **reutilización
  del vector de `embed_query`** (la razón de negocio central del refactor, sin cobertura hasta ahora),
  máximo una búsqueda cuando no hay dominio, y el log emitiéndose en TODA comparación. Dimensión 5
  (concurrencia) N/A — el nodo no tiene estado compartido mutable entre runs en este alcance. (B)
  ninguno — todos los hallazgos fuera de alcance ya estaban correctamente declarados y el subagente los
  confirmó contra los bullets existentes sin aportar ninguno nuevo.
- 2026-08-31: **plan cerrado** — 1/1 tarea completada.

## Retro de cierre

- **Estimación vs. real**: 0.5-1 sesión estimada; se completó en una sesión continua (incluyendo
  `/plan-task` completo con `grilling` + `design-review` + `scenario-coverage`).
- Verificado en vivo contra el backend real (no solo tests): los 3 casos rotos documentados en el
  contexto ahora generan draft; los 5 casos que ya funcionaban lo siguen haciendo, con
  `used_fallback=False` en los 5 — sin ninguna regresión detectada.
- `sdd-lint` semántico encontró un ERROR real de trazabilidad (ADR-0019 no referenciado de vuelta desde
  CU-BE-05/agent-graph.md) que habría dejado la documentación inconsistente si no se hubiera corregido
  antes de cerrar — confirma el valor de correr el gate incluso en una tarea de una sola sesión.
- `fact-checker` encontró un `INCORRECTO` real (formato no aplicado a un test añadido después del
  `ruff format` inicial) — recordatorio de que el orden de las herramientas importa: formatear DESPUÉS
  de la última edición, no solo una vez a mitad de la tarea.
- Mutation testing (`cosmic-ray`) reveló un patrón de mutantes equivalentes específico de este repo/
  herramienta: el marcador `*,` (keyword-only) en firmas de métodos se mutaba a `/,`/`|,` sin efecto
  observable (todas las llamadas usan argumentos con nombre) — documentado para no perseguirlo en
  futuras tareas que toquen `app/rag/retriever.py` o firmas similares.
- Deuda deliberadamente fuera de alcance (documentada en ADR-0019, no repetida aquí): los 6 huecos de
  contenido real de la KB detectados en la investigación previa a este plan; la divergencia
  `ticket.domain` vs. dominio real de las citas cuando el fallback gana; el riesgo agravado del umbral
  de 50.000 chunks de ADR-0018.
