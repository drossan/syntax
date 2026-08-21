---
id: backend-kb-ingestion
package: backend
status: active
branch: plan/backend/kb-ingestion
created: 2026-08-21
updated: 2026-08-21
---

# Ingestión real de la KB (CU-BE-07)

## Contexto y problema

El backend ya implementó de verdad (código real, TDD, pytest+cosmic-ray en verde — 749 tests) auth,
RBAC/tenant, tickets, approvals, admin, notifications y analytics (planes `skeleton-foundation` →
`domain-services`/`routers-core`/`routers-flujo-ia`, todos `completed`). El **núcleo de IA generativa**
del producto —el motivo de ser de Syntax— sigue siendo solo esqueleto doc-only (ficheros con docstring
`GUIÓN`, cero código): el grafo del agente, el retrieval RAG, **la ingestión de la KB**, y el scheduler
de SLA.

Este plan implementa la primera pieza de esa cadena — **CU-BE-07, ingestión de la KB** — porque sin KB
ingerida no hay nada real que recuperar ni citar; es la base de la que dependen el retriever (CU-BE-05,
tarea 14) y el nodo `generate` del agente (CU-BE-06), ambos fuera de este plan.

**Precondición verificada, no asumida**: `backend/app/ingestion/{loader,parser,chunker,embedder,
pipeline,cli}.py` + `__main__.py` son GUIÓN puro (0 líneas de código, solo docstring). La tarea que los
dejó así (`backend-skeleton-foundation-13`, completada 2026-08-13) declaraba explícitamente "Fuera de
alcance: implementar la lógica real". La fuente real de la KB (268 UC / 17 dominios en
`~/Documents/Desarrollo/syntax/docs-site/domains/`) **no existe en esta máquina** — todo el desarrollo y
los tests usan fixtures `.md` representativas del formato real, nunca la fuente real.

**Tres huecos verificados leyendo el código (no en la spec/tarea original) que este plan sí resuelve**,
porque bloquean la implementación:

1. `Settings` (`app/core/config.py`) no declara `llm_provider`/`openai_api_key`/`chat_model`/
   `embedding_model` — pese a que `.env.example` ya los documenta, hoy se ignoran (`extra="ignore"`).
2. La spec (`rag-ingestion.md` §5, `CU-BE-07` 3a) exige "no re-embeber si el contenido no cambió" vía un
   hash, pero ni `KBChunk` ni la spec `data-model.md` tienen columna para ese hash.
3. La entidad de dominio `KBDocument` (`domain/entities/business.py`) no tiene `traza`, aunque el ORM sí
   la columna — y la spec exige parsear el bloque Trazabilidad.

## Objetivos

1. **Cualquier UC válido de la KB queda ingerido de verdad**: documento + chunks + embeddings reales en
   pgvector, vía `python -m app.ingestion` (`make ingest`).
   - *Criterio de éxito*: test de integración — una fixture `.md` con frontmatter+Trazabilidad válidos
     produce filas reales en `kb_document`/`kb_chunk`/`embedding` (Postgres+pgvector de Docker).
2. **Re-ingerir sin cambios no genera embeddings nuevos** (idempotencia, ahorro de coste real).
   - *Criterio de éxito*: test — dos ingestas consecutivas del mismo fichero disparan una sola llamada
     al proveedor de embeddings (fake en test); la segunda pasada reutiliza los vectores existentes.
3. **Un documento malformado no corrompe el corpus; un `uc_id` duplicado aborta el batch entero
   (todo-o-nada: la validación de duplicados corre en memoria antes del primer upsert — ninguna fila
   nueva de esa ejecución llega a BD si hay un par en conflicto)**.
   - *Criterio de éxito*: tests 1:1 con los escenarios Gherkin de `CU-BE-07` (skip+log / fail explícito
     con el par en conflicto, sin persistir nada de esa ejecución).
