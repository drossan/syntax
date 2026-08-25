# Session log — `backend-kb-retriever-04` — `SqlAlchemyKBIndexWriter.search()` real (pgvector)

> Append-only. Registro canónico de la tarea (task-lifecycle §Cerrar una tarea).

## 2026-08-25 — Arranque

- **Gate TDD comprobado**: `depends_on: [backend-kb-retriever-01]` en `done`; rama del plan; ninguna otra
  tarea `active` (`-03` cerrada en `46f0db9`). Tarea → `active/`.
- **Leído en esta sesión**: el task file, `CU-BE-12` y `CU-BE-05` (los dos CU que materializa),
  `app/infra/vector/__init__.py` entero, `app/domain/ports/vector.py`, los modelos
  `KBChunk`/`Embedding`/`KBDocument` y `tests/test_vector_adapter.py`.
- **Decisión pendiente que la tarea dejaba abierta** ("decidir en la sesión cómo llega `settings` al
  adaptador sin romper a los callers de ingestión"): **`__init__(session, *, embedding_model: str | None
  = None)`**.
  - Verificado el alcance del problema antes de decidir: **~60 call-sites** construyen el adaptador con
    solo `session` (`app/ingestion/cli.py` + `test_pipeline.py`, `test_pipeline_packages_uc.py`,
    `test_vector_adapter.py`). Hacerlo obligatorio los rompería todos para darles un dato que **no usan**.
  - Se inyecta **el `str` del modelo, no `Settings` entero**: es lo único que el adaptador necesita, y
    así `app/infra/vector` no gana una dependencia de `app.core.config` que hoy no tiene.
  - Construido sin él, `search` **falla explícito** con `PortError` en vez de comparar contra vectores
    de cualquier modelo. Tiene test propio: la alternativa silenciosa es justo el fallo mudo que el
    hallazgo A3 vino a evitar.
  - La firma del **puerto** no se toca: el modelo de embeddings es detalle de infra, no del dominio.

## 2026-08-25 — TDD

- **Rojo primero**: 17 tests nuevos en `tests/test_vector_adapter.py` escritos **antes** de la
  implementación; rojo confirmado en esta sesión (`17 failed, 26 passed`).
- **Verde**: `search()` real (`JOIN embedding → kb_chunk → kb_document`, `ORDER BY
  cosine_distance ASC`, `LIMIT top_k`) + `Hit.content`.
- **Decisiones de implementación**:
  1. **Vectores "eje" en los tests** (`_axis(i)`: un `1.0` en una posición, `0.0` en el resto), no el
     `_vector(v)` = `[v] * 1536` que ya existía en el fichero. Motivo: todos los `[v] * 1536` son
     **proporcionales entre sí**, así que su coseno es siempre 1 y **cualquier orden pasaría el test**.
     Con vectores eje las similitudes son conocidas de antemano: `e0·e0` = 1, `e0·e1` = 0,
     `e0·(-e0)` = -1.
  2. **`Hit.content` sin default**: verificado con `grep` que **nadie construye `Hit`** todavía (la
     firma estaba fijada pero `search` nunca se había ejecutado), así que puede ser obligatorio. Un
     `content: str = ""` permitiría construir un hit sin texto en silencio.
  3. **`score = max(0.0, 1.0 - distance)`** en el adaptador, no en `app/rag/`: el clamp es una
     propiedad del **dato** (una similitud coseno no baja de -1 y por debajo de 0 no hay ranking que
     preservar), no una política de negocio.
  4. El **peso de `estado` y el dedup NO están aquí**: el `ORDER BY` no lleva expresiones ponderadas,
     que es lo que deja utilizable un índice ANN futuro (D3b/D4).
- **Regresión legítima, no un test roto**: se **elimina** `test_search_raises_not_implemented`, que
  asertaba el `NotImplementedError` como comportamiento esperado. Documentaba el andamio de la tarea 09;
  su desaparición es el objetivo de esta tarea (ítem de la DoD:
  `grep -rn "NotImplementedError" app/infra/vector/` → **sin resultados**, verificado).

## 2026-08-25 — Gates y cierre

- **`make test`**: **1135 passed** (1119 previos + 17 nuevos − 1 eliminado), sin regresión.
- **`ruff check` + `ruff format --check` + `mypy app`**: limpios (138 source files).
- **Gate de mutation** sobre `app/infra/vector/__init__.py` (213 mutantes): primera pasada **2.82%**
  (6/213) — **gate ya superado**, pero dos survivors eran **reales** y se mataron igual:
  1. `Embedding.model == …` → `<=`: el "otro modelo" del test (`text-embedding-ada-002`) ordena
     **después** del configurado, así que la desigualdad daba el mismo resultado. Añadido un tercer
     documento con un modelo que ordena **antes** (`a-modelo-legacy`).
  2. `KBDocumentModel.package == …` → `<=`: mismo patrón que ya apareció en `-02`. El test filtraba por
     el package **menor** en orden alfabético; ahora filtra por uno con vecinos a **ambos lados**
     (`syntax-api` antes, `syntax-render` después).
  - Los 4 restantes son **equivalentes** (`*` → `/` en dos firmas y sus variantes): todas las llamadas
    son por keyword. Segunda pasada: **1.88%**.
- **Gate `/sdd-lint`**: la tarea **no toca artefactos SDD** — verificado con
  `git diff --name-only HEAD -- .claude/specs/` → vacío. Mecánicos re-ejecutados y limpios.
- **Docs — tres capas**: (1) **docstrings**: `search` (con el porqué del clamp, del filtro por modelo y
  de por qué la política NO vive aquí), `Hit` reescrito entero (unidad = chunk, `content` completo,
  `score` crudo y el motivo: si viajara ponderado, `confidence.py` contaría `estado` dos veces), el
  `__init__` con el porqué del parámetro opcional, y el docstring de módulo, que decía que `search`
  quedaba en `NotImplementedError`; (2) **doc técnica**: sin cambios — `rag-ingestion.md` §6.1 ya
  describe exactamente esta salida desde `-01`; (3) **histórico**: este log.
- **Ficheros**: `app/infra/vector/__init__.py` (M), `app/domain/ports/vector.py` (M),
  `tests/test_vector_adapter.py` (M, +17 −1), `cosmic-ray.toml` (M).
- **Tiempo real**: ~3h (estimado 4h).
- **Follow-ups**: ninguno propio. `-05` consume esta `search` desde `app/rag/`; `-06` la cablea en
  `PgVectorStore.search` pasándole `settings.embedding_model`.
- **Gate `fact-checker`** (subagente fresco, `model: sonnet`): **17/17 VERIFICADO**, 0 INCORRECTO, 0 NO
  VERIFICABLE. Reprodujo el **SQL generado** por el `stmt` real (`embedding.vector <=> :vector_1 AS
  distance`, con los dos JOIN, `ORDER BY … ASC` y `LIMIT`); comprobó que `cosine_distance` vive en el
  `Comparator` de `pgvector 0.5.0` (no en `Vector` directamente) y funciona; que el `PortError` por
  `embedding_model` ausente salta **antes** de construir el `stmt`; que `cli.py:130` sigue construyendo
  con solo `session`; y que el `ORDER BY` no lleva expresiones ponderadas. Validó además el **argumento
  matemático** de los vectores eje: `[a]*1536` y `[b]*1536` con `a,b>0` son múltiplos escalares
  positivos, luego su coseno es siempre 1 y no sirven para fijar un orden. Re-ejecutó `make test`
  (1135), ruff/mypy y `make mutation` (1.88, exit 0).
