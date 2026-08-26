# 0018. Retrieval HTTP de la KB: ventana de recuperación, dedup por `uc_id` y peso de `estado` fuera de SQL

- **Estado**: accepted
- **Fecha**: 2026-08-25
- **Decisores**: Owner; `grilling` + `design-review` + `scenario-coverage` del plan `kb-retriever`
  (2026-08-24).
- **Contexto SDD**: refina [ADR-0010](./0010-rag-pgvector-chunking-h2-tolerante-estado-peso.md) (RAG:
  pgvector + peso de `estado`). Materializa FR-049…FR-056. Traza
  [CU-BE-12](../backend/casos-de-uso/CU-BE-12-consulta-de-la-kb-desde-el-panel.md) y la mitad de
  recuperación de [CU-BE-05](../backend/casos-de-uso/CU-BE-05-clasificacion-y-retrieval-rag.md).
  Detalle: [`rag-ingestion.md`](../backend/rag-ingestion.md) §4/§6,
  [`api-contract.md`](../general/api-contract.md).

## Contexto y planteamiento del problema

La ingestión de la KB está cerrada, pero el **camino de lectura** existe entero y **vacío a propósito**:
`SqlAlchemyKBIndexWriter.search()` lanza `NotImplementedError`, `StubVectorStore` devuelve `[]`/`None`, y
`app/rag/{retriever,reranker,confidence,citations}.py` son guiones sin código. Consecuencia observable:
`/kb` en el panel está vacío aunque la KB se ingiera.

Implementarlo obliga a decidir cosas que ADR-0010 no fijó, porque solo contemplaba el retrieval **del
agente**:

1. **Dos consumidores con formas distintas.** El agente LangGraph quiere **chunks** (con `chunk_id`,
   sin deduplicar, para el prompt de `generate`); el panel quiere **documentos** paginados. Comparten la
   capa de recuperación pero no la salida.
2. **Una búsqueda ANN no tiene cardinalidad.** El contrato de paginación
   ([`api-contract.md`](../general/api-contract.md)) exige `{items, page, page_size, total}`, y `total`
   no tiene una respuesta natural en una búsqueda por similitud.
3. **El 81% del corpus es `draft`** (218/268): el peso de `estado` de ADR-0010 tiene que aplicarse de
   verdad, y hay que decidir **dónde** — en SQL o en la capa de dominio.
4. **Un despliegue mal configurado no puede parecerse a "la KB no tiene resultados".** Es el fallo mudo
   que ADR-0017 identificó en la ingestión, y aquí reaparece con tres caras: proveedor de embeddings
   caído, vectores de otro modelo en el corpus, y consulta mal formada.

Al planificar aparecieron además dos hechos verificados que el encargo no contemplaba: **`snippet` es
drift contrato↔implementación** (declarado en `api-contract.yaml`, renderizado por el front, ausente en
la entidad, el schema y el mapeo del router — hoy no se nota porque el stub devuelve `[]`), y **ningún
CU ni ningún FR cubría el camino HTTP de la KB** (los tres endpoints se construyeron en `routers-core`,
antes de la capa SDD).

## Decision drivers

- La **política de negocio** (peso de `estado`, dedup) vive en el dominio, no en el adaptador SQL: es lo
  que permite testearla sin Postgres y no dejar inservible un índice ANN futuro.
- Un fallo de dependencia debe ser **distinguible** de un resultado vacío legítimo, siempre.
- No fijar firmas sin consumidor (criterio ya escrito en `ports/embeddings.py` y `ports/llm.py`).
- El `score` es una **señal** que consumirá la confianza híbrida de CU-BE-05: no puede quedar
  contaminado por una decisión de presentación.
- Optimizar sin métrica es deuda disfrazada de rendimiento.

## Opciones consideradas

1. **Recuperación cruda en infra + política en `app/rag/`**, con una **ventana de recuperación** que se
   re-rankea entera, se deduplica y se corta por página.
