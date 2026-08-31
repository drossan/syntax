# 0019. Fallback de retrieval sin filtro de dominio cuando el filtrado da baja relevancia

- **Estado**: accepted
- **Fecha**: 2026-08-31
- **Decisores**: Owner; `grilling` + `design-review` del plan `rag-domain-fallback` (2026-08-31).
- **Contexto SDD**: refina [ADR-0009](./0009-confianza-hibrida-y-auto-approve-por-tenant.md) (confianza
  híbrida) y referencia [ADR-0018](./0018-retrieval-http-de-la-kb-ventana-dedup-y-peso-de-estado.md)
  (separación agente/HTTP en `Retriever`, riesgo del umbral de 50.000 chunks). Traza
  [CU-BE-05](../backend/casos-de-uso/CU-BE-05-clasificacion-y-retrieval-rag.md) extensión 1c.

## Contexto y planteamiento del problema

Investigación en vivo contra el backend real (Postgres `backend-db-1`): 66.7% de los `approval_task`
(10/15) tienen `draft_body` vacío. Reclasificando + re-ejecutando retrieval (con y sin filtro de
dominio) sobre 9 de esos 10 tickets, 3 (33%) resultaron ser fallos de clasificación de dominio, no
huecos de contenido: el documento que responde a la pregunta existe en la KB, pero vive en un dominio
distinto del que `classify` asignó, y `retrieve` (`app/agents/nodes/retrieve.py`) solo cae a "sin
filtro" cuando `classification.dominio is None` (CU-BE-05 1a) — nunca cuando el dominio SÍ se asignó
pero está equivocado.

Los 3 casos comparten un patrón: el término clave de la pregunta ("publicar") vive repartido en al
menos 3 de los 17 dominios (`rendering-and-publishing`, `authoring-and-editor`,
`sites-domains-instances`). No es ruido aleatorio del clasificador — es una frontera de taxonomía
ambigua y sistemática.

**Dato matemático de partida**: una búsqueda sin filtro de dominio sobre el corpus completo nunca puede
dar un `max(score)` peor que la misma búsqueda filtrada a un subconjunto — el filtro solo puede empatar
o perder. Confirmado en los 9 casos probados. Consecuencia directa: **un umbral absoluto sobre el score
filtrado no puede servir de trigger** — uno de los 3 casos reales tiene score filtrado `0.611`, ya por
encima de `agent_confidence_threshold=0.6`, y aun así es el dominio equivocado; cualquier umbral que
dispare ahí también dispararía en casos correctos con score similar o mayor.

## Decision drivers

- No tocar el juicio cualitativo de `grade.py` (acierta en los 6 casos de hueco real de contenido de la
  KB — no hay nada que arreglar ahí).
- No corregir `ticket.domain`/`ticket.priority` persistidos — es una decisión de alcance distinta
  (re-clasificación), no de retrieval.
- El camino HTTP de `/kb/search` (ADR-0018) es un consumidor **distinto** de `Retriever`, donde un
  humano elige explícitamente el filtro de dominio en el panel: un fallback silencioso ahí sería
  sorprendente e indeseado.
- El coste de una segunda consulta de embeddings por ticket no debe pagarse dos veces si se puede evitar
  reutilizando el vector ya calculado.

## Opciones consideradas

1. **Reintento incondicional en el nodo `retrieve`**: siempre que hay dominio asignado, ejecutar también
   la búsqueda sin filtro (reutilizando el vector de la consulta) y usar el resultado sin filtro si
   mejora sobre un margen configurable.
2. **Pre-filtro por umbral absoluto** sobre el score filtrado antes de decidir si reintentar.
3. **Mezclar/deduplicar** ambas listas de hits en vez de sustituir una por otra.
4. **Mover la lógica a `Retriever.retrieve()`** (capa compartida por el agente y el camino HTTP).

## Resultado de la decisión

**Opción 1**, con los siguientes ejes:

### Dónde vive la lógica

En el nodo `retrieve` del agente (`app/agents/nodes/retrieve.py`), no en `Retriever` (`app/rag/
retriever.py`). `Retriever` ya documenta que tiene dos llamantes con semánticas distintas (ADR-0018):
el nodo del agente y el adaptador HTTP de `/kb/search`. Un fallback silencioso de dominio es una
política **específica del agente**; el camino HTTP, donde un humano elige explícitamente el filtro,
debe seguir respetándolo literalmente.

### Trigger: incondicional, no por umbral

Se descarta la **opción 2**. El caso real con score filtrado `0.611` (arriba) demuestra que un umbral
absoluto no puede distinguir "dominio equivocado con score decente" de "dominio correcto con score
similar" — ambos casos comparten el mismo rango de score. El reintento sin filtro se ejecuta **siempre**
que `domain is not None`; solo la **decisión de usar** el resultado sin filtro está gateada por
`Settings.rag_domain_fallback_margin` (`float`, default `0.05` — sin calibrar contra más datos que la
muestra de 9 casos de esta investigación, mismo criterio que `agent_confidence_threshold`; separa
limpio los 3 fallos reales, mejoras +0.106/+0.164/+0.164, de los 6 sin mejora, máximo +0.0137).

### Sin merge ni dedup

