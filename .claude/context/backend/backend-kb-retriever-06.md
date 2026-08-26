# Session log — `backend-kb-retriever-06` — `PgVectorStore.search` + `snippet` end-to-end

> Append-only. Registro canónico de la tarea (task-lifecycle §Cerrar una tarea).

## 2026-08-25 — Arranque

- **Gate TDD comprobado**: `depends_on: [backend-kb-retriever-02, backend-kb-retriever-05]`, **las dos
  en `done`** (`b2ae1c2` y `bb163a5`); rama del plan; ninguna otra tarea `active`. Tarea → `active/`.
- **Leído en esta sesión**: el task file, `CU-BE-12` (RN-1, RN-3, RN-4, RN-5), `pgvector.py` de `-02`,
  `app/rag/retriever.py`/`reranker.py`/`dedup.py` de `-05`, la entidad `KBSearchHit` y su schema, y
  `_hit_to_schema` del router.

## 2026-08-25 — TDD

- **Rojo primero**: 24 tests nuevos en `tests/test_pgvector_store_search.py` escritos **antes** de la
  implementación; rojo confirmado con `ImportError: cannot import name 'SNIPPET_MAX_CHARS'`.
- **Verde**:
  1. `PgVectorStore.search`: over-fetch (`rag_search_window * rag_chunks_per_doc`) → `Retriever.retrieve`
     → `dedup_by_uc_id` → recorte a la ventana → página. `total = len(ventana)`.
  2. `snippet` end-to-end: `KBSearchHit` (entidad y schema) gana `snippet: str`, `_hit_to_schema` lo
     propaga, `_snippet()` trunca a `SNIPPET_MAX_CHARS` (280) por límite de palabra + elipsis.
  3. Constructor de `PgVectorStore` gana `embeddings`/`settings`, **ambos opcionales**: `-02` ya lo
     construía con solo `session` para `list_documents`/`get_document`, y esa forma de uso **sigue
     funcionando** — `search` sin ellos falla explícito con `PortError` en vez de intentar buscar sin
     saber qué modelo comparar.
- **Decisiones de implementación**:
  1. **El `PortError` de "faltan embeddings/settings" se distingue del de fallo de infraestructura**:
     mismo tipo de excepción (no hay una jerarquía más fina en el repo), pero el mensaje dice
     explícitamente qué falta — es un error de **programación** (construir mal el store), no un fallo
     runtime, y así queda documentado.
  2. **`_snippet()` como función módulo, no método**: no toca `self`, así que no hay motivo para que
     sea un método — más fácil de testear aislada si hiciera falta.
  3. **`SNIPPET_MAX_CHARS = 280`, constante exportada** (no un setting, decisión ya fijada por `-01`):
     se exporta para que el test compruebe la frontera exacta (`len(content) == SNIPPET_MAX_CHARS`) sin
     hardcodear el número dos veces.
- **Gate de mutation, primera pasada — supervivencia real, no ruido**: sobre 315 mutantes, 22
  supervivieron (6.98%, ya por debajo del `break: 80`, pero se cazaron igual porque eran reales):
  1. **Over-fetch `*` → `+`/`**`/`<<`/`|`/`^`**: ningún test comprobaba que el `top_k` fuera
     **suficientemente grande** para llegar al último documento cuando la ventana tiene varios
     documentos de varios chunks. Test nuevo: 3 documentos de 6 chunks cada uno, similitud decreciente
     **por documento**; con `window=3, chunks_per_doc=6` (18 chunks) entran los 3 — cualquier operación
     que no sea el producto (p.ej. una suma daría 9) se queda corta.
  2. **`len(content) <= SNIPPET_MAX_CHARS` → `<`**: frontera exacta sin cubrir. Test nuevo con
     `content` de longitud **exactamente** `SNIPPET_MAX_CHARS`: se sirve entero, sin elipsis.
  3. **`last_space > 0` → `==0`/`!=0`/`<0`/`<=0`/`>=0`/`not >0`** (6 mutantes del mismo `if`): el test
     de "una sola palabra larguísima" no tenía **ningún** espacio, así que `last_space == -1` y todas
     las variantes de comparación con 0 coincidían. Test nuevo: el único espacio está en la
     **posición 0** — cortar ahí vaciaría el snippet entero (`""` + elipsis), así que `> 0` es la única
     condición correcta; se comprueba que el snippet **no** queda vacío.
  - Segunda pasada, con los 3 tests nuevos: **0.00%** (0/315). Sin equivalentes esta vez.
- **`make test`**: **1191 passed** (1164 previos + 27 tests: 24 de TDD + 3 de mutation), sin regresión
  antes del incidente de abajo; **1194** tras los 2 tests añadidos al recuperarlo (30 tests en total en
  `test_pgvector_store_search.py`).

## 2026-08-25 — Interrupción de sesión (aviso operativo, no del código)

- La sesión se cerró y reabrió a mitad del gate de mutation (`/exit` del usuario). El proceso en
  background del `make mutation` quedó **stopped** sin resultado confirmado (`cr-report` mostró
  `295/315 jobs completos` al reanudar) — se **relanzó desde cero** (`rm -f session.sqlite`) para no
  dar por bueno un resultado parcial.
- Al reanudar, `make test` dio **461 errores**: el contenedor `backend-db-1` de docker-compose se había
  caído junto con la sesión anterior (`docker compose ps` → sin contenedores). **Diagnóstico verificado
  antes de tocar nada**: se levantó `docker compose -f docker-compose.yml up -d db` y `make test` volvió
  a dar **1191 passed** sin ningún otro cambio — confirma que el síntoma era la DB caída, no una
  regresión introducida por el reinicio de sesión.

## 2026-08-25 — Mutación sin revertir en disco (INCIDENTE REAL, no solo un aviso operativo)