4. **Documentos retirados del origen se reconcilian** (no solo-upsert): sus filas se borran en cascada.
   - *Criterio de éxito*: test — un `uc_id` presente en BD pero ausente en el origen desaparece tras
     ejecutar la ingestión.
5. **El chunking es H2-tolerante** (no asume las 5 secciones fijas; no parte tablas/código a mitad).
   - *Criterio de éxito*: tests con fixtures que tienen H2 ausente, H2 renombrado y una sección que
     excede el presupuesto de tokens con una tabla dentro — la tabla llega entera a un solo chunk.

## Alcance y fuera de alcance

### Dentro del alcance

- `domain/ports/embeddings.py` (nuevo): puerto `EmbeddingModel` — solo `embed_documents`, sin caller
  para `embed_query` todavía (lo fijará el retriever, fuera de este plan).
- `infra/llm/openai_adapter.py`: **solo** la mitad de embeddings (`OpenAIEmbeddingModel` +
  `get_embedding_model()`, conmutable por `settings.llm_provider`). `OpenAIChatModel` (la otra mitad que
  anticipa el docstring del fichero) queda **fuera** — la implementará el plan del grafo del agente.
  **Fail-fast de dimensión** (hallazgo de `design-review`): `embedding.vector` es `Vector(1536)`
  **literal** en el ORM (`kb.py`, deliberadamente NO gobernado por `settings.embedding_dim` — hay un
  test de drift que lo protege). Antes de embeber, el adaptador comprueba
  `settings.embedding_dim == EMBEDDING_DIM_LITERAL` (importado desde `infra/db/models/kb.py`) y aborta
  con un error claro si no coincide, en vez de dejar que el `INSERT` falle a media ingesta. Cambiar
  `EMBEDDING_DIM` de verdad sigue exigiendo una migración de columna — fuera de este plan.
- `core/config.py`: añade `llm_provider`/`openai_api_key`/`chat_model`/`embedding_model` a `Settings`
  (hoy documentados en `.env.example` pero ignorados). `chat_model` se añade porque vive en el mismo
  `Settings` que el resto de config LLM, aunque no lo consuma código real todavía.
- `domain/ports/vector.py` (hoy solo docstring): puerto de **escritura** de la KB —
  `existing_uc_ids`/`existing_chunk_contents`/`upsert_document`/`delete_by_uc_ids` — nombrado
  `KBIndexWriter` (no `VectorStore`, para no colisionar con la clase `VectorStore` ya real de
  `domain/ports/vectorstore.py`, que es el puerto de **lectura** del router `kb` y pertenece a otra
  tarea). **Incluye también `search`** (firma vectorial: `search(query_vector: list[float], *, top_k:
  int, domain=None, package=None, estado=None) -> list[Hit]`, con `Hit = {uc_id, chunk_id, section_type,
  title, source_url, domain, estado, score}`, según `rag-ingestion.md` §6) para fijar ya el contrato que
  usará el retriever (tarea 14, fuera de este plan) — decisión de `grilling` (owner): fijar el shape
  ahora en vez de esperar a que exista un caller. El adaptador de la tarea 02 la implementa con
  `raise NotImplementedError` (sin test de esa rama: no hay caller que la ejercite todavía).
- `infra/vector/__init__.py` (hoy solo docstring): adaptador SQLAlchemy+pgvector real de ese puerto
  (`upsert_document`/`existing_uc_ids`/`existing_chunk_contents`/`delete_by_uc_ids`; `search` con
  `NotImplementedError`). Incluye una migración Alembic aditiva y de bajo riesgo:
  `UniqueConstraint(document_id, ordinal)` en `kb_chunk` (clave natural para el diff de re-ingesta; no
  añade columna, no requiere backfill).
- `domain/ports/vector.py` también define `KBDocumentDraft` (tipo propio de escritura, con `traza`) —
  no se toca la entidad `KBDocument` compartida con el puerto de lectura (su shape ya es "el final" para
  la tarea 14).
