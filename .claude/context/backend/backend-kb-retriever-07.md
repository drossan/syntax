# Session log — `backend-kb-retriever-07` — Swap del adaptador, `q` vacía, borrado del stub, guardia

> Append-only. Registro canónico de la tarea (task-lifecycle §Cerrar una tarea). **Última tarea del plan.**

## 2026-08-25 — Arranque

- **Gate TDD comprobado**: `depends_on: [backend-kb-retriever-06]` en `done` (`ca0a2df`); rama del
  plan; ninguna otra tarea `active`. Tarea → `active/`.
- **Leído en esta sesión**: el task file, `CU-BE-12`, `app/core/deps.py` entero, `app/api/errors.py`
  (mapeo `Validation`→422, `RequestValidationError`→422 problem+json ya registrado en `app/main.py`),
  el router `kb` de `-06`, `app/domain/ports/vectorstore.py`, y las 7 referencias verificadas a
  `StubVectorStore` que la tarea listaba.
- **Verificado antes de escribir**: `RequestValidationError` de FastAPI **ya** produce 422
  `problem+json` (`app/main.py:54,101`) — así que `Query(..., min_length=1, max_length=512)` basta
  para vacío/demasiado larga; **solo espacios** necesita el check manual (`q.strip()`), porque
  `min_length` cuenta caracteres, no los distingue de espacios.

## 2026-08-25 — Diseño: el fail-fast de dimensión (hallazgo E de la tarea)

- **Riesgo verificado**: `OpenAIEmbeddingModel.__init__` lanza `PortError` **al construir** si
  `settings.embedding_dim != EMBEDDING_DIM_LITERAL` (`-03`). Los tres endpoints de `/kb` comparten la
  **misma** dependencia `get_vector_store()` — si esta construyera el adaptador de embeddings de forma
  eager, `/kb/documents` (que no toca embeddings) se tumbaría con un 502 ajeno a lo que pidió.
