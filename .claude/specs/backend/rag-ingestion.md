# Spec — RAG: ingestión de la KB y retrieval

> Fuente de verdad de cómo la documentación de Syntax entra en pgvector y cómo se recupera. La
> implementan **13** (pipeline de ingestión: loader/parser/chunker/embedder/CLI) y **14** (retriever); la
> **05** (agent-graph) consume el **contrato de confianza/citas** definido aquí. Aterriza en las tablas
> `kb_document`/`kb_chunk`/`embedding` de **03** (`data-model.md`). **Este fichero es la spec, no el
> código.** Diseñada contra el **formato real verificado** de la fuente restaurada (§ conteos abajo).
>
> **SDD** — Doc de **referencia** de la capa SDD. Requisitos en [`spec.md`](./spec.md); decisión en
> [ADR-0010](../adr/0010-rag-pgvector-chunking-h2-tolerante-estado-peso.md); flujos en
> [CU-BE-07](./casos-de-uso/CU-BE-07-ingestion-de-la-kb.md) y
> [CU-BE-05](./casos-de-uso/CU-BE-05-clasificacion-y-retrieval-rag.md).

## 1. Fuente

- **Primaria**: `~/Documents/Desarrollo/syntax/docs-site/domains/`.
  - `<dominio>/uc/UC-*.md` → **268** casos de uso (UC), repartidos en **17** dominios.
  - `<dominio>/index.md` → **17** índices de dominio (con `## Glosario`).
  - `domains/index.md` → índice raíz (tabla de dominios; **sin** `## Glosario` — es navegación).
  - Total: **286** `.md` = 268 UC + 18 `index.md`.
- **Fallback** (documentado, no primario): `docs-site/.vitepress/dist/llms-full.txt` (1.4M, corpus
  concatenado) y `.vitepress/dist/llms.txt` (índice). Se usan **solo** si la fuente `domains/` no está
  disponible; el parseo por-fichero de `domains/` es el camino canónico (metadatos más ricos).
- **Distribución `package`** (5 valores, del frontmatter): `syntax-api` (125), `syntax-cx` (59),
  `syntax-core` (58), `syntax-ax` (19), `syntax-render` (7).

## 2. Parsing

- **Frontmatter YAML** (los 268 UC lo traen): `title`, `domain`, `package`, `uc`. **No hay `url`**
  (0 ficheros) → `kb_document.source_url` se **deriva** de la ruta en el repo (03 §4.3), no se lee.
- **Bloque `::: info Trazabilidad`** (presente en los 268 UC): `Estado` (`draft`/`active`), `Package`,
  `Traza` (lista de rutas de código fuente). → `kb_document.estado`, `kb_document.traza`.
  - **Precedencia `package`**: si el `Package` de Trazabilidad difiere del frontmatter, **gana el
    frontmatter** (03 §4.3); se **loguea** la discrepancia (no se silencia).
- **Línea `Relacionado:`** (presente en 258 UC): links markdown a otros UC
  (`[título](/domains/<d>/uc/UC-*)`) → grafo de relacionados (metadato; opcional para expansión de
  contexto en retrieval, no obligatorio en Fase 1).
- **`index.md` per-domain**: se ingiere **solo** `## Glosario` (bloque de términos
  `### grupo` + `- **Término** — definición`) como chunks con `section_type=glosario`. `## Casos de uso`
  y `## Todos los dominios` son **navegación** → **no** se embeben. El `domains/index.md` raíz no se
  ingiere (tabla de navegación).

## 3. Chunking — por sección H2 **tolerante**

El chunker parte cada UC por sus encabezados **H2**, pero **no asume estructura fija** (verificado
contra la KB real):

- H2 casi-uniformes pero **no universales** (nº de UC de 268 que traen la sección, **agrupando
  variantes renombradas**): `Comportamiento` 268, `Fidelidad` 268, `Reglas e invariantes` 268,
  `Detalles observados en QA` 266, `Conceptos` 257. → **hay UC sin alguna sección** (`Conceptos` falta en
  11 UC; `Detalles observados en QA` en 2): el chunker **tolera H2 ausentes** (no falla, no rellena).