- `app/ingestion/{loader,parser,chunker,embedder,pipeline,cli}.py` + `__main__.py`: implementación real
  completa, TDD, fiel a `rag-ingestion.md` y al Gherkin de `CU-BE-07`. Decisiones de `grilling` (owner):
  - `package`/`domain` del frontmatter con un valor fuera de los enums válidos (5/17) → **skip+log**,
    igual que cualquier otro frontmatter malformado (CU-BE-07 1a) — no es un caso más grave.
  - Discrepancia `package` (frontmatter vs Trazabilidad, RN-1c) → **solo log estructurado** (`structlog`,
    ya en el repo, ADR-0015), nivel warning; no forma parte del `IngestReport` devuelto.
  - `OpenAIEmbeddingModel` pasa siempre `dimensions=settings.embedding_dim` al proveedor (no solo lo
    documenta): cambiar la config cambia de verdad el tamaño del vector devuelto — sujeto al fail-fast
    de arriba.
  - **Actualiza `rag-ingestion.md` §5 y `CU-BE-07` (escenario 3a)** de "mismo hash" a "mismo contenido":
    la decisión de `grilling` (clave natural + comparación de contenido, sin columna de hash) deja esa
    redacción desalineada con el código (hallazgo de `design-review`).
  - **Chunks huérfanos dentro de un documento que sigue vivo** (hallazgo de `design-review`): si el
    re-chunking de un UC editado produce menos `ordinal` que antes, `upsert_document` debe borrar (con
    cascada a `embedding`) los `ordinal` del documento que ya no llegan en la nueva pasada — no solo
    los documentos retirados por completo. Se fija como escenario Gherkin explícito en la tarea 06.
  - **"Todo-o-nada" también cubre las reconciliaciones** (hallazgo de `design-review`): si el batch
    aborta por un `uc_id` duplicado, NO se ejecuta ningún borrado de documentos retirados en ese mismo
    run tampoco — inserciones y reconciliación son la misma transacción lógica "todo o nada".
- Fixtures `.md` en `backend/tests/fixtures/kb/domains/...` (mismo layout que la fuente real) para no
  depender de la KB real (ausente en esta máquina).
- Extiende `CU-BE-07` si `scenario-coverage` encuentra huecos; no toca otros CU.
- **Decisiones de `scenario-coverage` (owner)**:
  - Edición parcial de un UC (algunos chunks cambian, otros no): `upsert_document` acepta un
    `ChunkWrite.vector = None` como "no lo toques" — el adaptador conserva el `embedding` existente de
    ese `ordinal`; el pipeline solo pide vector nuevo a los chunks con contenido cambiado. Sin método
    nuevo en el puerto.
  - `embed_documents`/el pipeline pueden trocear internamente en sub-lotes de tamaño configurable si
    el batch supera el límite de items por request del proveedor — transparente para el llamante.
  - `ingest()` toma un **advisory lock de Postgres** al arrancar (`pg_try_advisory_lock`, no bloqueante):
    una segunda ejecución concurrente falla claro de inmediato, nunca espera ni corre en paralelo.
  - Sin librería de parseo Markdown nueva: loader/parser/chunker siguen con parseo manual por
    líneas/regex (ya bastaba para el formato verificado; evita pedir una dependencia nueva).
  - El log de `skip`/discrepancia de `package` (CU-BE-07 1a/1c) se testea con `pytest caplog` +
    `structlog` configurado para reenviar al `logging` estándar — patrón nuevo en este repo (sin
    dependencias nuevas), documentado como tal.
  - Nuevo `Settings.chunk_token_budget` (default a fijar en la tarea `-04`) + `tiktoken` (ya en
    requirements) con el encoding del modelo de embeddings, para el presupuesto de tokens del chunker.
  - Fallo real (proveedor/BD, no de validación) a mitad de un batch de varios documentos → aborta
    **todo** el run, mismo criterio que el `uc_id` duplicado.
  - 3+ ficheros con el mismo `uc_id` → se reportan **todos** los ficheros en conflicto, no solo un par.
  - La CLI distingue código de salida de error de uso (args malformados) del de fallo de negocio
    (p.ej. `2` vs `1`).