2. **Todo en SQL**: `ORDER BY` ponderado por `estado` y `DISTINCT ON (uc_id)` dentro del adaptador.
3. **Sin ventana**: `top_k = page * page_size` y `total` = `COUNT` de candidatos que pasan los filtros.
4. **Conservar `StubVectorStore` como fallback conmutable** para el adaptador real.

## Resultado de la decisión

**Opción 1.** Los ejes concretos:

### Recuperación (infra, sin política)

- `SqlAlchemyKBIndexWriter.search()` deja de lanzar `NotImplementedError` y es la **única** puerta de
  entrada a la búsqueda ANN: la reusará el nodo `retrieve` del grafo.
- Devuelve **coseno crudo, sin política de negocio**: `score = max(0.0, 1.0 - distance)`. El clamp no es
  cosmético — `1 - cosine_distance` ∈ `[-1, 1]`, y con similitud negativa la fórmula del peso
  (abajo) **penalizaría** al documento e invertiría el orden frente a un `draft`. Una similitud negativa
  es "menos relacionado que el azar": no hay ranking que preservar bajo 0.
- **Filtra por `Embedding.model == settings.embedding_model`.** Con vectores de dos modelos en el
  corpus, el coseno cruza espacios distintos y devuelve **basura perfectamente ordenada** — el fallo mudo
  del driver 4, en su forma más difícil de detectar.
- Un chunk **sin fila `embedding`** (caso real: `ChunkWrite.vector=None` sobre un chunk nuevo) queda
  fuera por el JOIN: no rompe la consulta y no aparece. Fijado por escenario.
- `Hit` gana **`content`** (el texto completo del chunk). Sirve al `snippet` hoy y al prompt de
  `generate` mañana. Ampliar este DTO —declarado "FINAL" en `kb-ingestion`— es seguro porque `search`
  nunca se ha ejecutado: no hay consumidor que romper.

### Ventana de recuperación y `total`

- `RAG_SEARCH_WINDOW = 100`, **expresada en DOCUMENTOS** (= el `page_size` máximo del contrato),
  implementada con un over-fetch de `100 * RAG_CHUNKS_PER_DOC` chunks (**factor 6**, sobre los ~5.7
  chunks/documento medidos en el corpus real).
- Se recupera la ventana, se re-rankea **entera**, se deduplica y se corta por página. **`total` = los
  documentos distintos dentro de la ventana**, no el corpus. Una `page` más allá de la ventana devuelve
  `items: []` con el mismo `total`.
- Medir la ventana en documentos —y no en chunks— es lo que impide que `total` y `items` cuenten
  unidades distintas: con la ventana en chunks, un `page_size` de 100 devolvía una página 1 truncada y
  un `total` que mentía.
- **Coste nulo hoy**: sin índice ANN el seq scan ya calcula las ~1626 distancias; la ventana solo elige
  cuántas se conservan.
- El cálculo del over-fetch vive en el **camino HTTP**. El nodo `retrieve` del agente recibe un `top_k`
  y no sabe nada de ventanas: la ventana es un concepto de paginación.

### Peso de `estado` y significado del `score`

- El peso se aplica en **`app/rag/reranker.py`**, sobre la ventana: `score' = score * (1 +
  RAG_ESTADO_WEIGHT)` si `estado is active`; **`draft` se deja intacto** (default `0.05`). El "suelo"
  que pedía ADR-0010 se cumple **por construcción**: lo que no se toca no puede hundirse.
- La objeción clásica al re-ranking ("solo reordena dentro del top-k") la neutraliza la ventana: un
  `active` en el puesto 45 por coseno crudo puede alcanzar la página visible.
- **`Hit.score` se queda CRUDO** (coseno acotado, sin peso). `rerank()` devuelve `RankedHit(hit,
  weighted_score)` y **solo ese `weighted_score` viaja a la API**. Si el peso se aplicara al `Hit`, el
  futuro `confidence.py` —que compone la confianza híbrida a partir de la similitud— contaría `estado`
  **dos veces**.
- Consecuencia a documentar: el `score` que devuelve `/kb/search` **puede superar `1.0`** y ya no es una
  similitud coseno. Es relevancia re-rankeada.