- **Variantes reales** (por eso las cifras "agrupadas" difieren del texto H2 exacto — `Reglas e
  invariantes` exacto = 262 → 6 renombrados; `Detalles observados en QA` exacto = 265 → 1 renombrado):
  `Reglas e invariantes (draft — comportamiento esperado)` (×5), `Reglas e invariantes (enlace de vista
  previa)`, `Detalles observados en QA y producto`, y H2 sueltos (`Matriz (resumen observable)`,
  `Decisión (resumen)`, `Entrada y consulta de un envío`…). → el chunker **tolera H2 renombrados/extra**:
  cada H2 se ingiere con su `section_type` normalizado (slug del título; variantes conocidas se mapean a
  la sección base, p.ej. cualquier `Reglas e invariantes*` → `reglas`).
- **No partir tablas** ni bloques de código a mitad: un chunk respeta los límites de estos. Un bloque de
  código sin cierre (fence sin su par de cierre en el resto del fichero) se trata como cerrado al final
  del documento — nunca se deja que "trague" el resto del fichero como si fuera código.
- **Chunk grande** (una sección que excede el presupuesto de tokens, `settings.chunk_token_budget` —
  hallazgo de `scenario-coverage`: sin este campo no había ningún valor ni tokenizador fijado; conteo
  con `tiktoken`, encoding del modelo de embeddings): se sub-parte por párrafos/listas, preservando
  `ordinal` para el orden dentro del documento; el sub-parte hereda el `section_type`. Un párrafo único
  sin separadores naturales que por sí solo excede el presupuesto **no se parte a mitad de frase**: queda
  como un único chunk por encima del presupuesto (con log de aviso), preferible a cortarlo mal.
- Contenido **antes del primer H2** (párrafo intro tras el H1) → chunk con `section_type=intro`.

Cada chunk aterriza en `kb_chunk` (03 §4.3): `content`, `section_type` (string libre), `token_count`,
`ordinal`, `document_id`.

## 4. Categorización (metadatos por chunk)

Cada chunk queda categorizado por **5 facetas**, todas heredadas de su `kb_document` salvo
`section_type` (propia del chunk):

1. `uc_id` — clave del documento (frontmatter `uc`).
2. `domain` — 1 de los **17** dominios.
3. `package` — 1 de los **5** (`syntax-api`/`syntax-cx`/`syntax-core`/`syntax-ax`/`syntax-render`).
4. `estado` — `draft` | `active`.
5. `section_type` — tipo de sección H2 normalizado (§3).

### Peso de `estado` (señal de retrieval, explícito)

- La distribución real es **218 draft / 50 active** → **el 81% del corpus es `draft`**. Penalizar draft a
  ciegas vaciaría el retrieval.
- `estado` es una **señal de re-ranking con peso configurable** (`RAG_ESTADO_WEIGHT`), **no un filtro
  duro** por defecto. Default: peso **neutro-a-leve** (active recibe un pequeño boost; draft **no** se
  hunde por debajo de un suelo). El peso es un desempate, no un veto.
- Filtrar por `estado` (p.ej. solo `active`) es **opt-in** por consulta, no el comportamiento base.

## 5. Embeddings

- **Puerto abstraído** (adaptador en 09): default OpenAI `text-embedding-3-small`.
- **Dimensión**: `embedding.vector` es `vector(1536)` **literal** en el ORM/migración (03 §8 lo describe
  como "desde config, no literal" — desviación real introducida en `database-foundation` para que
  `Settings` no se importe a nivel de módulo del ORM y evitar un falso negativo del drift-test; `03 §8`
  queda desactualizado en esa frase, no corregido aquí). `settings.EMBEDDING_DIM` gobierna qué dimensión
  se le pide al proveedor (vía el parámetro `dimensions` de la API) — el pipeline hace **fail-fast**
  antes de embeber si `settings.EMBEDDING_DIM` no coincide con la dimensión literal de la columna, en
  vez de dejar que el `INSERT` falle a media ingesta. `embedding.model` guarda qué modelo generó cada
  vector.
- **Cambiar modelo/dimensión de verdad** ⇒ migración Alembic de la columna + re-embeber **todo** el
  corpus + reconstruir el índice pgvector (coste documentado en 03 §8): no es cambio en caliente ni solo
  de `.env`.
- **Upsert idempotente por `uc_id`** (03 §4.3): re-ingerir un UC no duplica; solo re-embebe un chunk si
  su **contenido cambió** respecto al ya persistido para su `(document_id, ordinal)` — comparación
  directa de contenido, sin columna de hash dedicada.