- Tras la recuperación de la interrupción de sesión, el `fact-checker` (ver abajo) encontró que
  `pgvector.py:116` tenía `top_k=window << self._settings.rag_chunks_per_doc` — un **desplazamiento de
  bits**, no la multiplicación `window * self._settings.rag_chunks_per_doc` que el código y el
  docstring decían. **Causa real, no hipótesis**: el `make mutation` que quedó `stopped` a mitad
  (bt68az6f9) fue interrumpido por el `/exit` **durante** un job de `cosmic-ray exec`, que muta el
  fichero **en disco** y lo revierte al terminar ese job — la interrupción de proceso no le dio tiempo a
  revertir, y la mutación quedó **persistida** como si fuera código real.
- **No lo detectaron los tests ni el gate**: con `window=100, chunks_per_doc=6` de producción, `<<` pide
  6400 chunks en vez de 600 — sigue "funcionando" (sobre-pide de más, no de menos), así que ningún test
  de corrección lo distingue. El propio gate de mutation de esa pasada (2ª, la que dio 0.00%) mutaba
  **desde** el `<<` ya corrompido, así que nunca comparó contra el `*` correcto.
- **Corregido** en cuanto el `fact-checker` lo reportó: `<<` → `*`. Revisado el resto del fichero
  entero por si quedaba otra mutación sin revertir (comparado línea a línea con lo escrito en esta
  sesión) — limpio. `git diff --name-only HEAD` en los ficheros de tareas ya cerradas (`-02`/`-04`) dio
  vacío, así que el daño se limitó a este fichero de esta sesión.
- **Lección para el repo**: `make mutation` interrumpido a mitad (Ctrl-C, cierre de sesión, kill) puede
  dejar código mutado en disco sin que ningún test lo note si la mutación "sobre-funciona" en vez de
  romper. Tras cualquier interrupción de `cosmic-ray exec`, no basta con re-lanzar el gate — hay que
  **releer el fichero mutado** antes de confiar en él.
- Re-verificado desde cero tras el fix: `make test` (1191, luego 1194 con 3 tests más — 2 de la reserva
  `and`/`or` real que el mismo incidente destapó, ver abajo), `ruff`/`mypy` limpios, `make mutation`
  limpio corriendo **en exclusiva y sin interrupciones**.

## 2026-08-25 — Gates y cierre

- **`ruff check` + `ruff format --check` + `mypy app`**: limpios (139 source files).
- **Gate de mutation**, tres pasadas por el incidente de arriba: 6.98% (con la primera reinforcement,
  antes del incidente) → tras el fix del `<<` y sin refuerzo nuevo: **4.13%** (13/315) → con 2 tests
  más para un `and`/`or` real (`self._embeddings is None or self._settings is None` mutado a `and`
  también sobrevivía) y el default de `page_size`: **3.17%** (10/315), pasada final, ejecutada **sin
  interrupción**. Los 10 restantes: `*`↔`<<`/`**` en el over-fetch (indistinguibles con un corpus de
  test razonable — solo se notan en presupuesto, no en corrección), dos fronteras finas de
  `last_space` (`!=0`/`<0`, ambas equivalentes a `>0` para los casos de test sin más contorsión), y 3×
  `*`→`/` en firmas keyword-only (equivalentes, como en el resto del plan).
- **Gate `/sdd-lint`**: la tarea **no toca artefactos SDD** — verificado con
  `git diff --name-only HEAD -- .claude/specs/` → vacío.
- **Docs — tres capas**: (1) **docstrings**: `PgVectorStore.search` (con el porqué de los 4 pasos y de
  los dos parámetros opcionales), `_snippet()` (con sus 3 reglas de frontera), `KBSearchHit` en entidad
  y schema (con el porqué de `score` ponderado y `snippet` no centrado), `_to_search_hit`; (2) **doc
  técnica**: sin cambios — `rag-ingestion.md` §6.3 ya describe exactamente esta salida desde `-01`;
  (3) **histórico**: este log.
- **Ficheros**: `app/infra/vectorstore/pgvector.py` (M, `search` + `_snippet` + `SNIPPET_MAX_CHARS`),
  `app/domain/entities/business.py` (M, `KBSearchHit.snippet`), `app/api/v1/schemas/kb.py` (M,
  `KBSearchHit.snippet`), `app/api/v1/routers/kb.py` (M, `_hit_to_schema` propaga `snippet`),
  `tests/test_pgvector_store_search.py` (nuevo), `cosmic-ray.toml` (M).
- **Tiempo real**: ~3.5h (estimado 4h; incluye la recuperación de la interrupción de sesión).
- **Follow-ups**: ninguno propio. `-07` solo tiene que cablear `get_vector_store()` a este
  `PgVectorStore` ya completo, y puede escribir la guardia contrato↔OpenAPI sabiendo que `KBSearchHit`
  ya trae `snippet` en entidad, schema y router.
- **Gate `fact-checker`** (subagente fresco, `model: sonnet`, **dos pasadas** por el incidente):
  - 1ª pasada (antes del fix): detectó el `<<` sin revertir en `pgvector.py:116` — el hallazgo que
    disparó la corrección de arriba. 15/16 VERIFICADO, 1 FALSO (justo ese).
  - 2ª pasada (tras el fix, **12/12 VERIFICADO**, 0 INCORRECTO): re-leyó el fichero **completo**
    contrastando cada operador contra su docstring adyacente —línea por línea, foco explícito en
    encontrar otra mutación oculta— y no encontró ninguna; confirmó el `git diff HEAD` del fichero
    limpio; confirmó los 30 tests (12 nuevos correctos, sin `pass` vacíos); confirmó que
    `deps.py`/`StubVectorStore` siguen intactos (el swap sigue siendo de `-07`).