### Fuera de alcance

- **Retriever real / búsqueda semántica** (CU-BE-05, tarea 14): la implementación real de `search`
  (tanto la del router `kb` como la del futuro nodo `retrieve` del agente) queda fuera de este plan —
  `KBIndexWriter.search` se define aquí (firma) pero se deja con `NotImplementedError`. **Resolución del
  doble contrato** (hallazgo de `design-review`, decisión del owner): `KBIndexWriter.search` (este plan)
  es el que la tarea 14 implementará de verdad; `domain/ports/vectorstore.py::VectorStore` y su
  `StubVectorStore` (el puerto de lectura ya real, usado hoy por el router `kb`) quedan **deprecados en
  la tarea 14**, no en este plan — este plan NO los toca ni los borra, solo deja constancia de cuál
  gana para que la tarea 14 no tenga que redescubrir esta decisión.
- **`OpenAIChatModel` real** (clasificación/generación del agente): sigue GUIÓN; lo implementará el plan
  del grafo del agente (CU-BE-06), que este plan no toca.
- **Recrear la fuente real** `domains/*/uc/*.md`: la restaura el owner cuando corresponda; este plan
  nunca depende de ella, solo de fixtures.
- **BM25 híbrido / re-rank por cross-encoder**: diferido (ya lo dice `rag-ingestion.md` §8).
- **Ejecutar `make ingest` contra la KB real** como parte del gate de ninguna tarea (no hay fuente real
  en esta máquina) — queda como verificación manual del owner cuando tenga la fuente disponible.
- **Grafo del agente / scheduler de SLA**: siguen GUIÓN; son planes propios, no este.
- **Fallback `llms-full.txt`/`llms.txt`** (`rag-ingestion.md` §1, documentado como camino no-primario):
  ninguna tarea lo implementa — se deja para cuando haya un caso real que lo necesite (hallazgo de
  `scenario-coverage`, decisión del owner: declararlo fuera de alcance explícito en vez de ampliar `-03`).
- **Citas históricas (`agent_run.sources`) invalidadas por un re-ingest** que sustituye un `chunk_id` —
  hallazgo de `scenario-coverage`, cae dentro de "retriever real / tarea 14" (consumidor de citas), no
  de este plan.
- **Contrato de `search`/`Hit` bajo carga real** (fronteras de `top_k`, filtros combinados, orden del
  re-ranking, lecturas concurrentes con una re-ingesta en curso) — no testeable mientras `search` sea
  `NotImplementedError`; cae en la tarea 14.

## Recursos externos

- `.claude/specs/backend/rag-ingestion.md` — spec completa de ingestión (fuente de verdad del
  comportamiento: parsing, chunking H2 tolerante, categorización, embeddings, refuerzos §7).
- `.claude/specs/backend/casos-de-uso/CU-BE-07-ingestion-de-la-kb.md` — Gherkin de aceptación (fuente
  1:1 de los tests).
- `.claude/specs/backend/data-model.md` §4.3/7/8 — schema `kb_document`/`kb_chunk`/`embedding`.
- `.claude/specs/adr/0010-rag-pgvector-chunking-h2-tolerante-estado-peso.md` — decisión de arquitectura.
- `backend/app/infra/db/models/kb.py` — ORM ya real de las 3 tablas (sin tocar, salvo la migración
  aditiva del `UniqueConstraint`).
- Patrón de test de puertos con dobles (`_FakeChatModel`): `backend/tests/test_classification.py`.
- Patrón de test de repos contra Postgres real (Docker): `backend/tests/test_repositories_ticket.py` +
  `conftest.py` (fixture `superuser_engine` + `TRUNCATE` autouse).