- Filtrar por `estado` sigue siendo **opt-in** por consulta (ADR-0010): cuando el usuario lo pide
  explícitamente, actúa como **filtro duro**; por su cuenta, el sistema nunca filtra.

### Dedup por `uc_id` — solo en el camino HTTP

- Función **pura** `dedup_by_uc_id(ranked)` en `app/rag/`, que llama **solo el adaptador HTTP**. Un item
  por documento, con el `score`, el `section_type` y el `snippet` de su **mejor chunk**.
- El **camino del agente no deduplica**: sigue viendo chunks con `chunk_id`.
- Sin flag `dedup: bool`: un booleano cuyas dos ramas tienen un consumidor cada una es una función
  distinta llamada desde sitios distintos, no un parámetro.
- Motivo del dedup: sin `chunk_id` en `KBSearchHit`, dos hits del mismo UC son **dos tarjetas que
  enlazan al mismo sitio** — y el front usa `key={hit.uc_id}`, así que serían además claves React
  duplicadas. Se descartó exponer `chunk_id`/`ordinal` en el contrato: es un id interno que el contrato
  oculta a propósito y que el front no pide.

### `snippet`

- **El principio de la sección ganadora**, truncado a **~280 caracteres por límite de palabra + elipsis**.
  Constante documentada del adaptador, **no un setting**: no hay dos despliegues que la quieran distinta.
- **No** es un extracto centrado en el término buscado: la búsqueda es **semántica** y un chunk puede
  casar sin contener la palabra. Prometer un fragmento "alrededor del término" sería mentir en el 100%
  de los casos en que el retrieval hace su trabajo.
- Se trunca en el backend porque la tarjeta del front **no tiene `line-clamp`** y este plan no toca
  código del front.

### Entrada inválida y fallos de dependencia

- `q.strip()` vacía → **422** con el envelope problem+json, **antes** de llamar al proveedor. Misma regla
  para `""` y `"   "`. Una búsqueda sin término es una petición **mal formada**, no una búsqueda sin
  resultados: confundirlas reproduce justo el síntoma que este plan viene a eliminar.
- `q` gana también un **límite superior** de longitud (**512 caracteres** en el contrato) → 422, en la
  misma regla. Sin tope, un cliente con un bug quema cuota de embeddings a coste del despliegue. El valor
  es holgado para una caja de búsqueda del panel y queda muy por debajo del límite del proveedor: acota
  el abuso, no el uso.
- Fallo del proveedor de embeddings → **502** (`PortError` → 502 ya existe en `app/api/errors.py`). Un
  vector de **dimensión distinta** a la configurada se trata como fallo del puerto, **no** se deja llegar
  a la comparación pgvector, donde reventaría como error de driver sin decir qué pasó.
- Fallo de **base de datos** → 502 también en `/kb/documents`, que no toca embeddings para nada.
- El contrato declara sus respuestas operación por operación, así que `/kb/search` gana **`422`** y
  **`502`** explícitos en `api-contract.yaml`, más el `maxLength` de `q`.

### Listado y detalle

- `list_documents` con **`ORDER BY uc_id ASC`** (único ⇒ estable). Sin él, el orden es arbitrario **y**
  el front lo pinta como "documentos relacionados" en `/kb/[uc_id]`: 20 documentos arbitrarios del
  dominio etiquetados como relacionados.
- La estabilidad de la paginación se garantiza **dentro de una ventana de recuperación**, no entre
  peticiones separadas en el tiempo: una **re-ingestión concurrente** puede alterar los resultados de
  páginas sucesivas. **Limitación aceptada** y documentada (RN-8 de CU-BE-12) en vez de resolverse con
  cursores — es un problema general de cualquier ANN paginado, y la paginación de `/kb` hoy **no tiene
  UI**.