- **Edición parcial de un UC** (hallazgo de `scenario-coverage`): cuando solo algunos chunks de un
  documento cambian, el `upsert` acepta un vector `None` para los chunks sin cambios ("no lo toques" —
  el adaptador conserva su `embedding` existente) y solo pide vector nuevo a los chunks con contenido
  cambiado. Evita re-embeber el documento entero por una edición parcial.
- **Tamaño de batch del proveedor**: `embed_documents` puede trocear internamente en sub-lotes de
  tamaño configurable si el número de textos supera el límite de items por request del proveedor —
  transparente para el llamante (sigue devolviendo un vector por texto, en orden).

## 6. Retrieval (contrato para 05/14)

- **Búsqueda**: similitud pgvector por **coseno**, top-k sobre `embedding` (semántica; BM25 híbrido
  **diferido**, fuera de alcance).
- **Filtros** (metadatos §4, aplicables por consulta): `domain` (el clasificador de 05 fija 1-de-17 y
  **filtra el retrieval**), `package`, `estado` (opt-in).
- **Confianza híbrida** (la consume 05 para auto vs escalado): la señal se compone de
  **(a)** la **similitud** de los chunks recuperados (score coseno normalizado, este spec/14) y
  **(b)** el **grade** del LLM sobre relevancia (nodo de 05). Este fichero fija **(a)** y la **forma de
  salida**; **05** fija el **umbral** y la política auto/escalado/insuficiente→nota-al-humano.
  - Salida del retriever (por chunk): `{ uc_id, chunk_id, section_type, title, source_url, domain,
    estado, score }`. La lista ordenada por score (con el re-ranking de `estado`, §4) alimenta el grade.
- **Citas**: cada respuesta del agente cita las fuentes usadas por `uc_id` + `title` + `section_type`
  (+ `source_url` derivado). Se persisten en `agent_run.sources` (03 §4.2).

## 7. Refuerzos (scenario-coverage)

- **Frontmatter malformado / `uc_id` ausente o duplicado**: comportamiento **definido, nunca silencioso**.
  - `uc_id` ausente o frontmatter no parseable → **skip + log** (nivel error; el doc no entra).
  - `uc_id` **duplicado** entre ficheros → **fail explícito del batch** (colisiona la clave de upsert;
    dos ficheros no pueden mapear al mismo `kb_document`). Se reporta el par en conflicto.
- **Doc retirado en origen** (ya no está en `domains/`): la ingestión **reconcilia**, no solo-upsert →
  los `kb_document` (y en cascada `kb_chunk`/`embedding`, 03 §7) **huérfanos** se **borran/tombstone**.
  Se implementa como diff del set de `uc_id` presentes vs los de la BD.
- **Precedencia `package`** frontmatter vs Trazabilidad → **frontmatter gana**, se loguea si difieren (§2).
- **Señal `estado`** ≈ **218 draft / 50 active** (81% draft) → peso explícito, no penalizar a ciegas (§4).
- **3+ ficheros con el mismo `uc_id`**: se reportan **todos** los ficheros en conflicto, no solo un par.
- **Fallo real a mitad de un batch** (proveedor de embeddings o escritura en BD, no de validación): aborta
  **todo** el run — mismo criterio "todo o nada" que el `uc_id` duplicado, para cualquier causa de fallo.
- **Ejecuciones concurrentes**: la ingestión toma un **advisory lock de Postgres** al arrancar; una
  segunda ejecución simultánea espera o falla claro, nunca corre en paralelo con la primera.

## 8. Fuera de alcance

- Implementar loaders/parser/chunker/embedder/CLI (**13**) ni el retriever (**14**): aquí solo la spec.
- Búsqueda híbrida **BM25** / re-rank por cross-encoder: diferidos (plan).
- Umbral de confianza y política auto/escalado: los fija **05** (aquí solo la señal de similitud + forma).
- Recrear la fuente `domains/*/uc`: lo hace el owner (ya restaurada).
- **Fallback `llms-full.txt`/`llms.txt`** (§1): documentado como camino no-primario; ninguna tarea del
  plan `kb-ingestion` lo implementa — se deja para cuando haya un caso real que lo necesite.