Se descarta la **opción 3**. Si el resultado sin filtro mejora por encima del margen, se usa ESE
resultado **completo**, sustituyendo al filtrado — no se mezclan ambas listas. Mantiene el criterio ya
existente del nodo (ADR-0018 D3a: sin dedup en el camino del agente) y evita la complejidad de decidir
cómo intercalar hits de dos búsquedas con `top_k` cada una.

### Refactor de `Retriever`: `embed_query()` + `search()`

Se descarta pagar dos veces la llamada a `embed_query` (OpenAI) por ticket — no es el coste de un caso
raro, es coste permanente en el 100% de los tickets clasificados con dominio, para siempre (latencia
añadida a cada run, no solo a los que disparan el fallback). `Retriever.retrieve()` se parte en dos
métodos públicos: `embed_query(query) -> list[float]` y `search(vector, *, top_k, domain=None,
package=None, estado=None) -> list[RankedHit]`; `retrieve()` queda como envoltorio fino de ambos, sin
cambio de comportamiento para los llamantes existentes (camino HTTP, tests). El nodo `retrieve` del
agente usa los dos métodos sueltos para reutilizar el mismo vector en la segunda búsqueda.

Se descarta la **opción 4** (mover la lógica a `Retriever`) por el mismo motivo que "dónde vive la
lógica" arriba: mezclaría una política del agente en una capa compartida con el camino HTTP.

### Observabilidad: log, no campo de esquema

Se descarta añadir un campo nuevo de telemetría (`agent_run.domain_fallback: bool` o similar) — el
`domain` de cada cita en `agent_run.sources` ya permite inferir el fallback indirectamente comparándolo
con `ticket.domain`; una migración de esquema para un caso de uso de telemetría futura, no pedido
todavía, se descarta por ahora. En su lugar, un log `structlog` nivel `info` (mismo patrón que
ADR-0015) se emite en **toda comparación** (siempre que hay dominio asignado y se ejecuta la segunda
búsqueda), no solo cuando el margen se supera — si solo logueara "cuando se dispara", los casos límite
(deltas 0.03-0.04, justo bajo `0.05`) nunca se verían, y sin ellos no se podría calibrar el margen más
adelante con datos reales. Campos: `ticket_id`, dominio original de `classify`, `max_score` filtrado,
`max_score` sin filtro, y si el fallback se usó o no.

### Verificación: incluye control de regresión

No basta con confirmar que los 3 casos rotos ahora generan draft. Dado que `unfiltered ≥ filtered`
siempre, es plausible que el fallback sustituya un resultado ya bueno por uno de dominio incorrecto en
un ticket que hoy funciona. La verificación manual incluye re-triggerar también los 5 tickets de la
muestra de 15 `approval_task` que ya generaban draft correcto, confirmando que las citas resultantes no
empeoran.

### Confirmación

CU-BE-05 (Gherkin, extensión 1c) + `agent-graph.md` §4. Implementación y tests: plan
`rag-domain-fallback`, tarea `-01` — unit sobre `test_node_retrieve.py` (patrón `_FakeRetriever`) +
`test_rag_retriever.py` (refactor `embed_query`/`search`), verificación manual contra Postgres real.

## Consecuencias

- **Buena**: recupera el contexto correcto en el 33% de los casos de la muestra donde el clasificador
  asigna un dominio equivocado, sin tocar el juicio de `grade.py` (que ya acierta en el resto).
- **Buena**: el coste de la segunda búsqueda no duplica la llamada a embeddings (refactor
  `embed_query`/`search`), solo una consulta ANN adicional a Postgres.
- **Mala, aceptada**: `ticket.domain` puede quedar persistido distinto del dominio real de las citas en
  `agent_run.sources` cuando se usa el fallback — sin señal consultable salvo comparar manualmente las
  citas contra `ticket.domain`, o revisar el log nuevo. Puede confundir analítica por dominio futura que
  no sepa de esta divergencia.
- **Riesgo operacional agravado**: ADR-0018 ya deja escrito, sin mitigar, que el umbral de 50.000 chunks
  para crear un índice ANN "no tiene alarma, se cruzará en silencio". Esta decisión añade una **segunda**
  consulta ANN completa por cada ticket clasificado con dominio, el 100% de los runs, para siempre —
  duplicando exactamente el coste que dejará de ser gratis el día que se cruce ese umbral.
- **Mala, aceptada**: no resuelve los 6 casos de hueco real de contenido de la muestra (81.5%+ de los
  drafts vacíos siguen siendo huecos genuinos de la KB, no un problema de código).

## Pros y contras de las opciones

- **Opción 1 (reintento incondicional, elegida)** — *Pros*: cubre el caso real (score 0.611) que un
  umbral no cubriría; no toca `grade.py`. *Contras*: segunda consulta ANN en el 100% de los runs
  clasificados con dominio, para siempre.
- **Opción 2 (pre-filtro por umbral)** — *Pros*: evita la segunda consulta en más casos. *Contras*:
  matemáticamente no puede distinguir el caso real (0.611) de los casos correctos con score similar —
  se descarta por evidencia, no por preferencia.
- **Opción 3 (merge/dedup)** — *Pros*: podría conservar señal de ambas búsquedas. *Contras*: complejidad
  añadida (cómo intercalar dos `top_k`) sin evidencia de que aporte sobre "sustituir si mejora".
- **Opción 4 (lógica en `Retriever`)** — *Pros*: un solo sitio de cambio. *Contras*: mezcla una política
  específica del agente en una capa que el camino HTTP consume con semántica distinta (ADR-0018).