- Los **glosarios** son documentos de pleno derecho del camino de lectura: se listan, se buscan y se
  abren por su `uc_id` sintético. ⚠️ **Sesgo conocido**: la ingestión les asigna `package`/`estado` **por
  defecto** (`syntax-core`/`active`, `app/ingestion/pipeline.py`) porque su formato no los trae, así que
  quien filtre por esos valores arrastra 16 documentos que no pertenecen ahí. Es un defecto **de la
  ingestión**: se documenta aquí y se corrige donde nace (migración + re-ingesta, en su propio plan).

### Índice ANN: diferido, con umbral

- **No se crea índice ANN ahora.** Con ~1626 chunks el seq scan es **exacto** y suficiente; un índice ANN
  lo volvería **aproximado sin ganancia medida**, e `ivfflat` sobre una tabla casi vacía saldría mal
  particionado (sus listas se calibran con los datos que hay al crearlo).
- **Umbral escrito**: crear **`hnsw`** con `vector_cosine_ops` cuando `kb_chunk` supere **50.000 filas**
  (~30× el corpus actual).
- ⚠️ **Un umbral sin alarma es una promesa que nadie cumple.** Queda dicho aquí: nadie vigila hoy el
  conteo de `kb_chunk`, así que este umbral se cruzará en silencio salvo que alguien lo mire.

### Puertos: se mantienen los dos

- Siguen existiendo `KBIndexWriter` (escritura + `search`) y `VectorStore` (lectura del router).
  Colapsarlos metería **lectura paginada de negocio** dentro de un puerto llamado `KBIndexWriter` e
  invertiría la dirección de dependencia del router. Router y agente son consumidores con formas
  distintas (§ *Dos consumidores*).
- **Deuda registrada**, y mitigada en lo que tiene de real: el SQL de `kb_document` se parte **por
  responsabilidad** —escritura en `app/infra/vector`, lectura en `PgVectorStore`— con **un solo sitio por
  operación**.
- Se corrige de paso el docstring de `ports/vector.py`, que prometía que la tarea 14 dejaría
  `VectorStore`/`StubVectorStore` "deprecados en favor de este puerto": es **imposible**, porque
  `KBIndexWriter` no tiene `list_documents` ni `get_document`.

### `StubVectorStore`: borrado

- Se borra el stub, su test y sus menciones en docstrings. Los tests de router del repo ya corren contra
  Postgres real, así que no se pierde cobertura.
- Se descartó dejarlo como **fallback conmutable**: convertiría un despliegue mal configurado en "la KB
  está vacía" — exactamente el fallo silencioso que ADR-0017 identificó y que `rag-ingestion.md` §7
  prohíbe.

### Guardia contrato↔implementación

- Test que compara el OpenAPI de `create_app()` con `api-contract.yaml` **acotado a los schemas de KB**
  (`KBSearchHit`, `KBDocument`). Es la red que faltó: `snippet` llevaba roto desde `routers-core` y se
  descubrió **por casualidad** al planificar.
- **Descartada** aquí la guardia **global** para todos los routers: un diff completo del contrato es otro
  plan, con sus propios hallazgos que resolver.

### Lo que NO se hace

- **Sin caché del vector de consulta**: se embebe siempre. Optimizaría sin métrica, y su clave tendría
  que incluir modelo + dimensión o serviría vectores rancios al cambiar `embedding_model`. Queda como
  follow-up documentado.
- **Sin `rag_top_k`**: era un setting sin consumidor. Lo añadirá el plan del agent-graph, con su caller
  delante.
- **`confidence.py` y `citations.py` siguen en guión**: no tienen consumidor hasta el agent-graph, y
  fijar sus firmas ahora violaría el criterio explícito del repo.

### Dónde vive el Gherkin

- **CU nuevo**, [CU-BE-12](../backend/casos-de-uso/CU-BE-12-consulta-de-la-kb-desde-el-panel.md), con
  actor = **usuario del panel con `kb.read`**. CU-BE-05 se queda con el camino del **agente** y recibe una
  nota de alcance. Mezclar los dos actores en CU-BE-05 daría un CU que **ningún plan puede cerrar entero**
  (sus escenarios 1, 3 y 5 dependen de nodos LLM que no existen).

### Confirmación