- `langchain-openai==1.5.1` (ya instalado en `.venv`): `OpenAIEmbeddings.aembed_documents`/
  `aembed_query` verificados contra el paquete real, no adivinados.
- Investigación previa (subagente Plan, 2026-08-21): huecos A/B/C de Contexto, decisión de nombrar
  `KBIndexWriter` (no `VectorStore`) para evitar colisión con `vectorstore.py`, y estrategia de test del
  adaptador OpenAI (`monkeypatch` de `aembed_documents` a nivel de SDK — patrón nuevo en este repo, a
  confirmar en `design-review`).

## Estimación global

- **Tareas totales**: 7 (ver lista abajo).
- **Esfuerzo estimado**: 20-24h / 7-8 sesiones (creció tras `scenario-coverage`: fail-fast del advisory
  lock, sub-lotes de embeddings, `chunk_token_budget`, más fronteras/errores por tarea).
- **Recursos**: ninguno externo; Postgres+pgvector ya corre en Docker en esta máquina; sin
  `OPENAI_API_KEY` real necesaria para el gate (tests con fake/monkeypatch del SDK).

## Criterios de calidad y verificación

- TDD con pytest; tests antes de la implementación en cada tarea.
- `make test` (pytest) + `ruff check`/`ruff format --check` + `mypy strict` en verde tras cada tarea.
- Gate de mutation testing (`cosmic-ray`, `break: 80` — vía `stack.packages.backend.mutation-command`,
  **referencia no verificada** en este plugin) sobre los ficheros que toca cada tarea.
- Arquitectura hexagonal: el dominio (`domain/ports/*`) no importa `langchain_openai`/SQLAlchemy; los
  adaptadores (`infra/*`) implementan los puertos.
- Adaptador pgvector: integración real contra Docker (Postgres+pgvector). Adaptador OpenAI de
  embeddings: contrato con `aembed_documents` parcheado a nivel de SDK (sin red real en CI).
- Regresión: los ~749 tests backend existentes siguen en verde.

## Tasks

- [x] `backend-kb-ingestion-01` (P1) — Puerto `EmbeddingModel` + adaptador OpenAI real + `Settings`
  LLM/embeddings · depends_on: —
- [ ] `backend-kb-ingestion-02` (P1) — Puerto `KBIndexWriter` + adaptador pgvector real (+ migración
  `UniqueConstraint(document_id, ordinal)`) · depends_on: —
- [ ] `backend-kb-ingestion-03` (P1) — Loader + parser (frontmatter + Trazabilidad + glosario)
  · depends_on: —
- [ ] `backend-kb-ingestion-04` (P2) — Chunker H2 tolerante · depends_on: `backend-kb-ingestion-03`
- [ ] `backend-kb-ingestion-05` (P2) — Embedder · depends_on: `backend-kb-ingestion-01`,
  `backend-kb-ingestion-04`
- [ ] `backend-kb-ingestion-06` (P1) — Pipeline (orquestación + reconciliación) · depends_on:
  `backend-kb-ingestion-02`, `backend-kb-ingestion-05`
- [ ] `backend-kb-ingestion-07` (P2) — CLI + entry-point (`make ingest`) · depends_on:
  `backend-kb-ingestion-06`

## Registro de cambios del plan

- 2026-08-21: creado (draft, plan mode) tras investigación verificada del código real (no solo la spec)
  tanto por mí como por un subagente Plan independiente; ambos confirmaron los mismos 3 huecos (A/B/C).
  Pendiente: `grilling` + `design-review` antes de descomponer en ficheros de tarea.
