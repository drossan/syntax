---
id: backend-kb-retriever
package: backend
status: active           # pending | active | completed | cancelled
branch: plan/backend/kb-retriever
created: 2026-08-24
updated: 2026-08-25
---

# Retriever de la KB — camino de lectura real (tarea 14, CU-BE-05 + CU-BE-12)

## Contexto y problema

La **ingestión** de la KB está cerrada (plan `kb-source-packages-uc`, PR #9 **mergeada** a `main` el
2026-08-24 → `b871474`). El camino de **lectura** existe entero y está **vacío a propósito**:

| Pieza | Estado hoy | Fichero |
|---|---|---|
| `SqlAlchemyKBIndexWriter.search()` | `raise NotImplementedError("search real: tarea 14…")` | `app/infra/vector/__init__.py:168-177` |
| `StubVectorStore` | `return [], 0` / `return None` | `app/infra/vectorstore/stub.py:16-40` |
| `get_vector_store()` | `return StubVectorStore()`, sin dependencias | `app/core/deps.py:115-118` |
| `app/rag/{retriever,reranker,confidence,citations}.py` | **guión** (solo docstring "→ tarea 14") | `app/rag/*.py` |

Consecuencia observable: `/kb` en el panel está vacío aunque la KB se ingiera.

### Hallazgos verificados al planificar (no estaban en el encargo)