`CU-BE-12` (Gherkin) + FR-049…FR-056 en [`spec.md`](../backend/spec.md) +
[`rag-ingestion.md`](../backend/rag-ingestion.md) §4/§6. Implementación y tests: plan `kb-retriever`,
tareas `-01`…`-07` — integración contra Postgres+pgvector para adaptadores y router, unit con dobles para
`app/rag/*` y el adaptador de embeddings, más el test de guardia contrato↔OpenAPI de `-07`.

## Consecuencias

- **Buena**: el panel deja de ver una KB vacía, y los tres modos de fallo (petición mal formada,
  proveedor caído, BD caída) se distinguen entre sí y del vacío legítimo.
- **Buena**: la política de negocio es **testeable sin Postgres** (funciones puras en `app/rag/`), y el
  adaptador queda listo para un índice ANN sin arrastrar un `ORDER BY` ponderado que lo dejaría
  inservible.
- **Buena**: el `score` crudo llega intacto al plan del agent-graph, que puede componer la confianza
  híbrida sin contar `estado` dos veces.
- **Mala, aceptada**: el `score` de `/kb/search` **puede superar `1.0`** y ya no es interpretable como
  similitud coseno. Es el precio de que la lista esté de verdad ordenada por relevancia.
- **Mala, aceptada**: `total` responde "cuántos documentos distintos hay **en la ventana**", no "cuántos
  hay". Es la única respuesta honesta que admite un ANN, y se documenta como tal (RN-3 de CU-BE-12).
- **Mala, aceptada**: la paginación no es estable frente a una re-ingestión concurrente (RN-8).
- **Mala, aceptada — deuda**: dos puertos y dos adaptadores para la misma tabla, con la disciplina de "un
  solo sitio por operación" como única garantía de que no divergen.
- **Riesgo operacional**: el umbral de los 50.000 chunks **no tiene alarma**. Se cruzará en silencio.
- **Coste de contrato**: tocar `api-contract.yaml` **mueve** `frontend/src/types/api.ts` y
  `frontend/src/mocks/contract/openapi.json` (`openapi-typescript` emite el mapa de `responses` por
  operación). Se regeneran y se commitean en la misma tarea; si no, `pnpm gen:api:check` le deja un diff
  ajeno al siguiente que pase por ahí.

## Pros y contras de las opciones

- **Opción 1 (política en `app/rag/`, ventana, elegida)** — *Pros*: la política se testea sin infra; el
  re-ranking opera sobre una ventana suficientemente ancha para cambiar la página visible; `total` y
  `items` cuentan la misma unidad; el adaptador queda apto para un índice ANN. *Contras*: se recupera y
  se re-rankea más de lo que se muestra (hoy gratis, no siempre); `total` es una verdad acotada que hay
  que explicar; y la ventana introduce dos settings más.
- **Opción 2 (todo en SQL)** — *Pros*: una sola query, sin trabajo en Python. *Contras*: mete **política
  de negocio en infra**, deja inservible cualquier índice ANN futuro (el `ORDER BY` deja de poder usarlo),
  y no se puede testear sin Postgres. Además `DISTINCT ON` obliga a ordenar por `uc_id` antes que por
  score, con una subconsulta que oscurece justo lo que hay que poder leer.
- **Opción 3 (sin ventana, `top_k = page * page_size`)** — *Pros*: recupera lo justo. *Contras*: el
  re-ranking solo reordena dentro de lo ya recuperado, así que un `active` relevante nunca sube de
  página; y `total` como `COUNT` de candidatos responde a **otra pregunta** ("cuántos pasan los filtros",
  no "cuántos son relevantes"), que además crecería con el corpus sin relación con lo que se muestra.
- **Opción 4 (stub como fallback conmutable)** — *Pros*: el panel nunca devuelve error. *Contras*: es
  precisamente **el fallo mudo**: un despliegue sin clave de OpenAI o sin corpus se presentaría como una
  KB legítimamente vacía, y nadie lo miraría hasta que alguien preguntara por qué `/kb` no encuentra nada.