- 2026-08-21: `grilling` (owner) — decisiones:
  1. Nombre del puerto de escritura: `KBIndexWriter` (no `VectorStore`, evita colisión con
     `vectorstore.py`).
  2. `KBIndexWriter` **incluye ya `search`** (firma vectorial, `rag-ingestion.md` §6) para fijar el
     contrato del retriever ahora — desvío de mi recomendación (que era dejarlo fuera sin caller); el
     adaptador de la tarea 02 la implementa con `NotImplementedError`.
  3. Detección de "chunk sin cambios": clave natural `(document_id, ordinal)` + comparar `content` —
     sin columna de hash nueva.
  4. Migración aditiva `UniqueConstraint(document_id, ordinal)` en `kb_chunk`: **sí**, se incluye.
  5. `traza` en la entidad de escritura: tipo nuevo `KBDocumentDraft`, no se toca `KBDocument`
     (compartida con el puerto de lectura, ya cerrado para la tarea 14).
  6. Test del adaptador OpenAI de embeddings: `monkeypatch` de `aembed_documents` a nivel de SDK
     (patrón nuevo en este repo, documentado como tal, no como precedente silencioso).
  7. `package`/`domain` fuera de enum en el frontmatter → skip+log (igual que cualquier malformado).
  8. Discrepancia `package` (frontmatter vs Trazabilidad) → solo log estructurado, no en `IngestReport`.
  9. `uc_id` duplicado → todo-o-nada: se valida en memoria antes de cualquier upsert; ninguna fila de
     esa ejecución se persiste si hay conflicto.
  10. `OpenAIEmbeddingModel` pasa `dimensions=settings.embedding_dim` al proveedor (no solo lo valida).
  11. Descomposición en 7 tareas confirmada tal cual (sin cambios de agrupación).
  Todas mis recomendaciones se confirmaron salvo la (2).
- 2026-08-21: `design-review` (subagente fresco, sin `model` explícito — `models.design-review` en
  `task-pipeline.yml` es un id inválido, se avisó y se cayó a inherit; mismo aviso que en el plan
  frontend). Veredicto: NO daba el visto bueno sin cambios. Hallazgos y resolución:
  1. **[Bloqueante, corregido]** El plan se contradecía a sí mismo: "Dentro del alcance" decía que
     `vector.py` incluye `search`; "Fuera de alcance" decía que no. Era un resto de un borrador previo
     a `grilling`. Corregido arriba.
  2. **[Bloqueante, resuelto — decisión del owner]** `KBIndexWriter.search` (este plan) y
     `VectorStore.search` (ya real, `vectorstore.py`) competían por ser el contrato del retriever
     (tarea 14) con shapes incompatibles. Resuelto: `KBIndexWriter.search` es el que gana; `VectorStore`/
     `StubVectorStore` se deprecan en la tarea 14, no aquí. Anotado en Fuera de alcance.
  3. **[Riesgo real, corregido — decisión del owner]** `embedding.vector` es `Vector(1536)` literal en
     el ORM (protegido por un test de drift), incompatible en potencia con pasar
     `dimensions=settings.embedding_dim` al proveedor sin control. Resuelto: fail-fast
     (`settings.embedding_dim == EMBEDDING_DIM_LITERAL`) antes de embeber. Anotado en Alcance (tarea 01).
  4. **[Corregido]** La spec (`rag-ingestion.md`/`CU-BE-07`) sigue hablando de "hash" pese a la decisión
     de `grilling` #3 (comparación de contenido) — se actualiza en la tarea 03/06.
  5. **[Corregido]** Chunks huérfanos dentro de un documento que sigue vivo (re-chunking con menos
     `ordinal` que antes) no estaba cubierto explícitamente — se fija como escenario de la tarea 06.
  6. **[Corregido]** "Todo-o-nada" ante un `uc_id` duplicado se extiende explícitamente a las
     reconciliaciones (borrados), no solo a las altas nuevas.
  7. **[Anotado, no bloqueante]** El monkeypatch del SDK `langchain-openai` es un patrón de test nuevo
     en el repo (no detecta un cambio de forma de `aembed_documents` en un upgrade de la librería) — ya
     documentado como tal en Criterios de calidad; no se añade mitigación adicional en este plan.
  Hallazgos que resistieron (sin cambios): proporción de 7 tareas; migración
  `UniqueConstraint(document_id, ordinal)`; huecos A/C del Contexto; `skip+log` para enum inválido y
  discrepancia de `package`.