1. **`EmbeddingModel` no tiene `embed_query`** — el puerto está recortado a `embed_documents` a
   propósito (`app/domain/ports/embeddings.py`: *"sin `embed_query` todavía — lo fijará el retriever
   (14), sin caller en este plan: no se fija una firma sin consumidor"*). Ese criterio del repo es el
   que acota qué entra y qué no (ver *Fuera de alcance*).
2. **`RAG_ESTADO_WEIGHT` no existe** en `app/core/config.py`: solo se menciona en el docstring-guión de
   `app/rag/reranker.py` y en ADR-0010.
3. **No hay índice ANN** sobre `embedding.vector` (`app/infra/db/models/kb.py:7`). Ver **D4**.
4. **Hueco SDD**: **ningún CU ni ningún FR cubre el camino HTTP de la KB**. El actor de CU-BE-05 es el
   *agente LangGraph*, no un usuario del panel; `kb.read` solo aparece en `rbac.md` y en la RN-3 de
   CU-BE-03. Los tres endpoints se construyeron en `routers-core` contra `api-contract.yaml`, **antes**
   de la capa SDD.
5. **`snippet` es drift contrato↔implementación** (hallazgo del `grilling`): declarado en
   `api-contract.yaml:1305` y **renderizado** por el front (`kb-search.tsx:141`, `{hit.snippet}`), pero
   **ausente** en `app/domain/entities/business.py:157-167`, en `app/api/v1/schemas/kb.py:18-25` y en
   `_hit_to_schema` (`routers/kb.py:43-52`). Hoy no se nota porque el stub devuelve `[]`; **con datos
   reales cada tarjeta pintaría un snippet vacío**.

### Alcance real de CU-BE-05 aquí

CU-BE-05 tiene 5 escenarios. Solo el **2** (fallback sin filtro de dominio) y el **4** (draft ponderados,
no excluidos) son del retriever. El **1** (`classify` fija el dominio), el **3** (contexto insuficiente
escala) y el **5** (citas) dependen de nodos LLM del grafo, **inexistentes** → plan del agent-graph.
Este plan implementa la **mitad de recuperación** de CU-BE-05, más el **CU-BE-12** nuevo (camino HTTP).

## Objetivos

1. **El panel deja de ver una KB vacía.**
   - *Criterio de éxito*: test de integración con corpus sembrado — `GET /kb/documents` y
     `GET /kb/documents/{uc_id}` devuelven los documentos reales de `kb_document` (SQL plano, sin
     vectores), con sus filtros y su paginación.
2. **`GET /kb/search` recupera de verdad sobre pgvector.**
   - *Criterio de éxito*: test de integración con documentos de similitud conocida — orden `score desc`,
     filtros que acotan, peso de `estado` aplicado **sin excluir** `draft`, y un `snippet` no vacío por
     hit.
3. **`KBIndexWriter.search()` deja de lanzar `NotImplementedError`** y es la única puerta de entrada a
   la búsqueda ANN (la reusará el nodo `retrieve` del grafo en el plan siguiente).
   - *Criterio de éxito*: `grep -rn "NotImplementedError" app/infra/vector/` no devuelve nada.
4. **El camino de lectura queda cubierto por SDD y sin drift de contrato.**
   - *Criterio de éxito*: `/sdd-lint` verde sobre `CU-BE-12`, los FR nuevos y el ADR; `snippet` viaja
     end-to-end; `grep -rn "StubVectorStore" app/ tests/` no devuelve nada.
5. **Sin regresión.**
   - *Criterio de éxito*: `make test` verde sobre los **1064** tests actuales + los nuevos; `ruff` +
     `mypy --strict`; cosmic-ray `break: 80` sobre los ficheros tocados.

## Decisiones cerradas en `grilling` (2026-08-24)

Todas resueltas con el owner. Se materializan en el **ADR** de la tarea `-01`.

| # | Decisión | Resolución |
|---|---|---|
| **D1** | Embeber la consulta en el camino HTTP | **Embeber siempre, sin caché.** `get_vector_store()` pasa a recibir `Depends(get_db_session)` + `Depends(get_settings)`. `/kb/search` gana un modo de fallo **502** (`PortError` → 502 ya existe en `app/api/errors.py:159-160`). **Caché LRU descartada** para este plan: optimizaría sin métrica y su clave tendría que incluir modelo+dimensión o serviría vectores rancios al cambiar `embedding_model`. Queda como follow-up documentado. |
| **D2** | Qué es `total` en una búsqueda ANN | **Ventana de recuperación fija** (`RAG_SEARCH_WINDOW`): se recupera la ventana, se re-rankea entera, se deduplica y se corta por página. `total` = documentos distintos dentro de la ventana. Una `page` más allá de la ventana devuelve `items: []` con el mismo `total`. Descartados: `len(items)` (mentira armada para quien añada paginación), `COUNT` de candidatos (responde a otra pregunta), y quitar `total` del contrato (rompe front). |
| **D3a** | Chunks repetidos del mismo `uc_id` | **Dedup por `uc_id`**: un item por documento, con el `score`, el `section_type` y el `snippet` de su mejor chunk. El camino del **agente NO deduplica** (sigue viendo chunks con `chunk_id`). Motivo: sin `chunk_id` en `KBSearchHit`, dos hits del mismo UC son dos tarjetas que enlazan al mismo sitio. Descartado exponer `chunk_id`/`ordinal` en el contrato (id interno que el contrato ocultaba a propósito; el front no lo pide). |
| **D3b** | Dónde se aplica el peso de `estado` | **En `app/rag/reranker.py`**, sobre la ventana. La infra devuelve **coseno crudo, sin política**. La objeción clásica ("solo reordena dentro del top-k") la neutraliza la ventana de D2: se re-rankea sobre la ventana y se corta a la página, así que un `active` en el puesto 45 por coseno crudo puede alcanzar la página visible. Descartado el `ORDER BY` ponderado en SQL: mete política en infra, deja inservible cualquier índice ANN futuro (D4) y no se puede testear sin Postgres. |
| **D3c** | Cómo llega el texto del chunk | **`Hit` gana `content`** (texto completo del chunk). Sirve al `snippet` hoy y al prompt del nodo `generate` mañana. Ampliar este DTO "congelado" es seguro: `search` nunca se ha ejecutado, no hay consumidor que romper. Descartado truncar en SQL (dejaría al agente sin el texto) y la segunda query por `chunk_id` (N+1 disfrazado de disciplina). |
| **D4** | ¿Índice ANN ahora? | **Diferido**, con umbral escrito en el ADR: crear **`hnsw`** (`vector_cosine_ops`) cuando `kb_chunk` supere **50.000 filas** (~30× el corpus actual). Motivo: con ~1626 chunks el seq scan es **exacto** y suficiente; un índice ANN lo volvería aproximado sin ganancia medida, e `ivfflat` sobre una tabla casi vacía saldría mal particionado. El docstring de `models/kb.py:7` deja de decir "diferido al plan RAG (13/14)" —que ya no sería cierto— y apunta al umbral. |
| **D5** | `StubVectorStore` | **Borrado**, con `tests/test_vectorstore_stub.py` y las 5 menciones en docstrings. Los tests de router del repo ya corren contra Postgres real, así que no se pierde cobertura. Descartado el fallback conmutable (convertiría un despliegue mal configurado en "KB vacía", el fallo silencioso que ADR-0017 identificó y que `rag-ingestion.md` §7 prohíbe). **El docstring de `ports/vector.py:10` se corrige**: prometía deprecar `VectorStore`, lo cual es imposible — `KBIndexWriter` no tiene `list_documents` ni `get_document`. |
| **SDD** | Dónde vive el Gherkin del camino HTTP | **CU nuevo `CU-BE-12-consulta-de-la-kb-desde-el-panel.md`** (actor = usuario de soporte con `kb.read`) + FR en `spec.md`. CU-BE-05 se queda con el camino del agente y recibe una nota de qué escenarios cubre este plan (2 y 4) y cuáles son del agent-graph (1, 3, 5). Descartado mezclar dos actores en CU-BE-05: daría un CU que ningún plan puede cerrar entero. |
| **Peso** | Fórmula del re-ranking | `score' = score * (1 + RAG_ESTADO_WEIGHT)` si `estado is active`; **`draft` intacto** (default `0.05`). El "suelo" de ADR-0010 se cumple **por construcción**: `draft` no se toca, luego no puede hundirse. Se devuelve el **score ponderado**, no el coseno crudo, para que la lista sea de verdad `score desc` (`api-contract.md:46`) — a documentar: el `score` puede llegar a `1.05` y ya no es una similitud coseno. Descartada la penalización con suelo: aplasta el orden del 81% del corpus. |
| **`q` vacía** | `GET /kb/search?q=` | `q.strip()` vacía → **422** con el envelope problem+json, **antes** de llamar al proveedor. Misma regla para `""` y `"   "`. Motivo: una búsqueda sin término es una petición mal formada, no una búsqueda sin resultados — y confundirlas reproduce el síntoma que este plan viene a eliminar. El front no se ve afectado (`useKbSearch` no dispara sin término). |

## Decisiones añadidas por `design-review` (2026-08-24)

El subagente adversario **tumbó el plan**: 7 bloqueantes, dos de ellos contradiciendo criterios que el
propio plan declaraba. Resoluciones, todas con el owner:

| # | Hallazgo | Resolución |
|---|---|---|
| **A1** | El plan decía que el dedup vive en `app/rag/` pero D3a dice que el agente **no** deduplica: o iba en infra (violando el criterio) o era un flag `dedup: bool` con una rama sin consumidor. | **Función pura `dedup_by_uc_id(ranked) -> list[...]` en `app/rag/`**, que llama **solo** el adaptador HTTP. El `retriever` devuelve chunks, sin deduplicar — el camino del agente los consume tal cual. Sin flags. |
| **A2** | Quedan dos puertos, dos adaptadores y acceso ORM a `kb_document` en dos módulos; la razón original para conservar `VectorStore` ("no tocar el router") ya no aplica. | **Se mantienen los dos puertos.** Motivo al ADR: router y agente son consumidores con formas distintas (página de documentos vs chunks con `chunk_id`), y colapsar metería lectura paginada de negocio dentro de un puerto llamado `KBIndexWriter` e invertiría la dirección de dependencia del router. **Deuda registrada.** Lo real del hallazgo se mitiga: el SQL de `kb_document` se parte por responsabilidad —escritura en `app/infra/vector`, lectura en `PgVectorStore`— con **un solo sitio por operación**. |
| **A3** | `search()` no filtraba por `embedding.model`: con vectores de dos modelos el coseno cruza espacios distintos y devuelve **basura perfectamente ordenada** — el fallo mudo que D5 usó para descartar el fallback. | `search()` **filtra `Embedding.model == settings.embedding_model`**. Escenario en `-04`. |
| **A4** | Un chunk sin fila `embedding` (caso real de `ChunkWrite.vector=None` sobre chunk nuevo) es invisible al JOIN, sin señal. | Escenario explícito en `-04`: no rompe la query y no aparece. |
| **A5** | `/kb/documents` sin `ORDER BY` → orden arbitrario; y `useKbRelated` (`frontend/.../use-kb.ts`) pinta ese resultado como **"relacionados"** en `/kb/[uc_id]` → 20 documentos arbitrarios del dominio etiquetados como relacionados. | **`ORDER BY uc_id ASC`** (único ⇒ estable) en `list_documents`, cubierto por un FR nuevo de CU-BE-12. |
| **A6** | Se introducía un 422 sin declararlo en el contrato (que los declara operación por operación, 11 refs a `ValidationError`). | **`'422'` + `'502'`** en `/kb/search` en `-01`. |
| **A7** | Tocar el contrato **sí** mueve `src/types/api.ts` y `src/mocks/contract/openapi.json`. | `-01` corre `pnpm gen:api` y commitea la regeneración. Ver *Desviaciones*, punto 3. |
| **B1** | La ventana de D2 se medía en **chunks** y `total`/`page` en **documentos** (~5.7 chunks/doc): con `page_size` hasta 100 la página 1 salía truncada y `total` mentía. | **Ventana expresada en DOCUMENTOS**: `RAG_SEARCH_WINDOW = 100` (= `page_size` máximo del contrato), implementada con over-fetch de `100 * RAG_CHUNKS_PER_DOC` chunks (**factor 6**, sobre los ~5.7 medidos). Garantiza que la página 1 nunca se trunca para ningún `page_size` legal y que `total` cuenta la misma unidad que `items`. Coste nulo hoy: sin índice ANN (D4) el seq scan ya calcula las 1626 distancias. |
| **B3** | `rag_top_k` era un setting sin consumidor, contradiciendo el criterio que el plan invoca para dejar `citations.py` en guión. | **Eliminado.** Lo añadirá el plan del agent-graph. |
| **C1** | `score * (1 + w)` **no es un boost si `score ≤ 0`**: `1 - cosine_distance` ∈ [-1,1] y con similitud negativa el boost penaliza e invierte el orden frente a `draft`. | **`score = max(0.0, 1.0 - distance)` en el adaptador.** Un coseno negativo es "menos relacionado que el azar": no hay ranking que preservar bajo 0. El reranker queda como función pura sin casos especiales. Escenario de similitud negativa en `-04`. |
| **C2** | El plan cambiaba qué significa `score` sin actualizar `rag-ingestion.md` §6, que lo define como "coseno normalizado" y lo usa como señal (a) de la confianza híbrida → el futuro `confidence.py` contaría `estado` **dos veces**. | **`Hit.score` se queda CRUDO** (coseno acotado, sin peso). El peso se aplica al producir el `KBSearchHit`: `rerank()` devuelve `RankedHit(hit, weighted_score)` y solo ese `weighted_score` viaja a la API. Así el plan del agent-graph conserva la señal cruda intacta. **`rag-ingestion.md` §4/§6 se actualiza en `-01`** (ventana, dedup, significado de `total` y del `score` de la API). |
| **D3'** | Faltaba la política del `snippet`; `kb-search.tsx:141` lo pinta **sin `line-clamp`**. | **Truncado a ~280 chars por límite de palabra + elipsis**, constante documentada del adaptador (no setting: no hay dos despliegues que la quieran distinta). **No** se recorta alrededor del término: la búsqueda es semántica y el chunk puede casar sin contener la palabra — al ADR va escrito que el snippet muestra **el principio de la sección ganadora**, no el fragmento que casa. |
| **E3** | No hay guardia contra el siguiente drift contrato↔implementación (`grep -rln "api-contract" backend/tests/` vacío); `snippet` llevaba roto desde `routers-core` y se descubrió por casualidad. | **Test de guardia en `-07`**: compara el OpenAPI de `create_app()` con `api-contract.yaml` para los schemas de KB (`KBSearchHit`, `KBDocument`). Acotado a KB — un diff global del contrato es otro plan. |

**Discrepancia registrada con el revisor (B2).** Propone no gastar escenarios de frontera en la
paginación "porque no tiene consumidor". Se acepta a medias: el gate de mutation (`break: 80`)
generará survivors sobre el código de slicing si no hay tests. Habrá tests **mínimos** de frontera
(página más allá de la ventana), no una batería.

**Lo que resistió la review**: D4 (y con el matiz de que un umbral sin alarma es una promesa que nadie
cumple — el ADR lo dice así), D3a (con evidencia más fuerte que la del plan: `kb-search.tsx:132` usa
`key={hit.uc_id}` ⇒ dos chunks del mismo UC serían **claves React duplicadas**), D5, D3c, D1 (verificó
que router y store comparten la **misma** `AsyncSession` por el caché de dependencias de FastAPI, así
que no se abren dos transacciones) y `q`→422.

### Desviaciones explícitas respecto al encargo original

1. **Sí se toca `app/api/v1/routers/kb.py`.** El encargo pedía "sustituir adaptadores sin tocar el
   router". El drift de `snippet` (hallazgo 5) y la validación de `q` (422) lo hacen imposible sin
   dejar el producto peor: con datos reales el front pintaría snippets vacíos. Se registra como
   desviación decidida, no como deslizamiento de alcance.
2. **Sí se toca un DTO declarado "FINAL"**: `Hit` gana `content` (D3c).
3. **`api-contract.yaml` gana el `502` y el `422`** en `/kb/search`, y eso **sí mueve artefactos del
   frontend** — corregido tras `design-review` (A7): `frontend/package.json:15-16` define
   `gen:api` (`openapi-typescript ../.claude/specs/general/api-contract.yaml`) y `gen:api:check` con
   `git diff --exit-code -- src/types/api.ts src/mocks/contract/openapi.json`. `openapi-typescript`
   emite el mapa de `responses` por operación, así que añadir respuestas cambia esos dos ficheros. La
   tarea `-01` corre `pnpm gen:api` y **commitea la regeneración**; si no, el siguiente que ejecute
   `gen:api:check` se encuentra un diff que no es suyo. (No hay `.github/workflows`: no rompe CI,
   rompe a una persona.)

   > Versión anterior de esta línea, **falsa**: *"los tipos generados del front no se mueven"*.

## Alcance y fuera de alcance

### Dentro del alcance

- `EmbeddingModel.embed_query` (puerto) + `OpenAIEmbeddingModel.embed_query` (adaptador, sobre
  `aembed_query` — verificado que existe en el paquete instalado).
- Settings nuevos en `app/core/config.py`: `rag_estado_weight` (0.05), `rag_search_window` (100
  **documentos**), `rag_chunks_per_doc` (6, factor de over-fetch). **No** `rag_top_k` (B3).
- `SqlAlchemyKBIndexWriter.search()` real: coseno pgvector (`Embedding.vector.cosine_distance(...)`,
  verificado en el `pgvector` instalado), filtros `domain`/`package`/`estado`, top-k, **score acotado a
  `max(0, 1-distance)`**, **filtrado por `Embedding.model == settings.embedding_model`**, y **sin
  política de negocio**.
- `Hit.content` en `app/domain/ports/vector.py`; `Hit.score` permanece **crudo**.
- `app/rag/reranker.py` (peso de `estado` → `RankedHit`), `app/rag/dedup` (`dedup_by_uc_id`, función
  pura) y `app/rag/retriever.py` (embed → ventana → rerank) reales.
- `PgVectorStore` en `app/infra/vectorstore/` (`search` + `list_documents` + `get_document`, este con
  `ORDER BY uc_id ASC`) + recableado de `get_vector_store()` + **borrado de `StubVectorStore`**.
- `snippet` end-to-end: entidad `KBSearchHit`, `app/api/v1/schemas/kb.py`, `_hit_to_schema`, con
  truncado a ~280 chars por límite de palabra + elipsis.
- Validación de `q` vacía → 422.
- SDD: `CU-BE-12` + FR en `spec.md` (incluido el del orden determinista) + ADR con **todas** las
  decisiones de `grilling` y `design-review`; nota de alcance en CU-BE-05; **actualización de
  `rag-ingestion.md` §4/§6**; corrección de los docstrings falsos (`ports/vector.py:10`,
  `models/kb.py:7`, `routers/kb.py:8`).
- `api-contract.yaml`: `422` + `502` en `/kb/search`, **más `pnpm gen:api` y el commit de
  `frontend/src/types/api.ts` + `frontend/src/mocks/contract/openapi.json`** (A7).
- Test de guardia contrato↔OpenAPI acotado a los schemas de KB.

### Fuera de alcance

- **Migración del índice ANN** (D4): diferida al umbral de 50.000 filas en `kb_chunk`.
- **Caché de vectores de consulta** (D1): follow-up documentado, sin métrica que lo justifique hoy.
- `app/rag/confidence.py` y `app/rag/citations.py`: **sin consumidor** hasta el plan del agent-graph.
  Fijar sus firmas ahora violaría el criterio explícito del propio repo (`ports/embeddings.py`,
  `ports/llm.py`: *"no se fija una firma sin consumidor"*). Siguen en guión.
- Nodos `classify` / `grade` y los escenarios **1, 3 y 5** de CU-BE-05 → plan del agent-graph.
- Búsqueda híbrida **BM25** y re-rank por **cross-encoder**: diferidos por ADR-0010 y
  `rag-ingestion.md` §8.
- Tocar el `Protocol` `app/domain/ports/vectorstore.VectorStore` (su firma no cambia).
- Tocar **código** del frontend: la paginación de `/kb` no existe hoy y este plan no la crea, ni añade
  el `line-clamp` que le falta a la tarjeta (por eso el snippet se trunca en el backend). `snippet` ya
  está renderizado, así que empieza a funcionar solo. **Excepción**: `-01` regenera dos ficheros
  *generados* del front (`types/api.ts`, `mocks/contract/openapi.json`) — es regeneración mecánica
  desde el contrato, no código escrito a mano.
- Guardia global contrato↔OpenAPI para **todos** los routers: aquí solo se cubren los schemas de KB.
- Exponer `chunk_id` / `ordinal` en el contrato (D3a, descartado).
- Ejecutar `make migrate` / `make ingest` reales contra la fuente (~$0.007 de embeddings):
  **verificación manual del owner**, fuera del gate de toda tarea. Ninguna tarea los ejecuta.
- Cualquier referencia al nombre del cliente/proyecto del que se verificó el formato de la KB (decisión
  de `grilling` de un plan anterior; hay grep de guardia).

## Recursos externos

- Flujo canónico: `docs/guides/task-lifecycle.md` · arranque de tarea:
  `.claude/specs/backend/HOW-TO-START-A-TASK.md` (incl. la PRECONDICIÓN dura).
- Specs: `.claude/specs/backend/rag-ingestion.md` **§4** (peso de `estado`) y **§6** (contrato de
  retrieval) · `.claude/specs/backend/spec.md` (FR-023…FR-025, FR-035) ·
  `casos-de-uso/CU-BE-05-clasificacion-y-retrieval-rag.md` · `.claude/specs/general/api-contract.md`
  (`:46`, orden `score desc`) + `api-contract.yaml` (`:569-645` paths, `:1295-1305` `KBSearchHit`) ·
  `.claude/specs/general/testing.md` · `.claude/specs/general/coding-standards.md`.
- ADR: `0010-rag-pgvector-chunking-h2-tolerante-estado-peso.md` (**incluida su contranota de
  trazabilidad de 2026-08-24**) y `0017-tipos-de-fuente-de-kb-en-codigo-y-alias-de-package.md`.
- Precedentes de test: `tests/test_vector_adapter.py` (integración pgvector con `superuser_engine` +
  `TRUNCATE embedding, kb_chunk, kb_document`), `tests/test_router_kb.py` (superficie HTTP),
  `tests/test_openai_adapter.py` (adaptador con doble).
- Corpus real (cifra **reportada por el owner**, no re-ejecutada al planificar): 284 documentos
  (268 UC + 16 glosarios), 218 `draft` / 50 `active`, **1626 chunks** / 338.021 tokens.

## Estimación global

- **Tareas totales**: 7.
- **Esfuerzo estimado**: 16-24 h (≈ 1 sesión por tarea).
- **Recursos**: Postgres+pgvector de docker-compose para las tareas de integración
  (`docker compose -f backend/docker-compose.yml up -d db`). **No** hace falta clave de OpenAI: los
  tests usan dobles del puerto de embeddings.

## Criterios de calidad y verificación

- **TDD real**: test rojo ANTES, 1:1 desde los escenarios del CU enlazado (cada `Then` es un assert).
- **Hexagonal**: el dominio no importa infra; adaptadores en `app/infra/`; puertos en
  `app/domain/ports/`. `app/rag/` consume puertos, nunca SQL crudo. **La política de negocio (peso de
  `estado`, dedup) vive en `app/rag/`, no en el adaptador SQL** (D3b).
- Niveles por artefacto (`HOW-TO-START-A-TASK.md` §3): adaptadores pgvector → **integración** contra
  Postgres real; `app/rag/*` y el adaptador de embeddings → **unit con dobles**; router → integración.
- `make test` verde **sin regresión sobre los 1064** · `ruff` + `mypy --strict` · cero secretos.
- Gate de mutation `cosmic-ray` (`break: 80`, `make mutation`) sobre los ficheros tocados.
- Gate `/sdd-lint` y gate `fact-checker` (no-negociable) en el cierre de cada tarea.
- Commits `<task-id>: <conventional commit>` en `plan/backend/kb-retriever` (rama desde **`main`**,
  `b871474` — no hay rama de integración `dev` en este repo).

### Avisos operativos que se trasladan a sus fases

- **`mutation` / `fact-checker`**: **no solapar `pytest` con `cosmic-ray exec`** — cosmic-ray muta el
  fichero fuente **en disco** y un `pytest` concurrente falla en falso (precedente: una tanda de 22
  fallos fantasma).
- **`design-review`**: `models.design-review: claude-opus-4-8` en `.claude/task-pipeline.yml:33` **no es
  un id de modelo válido** → la fase **cae a `inherit`**. Lo arregla el owner aparte; este plan no lo toca.

## Tasks

<!-- Los ficheros de tarea se materializan en `.claude/tasks/pending/backend/` en el Paso 5 de
     `/plan-task`, tras `design-review`. -->

- [x] `backend-kb-retriever-01` (P1) — SDD + contrato: `CU-BE-12`, FR, ADR, `rag-ingestion.md` §4/§6, docstrings falsos, `422`/`502` + `gen:api`  · depends_on: —
- [x] `backend-kb-retriever-02` (P1) — `PgVectorStore.list_documents`/`get_document` (SQL plano, `ORDER BY uc_id ASC`)  · depends_on: backend-kb-retriever-01
- [ ] `backend-kb-retriever-03` (P1) — `embed_query` (puerto + adaptador OpenAI) + settings `RAG_*`  · depends_on: backend-kb-retriever-01
- [ ] `backend-kb-retriever-04` (P1) — `SqlAlchemyKBIndexWriter.search()` + `Hit.content` + clamp del score + filtro por `embedding.model`  · depends_on: backend-kb-retriever-01
- [ ] `backend-kb-retriever-05` (P2) — `app/rag/`: `reranker` (peso→`RankedHit`) + `dedup_by_uc_id` + `retriever` (ventana)  · depends_on: backend-kb-retriever-03, backend-kb-retriever-04
- [ ] `backend-kb-retriever-06` (P1) — `PgVectorStore.search` + `snippet` end-to-end (entidad, schema, `_hit_to_schema`, truncado)  · depends_on: backend-kb-retriever-02, backend-kb-retriever-05
- [ ] `backend-kb-retriever-07` (P1) — Swap: `get_vector_store()` + `q`→422 + borrar stub + reescribir `test_router_kb.py` + guardia del contrato  · depends_on: backend-kb-retriever-06

Notas de ejecución:

- **`-01` es doc-only** (se justifica en su `## Scenarios`; lo verifica `/sdd-lint`) y va primero porque
  `-02`…`-07` **enlazan** su Gherkin a `CU-BE-12` / `CU-BE-05` (`features.sdd: true`).
- **`-02`, `-04`, `-06` y `-07` son INTEGRACIÓN** contra el Postgres de docker-compose. KB es global →
  sin RLS que verificar (mismo criterio que `test_vector_adapter.py`). **`-03` y `-05` son unit** con
  dobles.
- **`-02` va temprano a propósito** (hallazgo D1' del `design-review`): `list_documents`/`get_document`
  son SQL plano y no dependen de embeddings, ventana, rerank ni dedup. Se implementan y verifican
  contra el adaptador **en aislamiento**, sin recablear `deps.py`.
- **El swap NO se puede partir** (declinación parcial de D1', razonada): el router resuelve los tres
  endpoints por la MISMA dependencia `get_vector_store()`, así que `/kb` no puede ver datos reales
  hasta que `search` también funcione — a menos que se partiera el puerto en dos, que es justo lo que
  A2 acaba de descartar. Por eso el swap es atómico en `-07` y el objetivo 1 se entrega ahí.
- **`-06` produce el `snippet`, `-07` lo publica**: el snippet lo genera el adaptador al mapear
  `Hit.content` → `KBSearchHit`, así que entidad y schema van con su productor (`-06`), no con el swap
  — evita que `-07` reabra un `KBSearchHit` que `-06` acaba de construir (hallazgo D2').
- **`-07` reescribe `tests/test_router_kb.py`**, que hoy asierta el vacío del stub como comportamiento
  esperado: es una regresión **legítima**, no un test roto. Y cuenta en su alcance las menciones
  huérfanas de `StubVectorStore` (`app/infra/agent_runner/stub.py:9`, `ports/vectorstore.py:5`).

## Registro de cambios del plan

- 2026-08-24: creado. Rama desde `main` (`b871474`) tras verificar que la **PR #9 está mergeada** (el
  encargo la daba por abierta). D1-D5 abiertas para el `grilling`.
- 2026-08-24: refinado con `grilling` (10 preguntas, 10 decisiones). Cerradas D1-D5 más la ubicación
  del Gherkin (CU-BE-12 nuevo), la fórmula del peso de `estado` y el tratamiento de `q` vacía.
  **Cambios de alcance derivados**: (a) el `grilling` descubrió que `snippet` es drift
  contrato↔implementación, lo que obliga a tocar `routers/kb.py` — desviación explícita del encargo;
  (b) `Hit` gana `content`, ampliando un DTO declarado "FINAL"; (c) la tarea del índice ANN **sale del
  plan** (D4, diferida con umbral); (d) se añade el borrado de `StubVectorStore` (D5); (e) el plan pasa
  de 6 tareas provisionales a 6 definitivas con otra descomposición.
- 2026-08-24: `design-review` (subagente adversario, `inherit` — `models.design-review` trae un id
  inválido). **Veredicto: el plan NO aguantaba.** 7 bloqueantes + 6 hallazgos de tamaño/descomposición.
  Resoluciones en la sección *Decisiones añadidas por `design-review`*. Cambios materiales:
  **(1)** se corrige una afirmación **falsa** del plan (los tipos generados del front **sí** se mueven al
  tocar el contrato — A7); **(2)** `search()` pasa a filtrar por `embedding.model` (A3) y a acotar el
  score a `[0,1]` (C1, la fórmula que cerró el `grilling` estaba rota para similitud negativa);
  **(3)** la ventana de D2 se redefine **en documentos** con over-fetch de chunks (B1: medía unidades
  distintas que `total`); **(4)** `Hit.score` se queda crudo y el peso viaja en un `RankedHit`, para no
  contar `estado` dos veces en el futuro `confidence.py` (C2); **(5)** `list_documents` gana orden
  determinista (A5, con impacto en los "relacionados" del front); **(6)** el dedup se fija como función
  pura en `app/rag/` llamada solo por el adaptador HTTP (A1, resolvía una contradicción interna);
  **(7)** se elimina `rag_top_k` (B3); **(8)** se añaden política de `snippet` (D3') y test de guardia
  contrato↔OpenAPI acotado a KB (E3); **(9)** el plan pasa de **6 a 7 tareas** y `list_documents`/
  `get_document` se adelantan a `-02` (D1'). Se **mantienen los dos puertos** (A2) con la deuda escrita,
  y se declina parcialmente D1' (el swap no se puede partir sin partir el puerto, que A2 descarta).
  Discrepancia registrada con el revisor en B2 (sí habrá tests mínimos de frontera de paginación: el
  gate de mutation los exige).
- 2026-08-24: descompuesto en **7 tareas** + materializado
  `.claude/specs/backend/casos-de-uso/CU-BE-12-consulta-de-la-kb-desde-el-panel.md`. Con
  `features.sdd: true` el Gherkin vive **solo** en el CU; las tareas enlazan y declaran qué escenarios
  materializan.
- 2026-08-24: `scenario-coverage` (subagente QA, modelo `sonnet` por `models.scenario-coverage`).
  **16 escenarios incorporados al CU** (fuente única), entre ellos tres huecos que ninguna tarea
  contemplaba: el **vector de dimensión incorrecta** devuelto por el proveedor (modo de fallo distinto
  de "proveedor caído"), el **fallo de base de datos** en `/kb/documents` —que no toca embeddings y
  solo tenía cubierto el 502 del proveedor— y el **vacío legítimo** (filtros sin coincidencias),
  indistinguible hasta ahora de un fallo. Cazó además dos **inconsistencias internas**: `-04` no
  listaba el escenario de similitud negativa que `design-review` había exigido, y el `## Spec` de `-07`
  pedía un test de construcción perezosa que su `## Scenarios` no declaraba. Y señaló que RN-2 describe
  **dos** comportamientos (peso y filtro opt-in) con Gherkin para uno solo.
  **Tres decisiones del owner** derivadas: **(a)** `q` gana un **límite superior** → 422, en la misma
  regla que la vacía (sin tope, un cliente con un bug quema cuota de embeddings); **(b)** la
  inestabilidad de paginación bajo re-ingestión concurrente se acepta como **limitación conocida**
  (RN-8) en vez de resolverse con cursores — sobre-ingeniería para una paginación que hoy no tiene UI;
  **(c)** los **glosarios** se exponen en el camino de lectura (RN-9), documentando que su
  `package`/`estado` son **defaults de escritura** (`pipeline.py:47-48`, verificado) y no hechos: quien
  filtre por `syntax-core`/`active` arrastra 16 documentos que no pertenecen ahí. Es un defecto **de la
  ingestión**, se corrige en su plan, no en este.
  **Ambigüedad de diseño resuelta en vez de convertida en escenario**: el cálculo del over-fetch vive en
  `-06` (camino HTTP) y `retrieve` solo recibe un `top_k` — la ventana es un concepto de paginación que
  el nodo del agente no usa.
  **Sección (B), fuera del alcance declarado — 5 hallazgos, todos mantenidos fuera** por decisión del
  owner: consistencia de paginación bajo re-ingestión (absorbido por RN-8 como limitación documentada),
  comportamiento del ANN a escala con índice `hnsw` (D4), `line-clamp`/paginación en el front, exponer
  `chunk_id`/`ordinal` en el contrato (D3a), y usar el corpus real como gate en vez de corpus sembrado.
  **Descartes del QA compartidos**: 403 (`require_capability` reutilizado sin cambios, ya cubierto por
  CU-BE-03), enum inválido en query params (422 estándar del framework), y las 8 dimensiones en `-01`
  por ser doc-only.
- 2026-08-25: plan **arrancado** (rama `plan/backend/kb-retriever` desde `main`, `b871474`) y **`-01`
  cerrada**. Ajustes materiales que salen de sus gates y que afectan a las tareas siguientes:
  **(1)** los FR nuevos son **FR-049…FR-056** (8, no 6): un AVISO de `/sdd-lint` sobre granularidad EARS
  obligó a separar el `score` devuelto (relevancia ponderada, puede superar `1.0`) de la similitud cruda,
  y a partir "listar + abrir + 404" en dos requisitos. `CU-BE-12` y `ADR-0018` referencian el rango nuevo.
  **(2)** `api-contract.yaml` gana un `components/responses/**BadGateway**` reutilizable (no existía; el
  único 502 del fichero era inline en adjuntos, que **no se toca**) y declara el `502` **también en
  `/kb/documents`** — el plan solo lo pedía en `/kb/search`, pero la ext. 2e del CU y el FR de fallos lo
  exigen ahí, y omitirlo dejaría que `-02` introdujera un código no contratado (lo que A6 marcó como
  bloqueante). **(3)** `q` queda con `minLength: 1` y **`maxLength: 512`** en el contrato —
  `scenario-coverage` decidió que hubiera tope, la cifra la fija esta tarea; **`-07` debe implementarlo**
  además de la validación de vacía/espacios. **(4)** El escenario de glosarios del CU se **partió en dos**
  (listar / abrir); `-02` recibe el título nuevo en su lista de escenarios. **(5)** Verificado que
  **`pnpm gen:api` sí mueve** `types/api.ts` y `mocks/contract/openapi.json` (A7 confirmado, regeneración
  commiteada). Gates: `/sdd-lint` 0 ERROR / 6 AVISO (5 corregidos, 1 reconocido), `fact-checker` 20/20
  VERIFICADO, `make test` 1064 sin regresión, frontend 332 en verde.