- **Resuelto con `_LazyEmbeddingModel`**: envoltorio que implementa `EmbeddingModel` sin construir el
  adaptador real hasta la primera llamada (`embed_query`/`embed_documents`), momento que solo dispara
  `/kb/search`. Vive en `deps.py` (capa de wiring, no de dominio) como clase privada, con una
  dependencia propia `get_embeddings_port()` — **separada** de `get_vector_store()** a propósito, para
  que los tests puedan sobrescribirla con un doble sin tocar la sesión ni el resto del cableado.

## 2026-08-25 — TDD

- **Rojo confirmado de verdad, no fabricado**: escribí `test_router_kb.py` (28 tests) **junto con** la
  implementación —no en el orden estricto rojo→verde, porque necesitaba explorar el mecanismo real de
  validación (`RequestValidationError`/`Validation`) antes de poder escribir cualquiera de los dos con
  sentido—. Al ver que los 28 pasaban a la primera, hice la comprobación honesta que exige TDD: `git
  stash` de `deps.py`+`kb.py` (dejando solo el stub borrado y las nuevas dependencias declaradas en el
  test), re-ejecuté la suite y obtuve el rojo real: `ModuleNotFoundError: No module named
  'app.infra.vectorstore.stub'` / `ImportError: cannot import name 'get_embeddings_port'`. `git stash
  pop` y verde de nuevo. Documentado explícitamente porque las reglas de honestidad de la sesión piden
  no afirmar TDD si no ocurrió en ese orden.
- **Cambios**:
  1. `app/core/deps.py`: `_LazyEmbeddingModel` + `get_embeddings_port()` + `get_vector_store()`
     reescrito (`session`, `settings`, `embeddings` inyectados, devuelve `PgVectorStore` real).
  2. `app/api/v1/routers/kb.py`: `q: Query(..., min_length=1, max_length=512)` + check manual de
     `q.strip()` → `Validation` (422); docstring de módulo reescrito (ya no describe el stub).
  3. **Borrados**: `app/infra/vectorstore/stub.py`, `tests/test_vectorstore_stub.py`.
  4. **Docstrings corregidos** (las 5 menciones a `StubVectorStore` que quedaban, sin dejar el nombre
     literal en ningún sitio — la DoD exige que el grep no devuelva nada, no solo que no describan un
     comportamiento falso): `ports/vector.py`, `ports/vectorstore.py`, `infra/agent_runner/stub.py`,
     `infra/vectorstore/pgvector.py`.
  5. `tests/test_router_kb.py` **reescrito entero** (regresión legítima: la versión vieja asertaba el
     vacío del stub como comportamiento esperado).
  6. `tests/test_kb_contract_guard.py` **nuevo** (hallazgo E3): compara el OpenAPI de `create_app()`
     con `api-contract.yaml` para `KBSearchHit`/`KBDocument`, campo a campo. Pasó a la primera —
     esperable, `snippet` ya se cerró en `-06`; su valor es la **red futura**, no un fix retroactivo.

## 2026-08-25 — Gate de mutation: deuda ajena real, esta vez NO corregida

- **`app/api/v1/routers/kb.py`** (97 mutantes): primera pasada **17.53%** (17/97) — gate pasa pero con
  margen estrecho. Survivors reales: fronteras de `q` (`min_length=1` sin frontera de 1 carácter
  cubierta), `page`/`page_size` (`ge`/`le`/defaults sin cubrir en NINGUNO de los dos endpoints).
  Reforzado con 7 tests de frontera (uno por endpoint donde aplica). Segunda pasada: **2.06%** (2/97) —
  el único restante es el mutante **equivalente** `min_length=1→0`: con el check manual de
  `q.strip()` ya activo, un `q=""` se rechaza igual con `min_length=0` o `1` (el check manual lo
  atrapa de todas formas) — no hay entrada que los distinga.
- **`app/core/deps.py`** (43 mutantes, el fichero entero — 150+ líneas de las que esta tarea solo tocó
  ~45): primera pasada con `test_router_kb.py` como único test-command → **30.23%** (13/43), **gate
  falló**. Leídos uno a uno:
  - **2 REALES y MÍOS**: `if self._model is None:` en `_LazyEmbeddingModel._resolve()` sobrevivía a
    `is not None` y a `not ... is None`. Causa: **todos** los tests de `test_router_kb.py` sobrescriben
    `get_embeddings_port` con un doble, así que la clase perezosa real **nunca se ejercitaba** — la
    misma clase que resuelve el riesgo del hallazgo E quedaba sin cubrir. Corregido con
    `tests/test_deps_lazy_embedding.py` (5 tests unit, monkeypatcheando `app.core.deps.get_embedding_model`):
    construir no llama al factory; la primera llamada real sí; una segunda llamada **reutiliza** el
    modelo ya construido (no lo reconstruye); un fallo del factory se propaga como `PortError`; y
    `embed_documents` también resuelve perezoso, no solo `embed_query`.
  - **11 DEUDA AJENA, fuera del alcance de esta tarea**: en `get_current_subject`/`get_tenant_context`/
    `_unauthorized`/`get_db_session` — funciones que `-07` **no tocó**, sin cobertura contra el
    test-command estrecho porque sus tests reales viven en `tests/test_router_auth.py`. Ampliar el
    test-command a `test_router_kb.py + test_deps_lazy_embedding.py + test_router_auth.py` bajó la
    supervivencia a **13.95%** (6/43): los 6 restantes siguen siendo ese código de autenticación/RLS
    ajeno (comparación `purpose`, `is`/`==`/`and`/`or` de `tenant.status`, `get_session()` mutado a
    `[]`) — **decisión explícita de no tocarlos**: es código de seguridad fuera del encargo de este
    plan, y arreglarlo sin revisar sus propios casos de uso (CU-BE-01/CU-BE-03) sería alcance fuera de
    lo que implica la tarea. Se dejan como follow-up con nombre, no se corrigen aquí.
- **`cosmic-ray.toml` final**: `module-path = "app/core/deps.py"`, test-command con los tres ficheros
  de arriba.

## 2026-08-25 — Gates y cierre

- **`make test`**: **1215 passed** (1194 previos + 33 nuevos: 28 de `test_router_kb.py` + 2 de
  `test_kb_contract_guard.py` + 5 de `test_deps_lazy_embedding.py`, menos los del `test_router_kb.py`
  viejo y `test_vectorstore_stub.py` borrados), sin regresión.
- **`ruff check` + `ruff format --check` + `mypy app`**: limpios — **138 source files** (uno menos que
  el pico de `-06`: `stub.py` desaparece; los tres ficheros de test nuevos compensan).
- **`grep -rn "StubVectorStore" app/ tests/`**: **vacío** (ítem de la DoD, verificado literal — incluye
  los propios docstrings que antes lo mencionaban como referencia histórica; se reescribieron sin el
  nombre para que el grep no devuelva falsos positivos).
- **Guard grep** del nombre del cliente/proyecto: 0 resultados.
- **Gate `/sdd-lint`**: la tarea **no toca artefactos SDD** (los fijó `-01`) — verificado con
  `git diff --name-only HEAD -- .claude/specs/` → vacío.
- **Docs — tres capas**: (1) **docstrings**: `get_vector_store`/`get_embeddings_port`/
  `_LazyEmbeddingModel` (nuevos), `routers/kb.py` (módulo + `search`), y los 4 ficheros que mencionaban
  el stub; (2) **doc técnica**: cierre del plan — ver nota retro abajo; (3) **histórico**: este log.
- **Ficheros**: `app/core/deps.py` (M), `app/api/v1/routers/kb.py` (M), `app/domain/ports/vector.py`
  (M, docstring), `app/domain/ports/vectorstore.py` (M, docstring), `app/infra/agent_runner/stub.py`
  (M, docstring), `app/infra/vectorstore/pgvector.py` (M, docstring), `tests/test_router_kb.py`
  (reescrito), `tests/test_kb_contract_guard.py` (nuevo), `tests/test_deps_lazy_embedding.py` (nuevo),
  `cosmic-ray.toml` (M). **Borrados**: `app/infra/vectorstore/stub.py`, `tests/test_vectorstore_stub.py`.
- **Tiempo real**: ~4.5h (estimado 4h; incluye el gate de mutation en 2 ficheros con pasadas de deuda).
- **Follow-ups**:
  1. **`app/core/deps.py`, código de autenticación/tenant sin cubrir** (6 mutantes supervivientes):
     comparación `claims.get("purpose") > _ACCESS_TOKEN_PURPOSE` en vez de `!=`; `tenant.status ==` en
     vez de `is` (dos veces, uno de ellos un `and`/`or` real); `get_session()` mutado a `[]` sin que
     falle nada. Ninguno es de este plan — quien toque `get_current_subject`/`get_tenant_context`
     debería revisarlos contra CU-BE-01/CU-BE-03.
  2. El aviso conocido de `models.design-review: claude-opus-4-8` en `.claude/task-pipeline.yml` sigue
     sin corregir (lo arregla el owner).
  3. Caché de vectores de consulta (D1) y la migración del índice ANN a 50.000 filas (D4) siguen
     documentadas como follow-up en `ADR-0018`, no ejecutadas — no eran parte del alcance del plan.

## 2026-08-25 — Nota retro del plan (última tarea, cierre)

- **Estimación vs. real**: 16-24h estimadas; **~19.5h reales** (3+2+2+3+2+3.5+4.5), dentro de rango.
- **Sorpresas del plan** (no previstas al planificar, todas resueltas dentro del plan):
  1. El **incidente de `-06`**: una interrupción de sesión a mitad de `cosmic-ray exec` dejó una
     mutación sin revertir en disco (`*` → `<<`), y ningún test la detectó porque sobre-funcionaba en
     vez de romper. Encontrado por `fact-checker`, no por el gate de mutation. Lección para el repo:
     tras interrumpir `cosmic-ray exec`, hay que releer el fichero mutado antes de confiar en él.
  2. El gate de mutation sobre ficheros **grandes y compartidos** (`config.py` en `-03`, `deps.py` en
     `-07`) destapa dos tipos de hallazgo distintos que hay que saber separar: deuda **propia** de la
     tarea (se corrige) y deuda **ajena** de código no tocado, sin cobertura solo porque el
     test-command es más estrecho que el fichero (se amplía el test-command o se documenta como
     follow-up, nunca se corrige a ciegas fuera del encargo).
- **Dependencias no vistas**: ninguna — el orden `01 → {02,03,04} → 05 → 06 → 07` que fijó el plan se
  siguió sin re-planificación.
- **Qué haría distinto**: acotar `cosmic-ray.toml` por **diff**, no por fichero completo, evitaría el
  ruido de deuda ajena en ficheros compartidos grandes — pero la herramienta no lo soporta hoy; queda
  como mejora de tooling, no de este plan.
- **Gate `fact-checker`** (subagente fresco, `model: sonnet`): **14/14 VERIFICADO**, 0 INCORRECTO, 0 NO
  VERIFICABLE. Sobre la afirmación de proceso TDD (§14), **replicó él mismo** la comprobación: hizo su
  propio `git stash` de `deps.py`+`kb.py`, obtuvo el mismo `ModuleNotFoundError` citado en este log, y
  restauró con `stash pop` sin dejar residuo (`git stash list` vacío al terminar). Confirmó también que
  los dos tests de 200-vs-502 con el mismo doble de embeddings existen y aciertan cada uno su código.