- 2026-08-21: `scenario-coverage` (subagente fresco, sin `model` explícito — `models.scenario-coverage`
  no está en `task-pipeline.yml` para este plan, inherit por ausencia). Informe con (A) huecos dentro de
  alcance por tarea + transversales, y (B) huecos fuera de alcance declarado. Decisiones del owner:
  1. **[Aplicado, diseño]** Gap real (no solo de test): `existing_chunk_contents` no exponía vector, sin
     camino para reconstruir `upsert_document` en una edición PARCIAL sin re-embeber todo el documento.
     Resuelto: `ChunkWrite.vector: list[float] | None`, `None` = "no lo toques" (conserva el embedding
     existente). Sin método nuevo en el puerto.
  2. **[Aplicado]** Límite de items por request del proveedor de embeddings (riesgo real con la KB
     completa): `embed`/pipeline troceen en sub-lotes internamente, transparente al llamante.
  3. **[Aplicado]** Concurrencia entre ejecuciones de `make ingest`: advisory lock de Postgres en
     `ingest()`.
  4. **[Rechazado, decisión owner]** Librería de parseo Markdown real (p.ej. `markdown-it-py`): no se
     añade — parseo manual por líneas/regex sigue siendo suficiente para el formato verificado.
  5. **[Aplicado]** Verificación de la emisión de logs (`skip`/discrepancia): `pytest caplog` +
     `structlog`→`logging` estándar. Patrón nuevo en este repo, documentado, sin dependencias nuevas.
  6. **[Aplicado]** `Settings.chunk_token_budget` (nuevo) + `tiktoken` para el presupuesto de tokens del
     chunker — no existía ningún valor ni tokenizador fijado en spec/código.
  7. **[Aplicado, decisión owner]** Fallback `llms-full.txt`/`llms.txt`: declarado fuera de alcance
     explícito del plan (no se amplía `-03`).
  8. **[Aplicado, decisión owner]** Fallo real (no de validación) a mitad de un batch multi-documento:
     aborta todo el run (mismo criterio que el `uc_id` duplicado, no éxito parcial).
  9. **[Aplicado, decisión owner]** 3+ ficheros con el mismo `uc_id`: se reportan todos los ficheros en
     conflicto, no solo un par.
  10. **[Aplicado, decisión owner]** Códigos de salida de la CLI distintos para error de uso vs fallo de
      negocio.
  11. **[Anotado, no aplicado]** Huecos (B) fuera de alcance (citas históricas invalidadas por
      re-ingest, contrato de `search`/`Hit` bajo carga real, validar contra la KB real, `OpenAIChatModel`,
      BM25 híbrido): confirmados como genuinamente fuera de este plan, añadidos explícitamente a "Fuera
      de alcance" para que quede constancia (no eran un olvido, son una decisión).
  Múltiples escenarios Gherkin menores (fronteras N=0/1/n, `existing_uc_ids`/`delete_by_uc_ids` con
  conjuntos vacíos, `yaml.safe_load` explícito, IO/encoding, etc.) incorporados directamente a las
  tareas correspondientes y a `CU-BE-07`/`rag-ingestion.md` — ver esos ficheros.
- 2026-08-21: **`backend-kb-ingestion-01` cerrada** (`completed`). TDD verde (771 tests totales),
  `ruff`/`mypy --strict` limpios, `cosmic-ray` con 0.00% de supervivencia (36/36 KILLED), `sdd-lint` con
  0 ERROR/5 AVISO (1 corregido — el Then no-determinista "espera o falla claro" de CU-BE-07 4a, alineado
  con la decisión real `pg_try_advisory_lock` no bloqueante; 4 reconocidos sin cambio, elaboración legítima
  del CU/spec más allá del FR), `fact-checker` con 8/8 VERIFICADO. Detalle en
  `.claude/context/backend/backend-kb-ingestion-01.md`.
