# Session log — `backend-kb-retriever-05` — `app/rag/`: re-ranking, dedup y retriever

> Append-only. Registro canónico de la tarea (task-lifecycle §Cerrar una tarea).

## 2026-08-25 — Arranque

- **Gate TDD comprobado**: `depends_on: [backend-kb-retriever-03, backend-kb-retriever-04]`, **las dos
  en `done`** (`46f0db9` y `303635e`); rama del plan; ninguna otra tarea `active`. Tarea → `active/`.
- **Leído en esta sesión**: el task file, `CU-BE-12` y `CU-BE-05`, los guiones de `app/rag/reranker.py`
  y `app/rag/retriever.py`, `app/domain/ports/vector.py` (el `Hit` que produce `-04`) y
  `app/domain/ports/embeddings.py` (el `embed_query` de `-03`).

## 2026-08-25 — TDD

- **Rojo primero**: 29 tests (18 en `test_rag_reranker.py`, 11 en `test_rag_retriever.py`) escritos
  **antes** de la implementación; rojo confirmado en esta sesión con
  `ImportError: cannot import name 'Retriever' from 'app.rag.retriever'`.
- **Verde**: `reranker.py` (`rerank` + `RankedHit`), `dedup.py` (`dedup_by_uc_id`) y `retriever.py`
  (`Retriever.retrieve`). Los tres guiones-docstring sustituidos por documentación real.
- **Decisión que la tarea dejaba abierta** ("`dedup` en fichero nuevo o dentro de `reranker.py`;
  decidir y justificarlo"): **módulo propio `app/rag/dedup.py`**.
  - Motivo: **el consumidor es distinto**. `rerank` lo usan **los dos** caminos (agente y HTTP);
    `dedup_by_uc_id` lo llama **solo** el adaptador HTTP. Ponerlos en el mismo módulo sugeriría que van
    en pareja e invitaría a llamarlos siempre juntos — exactamente lo que D3a prohíbe.
  - Sin flag `dedup: bool`: un booleano cuyas dos ramas tienen cada una su propio consumidor es una
    función distinta llamada desde sitios distintos, no un parámetro (hallazgo A1).
- **Decisiones de implementación**:
  1. **`RankedHit` envuelve el `Hit`, no lo copia campo a campo** (`ranked[0].hit is hit`, con test):
     el `score` crudo sobrevive intacto para la confianza híbrida de CU-BE-05, y nada se pierde por el
     camino — el `content` lo necesitan el snippet de `-06` y el prompt de `generate`.
  2. **Orden estable** vía `sorted` (garantizado por Python), con dos tests de empate: empate entre dos
     `draft` y empate **producido por el peso** (un `draft` de 0.525 empata con un `active` de 0.5 y
     `weight=0.05`). Sostiene la estabilidad de paginación de RN-6.
  3. **`Retriever` recibe `estado_weight: float`, no `Settings`**: la capa de aplicación no depende de
     la configuración global; el valor lo inyecta quien la construye.
  4. **`retrieve` no calcula el `top_k` ni deduplica**: los dos son concepto del camino HTTP (`-06`).
     Hay test explícito de que **no** deduplica, porque es lo que el agente necesita.
  5. Los dobles de test **fallan ruidosamente** si el retriever llama a `embed_documents`
     (`AssertionError` en el fake): embeber una consulta como si fuera un documento es un error
     silencioso plausible, y el doble lo convierte en un fallo visible.
- **Test que no viene de un escenario del CU** (declarado como tal): *no se llama al proveedor más de
  una vez por búsqueda*. Cada llamada cuesta dinero; es también la razón por la que la caché de vectores
  quedó como follow-up documentado en vez de optimizarse a ciegas.

## 2026-08-25 — Gates y cierre

- **`make test`**: **1164 passed** (1135 previos + 29 nuevos), sin regresión.
- **`ruff check` + `ruff format` + `mypy app`**: limpios (139 source files — uno más, `app/rag/dedup.py`).
  `ruff format` reformateó una comprensión de lista de `reranker.py`.
- **Gate de mutation** sobre **`app/rag`** (el directorio entero, 104 mutantes): **4.81%** (5/104) a la
  primera. Gate superado. Los 5 survivors son **equivalentes**, ninguno matable con un test de
  comportamiento:
  - 4 × `*` → `/` en las firmas keyword-only (todas las llamadas son por keyword).
  - 1 × `hit.estado is KbEstado.active` → `==`: los miembros de un `Enum` son **singletons**, así que
    `is` y `==` dan siempre el mismo resultado. No hay entrada que los distinga.
- **Gate `/sdd-lint`**: la tarea **no toca artefactos SDD** — verificado con
  `git diff --name-only HEAD -- .claude/specs/` → vacío. Mecánicos re-ejecutados y limpios.
- **Docs — tres capas**: (1) **docstrings**: los tres módulos de `app/rag/` pierden su cabecera "GUIÓN
  (→ tarea 14)" y ganan documentación real —por qué la política vive fuera del SQL, por qué `draft` no
  se toca, por qué hay dos scores, por qué el dedup tiene módulo propio y por qué `retrieve` no pagina—,
  conservando sus secciones de **anti-patrones**; (2) **doc técnica**: sin cambios — `rag-ingestion.md`
  §4 ya trae la fórmula exacta y §6.2/§6.3 el reparto de los dos caminos, escritos en `-01`; (3)
  **histórico**: este log.
- **Ficheros**: `app/rag/reranker.py` (M, guión → real), `app/rag/retriever.py` (M, guión → real),
  `app/rag/dedup.py` (nuevo), `tests/test_rag_reranker.py` (nuevo), `tests/test_rag_retriever.py`
  (nuevo), `cosmic-ray.toml` (M).
- **Tiempo real**: ~2h (estimado 3h).
- **Follow-ups**: ninguno propio. `app/rag/confidence.py` y `app/rag/citations.py` **siguen en guión** a
  propósito: no tienen consumidor hasta el plan del agent-graph.
- **Gate `fact-checker`** (subagente fresco, `model: sonnet`): **17/17 VERIFICADO**, 0 INCORRECTO, 0 NO
  VERIFICABLE. Comprobó que `app/rag/` **no importa nada de `app.infra`** (las menciones son solo de
  docstring), que `confidence.py`/`citations.py` siguen siendo guiones sin código ejecutable, que
  `retrieve` no llama al dedup ni calcula ventana, y que `sorted()` es estable por Timsort.
  - **Matiz suyo, aceptado y valioso**: el argumento de que `is` → `==` es un mutante equivalente se
    sostiene **porque `KbEstado` es un `enum.Enum` puro**, no un mixin `str`. Si heredara de `str`, `==`
    compararía por valor y el mutante **dejaría de ser equivalente**. Queda escrito por si alguien
    convierte los enums a `str`-mixin en el futuro.
