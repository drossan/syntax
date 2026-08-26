# Session log — `backend-kb-retriever-01` — SDD y contrato del camino de lectura de la KB

> Append-only. Registro canónico de la tarea (task-lifecycle §Cerrar una tarea).

## 2026-08-25 — Arranque

- **Arranque del plan**: `kb-retriever.md` → `.claude/plans/active/backend/` (`status: active`,
  `updated: 2026-08-25`). Rama `plan/backend/kb-retriever` creada desde `main` (`b871474`, ya
  `up-to-date`) — este repo **no tiene rama de integración `dev`**, decisión registrada en el plan.
- **Gate TDD comprobado**: `depends_on: []`, ninguna otra tarea del plan en `active`
  (`.claude/tasks/active/backend/` estaba vacío), rama correcta. Tarea →
  `.claude/tasks/active/backend/backend-kb-retriever-01.md` (`status: active`, `updated: 2026-08-25`).
- **Precondición dura** (`HOW-TO-START-A-TASK.md`): verificada como ya satisfecha en esta sesión —
  `backend/.venv/bin/python -c "import langgraph, structlog, pgvector"` responde `deps ok`. No
  re-ejecuto `make install`.
- **Leído** (esta sesión): `HOW-TO-START-A-TASK.md` (backend), `docs/guides/task-lifecycle.md`, el plan
  `kb-retriever.md` **entero** (incl. las 3 secciones de decisiones: `grilling` 10, `design-review` 13,
  y el Registro de cambios con las 3 decisiones de `scenario-coverage`), `CU-BE-12` completo, el task
  file.
- **Numeración verificada en esta sesión**: máximo FR actual en `spec.md` es **FR-048**
  (`grep -nE 'FR-04[5-9]|FR-05[0-9]'` → FR-048 es el último); FR-049/FR-054 solo aparecen como
  referencia *forward* en la cabecera de `CU-BE-12`. `ls .claude/specs/adr/` → el último es **0017**,
  no existe `0018`. Los 6 FR del `## Spec` de la tarea encajan exactamente en **FR-049…FR-054**.
- **Naturaleza de la tarea**: **doc-only**. No escribe código de negocio y **no tiene línea de mutation
  testing** (no añade código ejecutable que mutar) — se declara aquí en vez de omitirlo en silencio.
  Verificación: `/sdd-lint` + `pnpm gen:api:check` + `make test` sin regresión + revisión manual de los
  docstrings corregidos.
- **Plan de ejecución**: (1) leer specs objetivo (`spec.md` §KB, `rag-ingestion.md` §4/§6, ADR-0010 y
  0017 como plantilla MADR, `api-contract.md`/`.yaml` en los paths de KB, los 3 docstrings falsos);
  (2) escribir FR-049…FR-054 + enlace del CU en `spec.md`; (3) ADR-0018 + `adr-index.md`;
  (4) `rag-ingestion.md` §4/§6; (5) nota de alcance en `CU-BE-05`; (6) `api-contract.yaml` (422/502 +
  `maxLength` de `q`) y `pnpm gen:api` con los generados commiteados; (7) los 3 docstrings;
  (8) cierre: `make test` + ruff/mypy + `/sdd-lint` + `fact-checker`.

## 2026-08-25 — Ejecución

- **SDD escrito**:
  - `spec.md` — FR nuevos en la sección "KB: ingestión y retrieval" (su cabecera ahora enlaza también
    ADR-0018) + `CU-BE-12` añadido a la lista de "Casos de uso".
  - **ADR-0018** `0018-retrieval-http-de-la-kb-ventana-dedup-y-peso-de-estado.md` (MADR, mismo formato
    que 0017) con **todas** las decisiones del plan agrupadas por eje: recuperación sin política + clamp
    + filtro por `embedding.model`; ventana en documentos con over-fetch y qué significa `total`; peso de
    `estado` en `app/rag/` y `Hit.score` crudo vs `KBSearchHit.score` ponderado; dedup solo en el camino
    HTTP; política del `snippet`; 422/502; orden determinista y RN-8; glosarios y su sesgo (RN-9); índice
    ANN diferido con umbral de 50.000 filas **y su falta de alarma**; los dos puertos con su deuda;
    borrado del stub; guardia de contrato acotada a KB; y "lo que NO se hace" (caché de vectores,
    `rag_top_k`, `confidence.py`/`citations.py`). Añadido a `adr-index.md`.
  - `rag-ingestion.md` — **§4** gana la fórmula del peso y **dónde** se aplica (no en el `ORDER BY`);
    **§6** se parte en **§6.1 recuperación común** (score crudo acotado, filtro por modelo, chunk sin
    embedding, salida con `content`), **§6.2 camino del agente** (chunks, `score` crudo, con el aviso de
    que ponderarlo haría que la confianza híbrida contara `estado` dos veces) y **§6.3 camino HTTP**
    (ventana, dedup, `total`, score ponderado que puede superar `1.0`, snippet, orden determinista,
    422/502).
  - `CU-BE-05` — nota de alcance en la cabecera: qué escenarios cubre este plan (**2** y **4**) y cuáles
    son del agent-graph (**1**, **3**, **5**), más el reparto de actores frente a `CU-BE-12`.
- **Contrato** (`api-contract.yaml`):
  - `/kb/search` gana `'422'` → `ValidationError` y `'502'` → **`BadGateway`**, un `components/responses`
    **nuevo**: verificado que no existía ninguno reutilizable para 502 — el único 502 del fichero estaba
    **inline** en el endpoint de adjuntos. Ese inline **no se toca** (otro router, fuera de alcance);
    queda como follow-up unificarlo con el `$ref`.
  - `q` gana `minLength: 1` y **`maxLength: 512`** + descripción del 422. `scenario-coverage` decidió que
    hubiera tope pero no la cifra: **512 es decisión mía**, holgada para una caja de búsqueda del panel y
    muy por debajo del límite del proveedor. `minLength: 1` evita que el contrato permita `q=""` mientras
    la API responde 422.
  - **Decisión mía fuera de lo que literalmente pedía la tarea**: `'502'` también en **`/kb/documents`**.
    El plan solo lo pedía en `/kb/search`, pero la ext. **2e** del CU y el FR de fallos declaran el 502
    ahí (fallo de BD, sin embeddings de por medio). Sin declararlo, `-02`/`-07` introducirían un código
    no contratado — justo lo que **A6** marcó como bloqueante. Registrado como desviación consciente.
  - Descripciones nuevas en `KBSearchHit` (`score` = relevancia re-rankeada que puede superar `1.0`;
    `snippet` = principio de la sección, no extracto centrado en el término) y en los `summary` de los
    dos endpoints.
  - `pnpm gen:api` → **`frontend/src/types/api.ts` y `frontend/src/mocks/contract/openapi.json` SÍ se
    mueven** (confirma A7 del plan, que corregía una afirmación falsa de la versión anterior).
- **Docstrings corregidos** (los 3 de la tarea + 1 más):
  1. `app/domain/ports/vector.py` — prometía que la tarea 14 dejaría `VectorStore`/`StubVectorStore`
     "deprecados en favor de este puerto". **Verificado leyendo el `Protocol`**: `KBIndexWriter` no tiene
     `list_documents` ni `get_document`, así que es imposible. Sustituido por la decisión real (dos
     puertos + deuda + regla "un solo sitio por operación"), apuntando a ADR-0018.
  2. `app/infra/db/models/kb.py` — "Índice ANN diferido al plan RAG (13/14)" → umbral de ADR-0018
     (50.000 filas, `hnsw`) **con el aviso de que nadie vigila ese conteo**.
  3. `app/api/v1/routers/kb.py` — describía el stub como "comportamiento esperado, no un bug" y decía que
     la tarea 14 lo sustituiría "sin tocar este router" (falso: `-07` sí lo toca). Reescrito como estado
     transitorio, con lo que hará `-07` (swap + 422 + `snippet`).
  4. **Añadido por mí**: `app/ingestion/pipeline.py` — su "a revisar si el retriever necesita semántica
     real de `package` para glosarios" **ya está revisado** por RN-9 de CU-BE-12. Ahora dice que el
     defecto se corrige en la ingestión (migración + re-ingesta), no parcheando el retriever.
- **NO tocado a propósito** (sigue siendo cierto hoy, lo cambian `-04`/`-05`/`-07`): el
  `NotImplementedError` de `app/infra/vector/__init__.py:177`, el docstring de `Hit`, `StubVectorStore` y
  sus menciones, y los guiones de `app/rag/*`.

## 2026-08-25 — Gates y cierre

- **Sin gate de mutation**: tarea doc-only, no añade código ejecutable que mutar (declarado, no omitido).
- **`make test`** (desde `backend/`, con el Postgres de docker-compose levantado): **1064 passed** —
  igual que la línea base del plan, **sin regresión**. Ejecutado **dos veces**: tras el bloque SDD y tras
  los docstrings.
- **`ruff check` + `ruff format --check` + `mypy app`** (strict): limpios, 137 source files.
- **Frontend** (por la regeneración del contrato): `pnpm typecheck` limpio y `pnpm test` → **332 passed
  (70 ficheros)**. Sin regresión por el `gen:api`.
- **Guard grep** del nombre del cliente/proyecto sobre `backend/app`, `backend/tests`, `.claude/specs` y
  `frontend/src`: **0 resultados**.
- **Gate `/sdd-lint`** (`features.sdd: true`; `models.sdd-lint` ausente → inherit):
  - **Mecánico**: limpio — estados MADR canónicos, sin `[NECESITA ACLARACIÓN`, ids `FR-`/`SC-` bien
    formados y sin duplicados, secciones obligatorias presentes, **todos** los enlaces y wikilinks de
    `CU-BE-12` y `ADR-0018` resuelven, ningún CU huérfano, ADR-0018 en el índice.
  - **Semántico** (subagente fresco): **0 ERROR · 6 AVISO** → gate **pasa**. Trazabilidad completa
    (6/6 FR cubiertos por el CU) y coherencia confirmada punto por punto entre ADR-0018,
    `rag-ingestion.md` §4/§6 y el CU sobre `score`, `total`, ventana, dedup, snippet, peso y 422/502.
  - **AVISO corregidos en esta sesión** (5 de 6):
    1. *Ambigüedad real sobre qué `score` se devuelve*: ningún FR distinguía el crudo del ponderado, así
       que leyendo solo `spec.md` se infería un `score` acotado a `[0,1]` — lo contrario de RN-4.
       → **FR nuevo** que fija que el `score` de la API es la relevancia re-rankeada y puede superar `1.0`.
    2. *FR con dos requisitos en uno, el segundo sin patrón EARS* (la página fuera de ventana) →
       reformulado en forma canónica `Cuando …, el sistema DEBERÁ …`.
    3. *FR que empaquetaba tres comportamientos con disparadores distintos* (listar + abrir + 404) →
       **partido en dos FR**. Por eso el rango pasa de FR-049…FR-054 a **FR-049…FR-056**; `CU-BE-12` y
       `ADR-0018` actualizados al rango nuevo.
    4. *`Then` no observable* en el escenario del modelo de embeddings ("solo se consideran los vectores
       del modelo configurado", que reformula el mecanismo) → ahora asserta el resultado observable.
    5. *Dos comportamientos en un escenario* (los glosarios se listan **y** se abren) → **partido en dos
       escenarios**; el título citado por `-02` se conserva y el nuevo se añadió a su lista.
    - Menores del mismo lote: imprecisión de *"un active solo adelanta a un draft de relevancia
      equivalente"* (con `w=0.05` adelanta hasta a un draft 5% más relevante) → redacción fiel; fuga de
      implementación en el escenario principal Cockburn (nombraba `RAG_SEARCH_WINDOW` y el over-fetch) →
      delegada al ADR; y "rango" vs "ventana" unificados en los `Examples`.
  - **AVISO reconocido y NO corregido (1)**: fundir en un `Scenario Outline` los dos escenarios de 404
    (`uc_id` inexistente / `uc_id` con forma inesperada). **Motivo**: las tareas `-02`…`-07` citan los
    escenarios **por título**, así que renombrarlos rompería esas referencias; el propio validador lo
    clasifica como "AVISO leve".
  - **Punto de atención atendido**: RN-7 no tiene escenario propio ni escenario negativo de autorización.
    Era el **descarte explícito** de `scenario-coverage` (403 ya cubierto por CU-BE-03,
    `require_capability` reutilizado sin cambios) → ahora está **escrito en la propia RN-7**, no solo en
    el Registro de cambios del plan.
- **Gate `fact-checker`** (subagente fresco, `model: sonnet` por `models.fact-checker`): **20/20
  VERIFICADO**, 0 INCORRECTO, 0 NO VERIFICABLE. Verificó por su cuenta la línea base (FR-048 y ADR-0017
  como máximos en `main`), las tres suites, ruff/mypy, el guard grep, que `KBIndexWriter` **no** tiene
  `list_documents`/`get_document` mientras `VectorStore` **sí** (lo que hace imposible la promesa del
  docstring viejo), que el `NotImplementedError` sigue en pie, y que `git diff main -- backend/` **cae
  íntegramente dentro de docstrings de módulo**: ninguna sentencia ejecutable cambia. Reprodujo además
  el diff de `gen:api` (51 líneas) corriendo el generador él mismo — confirma que los generados salen
  del contrato y no de una edición a mano.
  - **Único matiz suyo**, aceptado: mi enunciado decía `tasks/pending/backend/backend-kb-retriever-0*`
    para las tareas que citan escenarios por título, y `-01` ya está en `active/`. El glob solo alcanzaba
    `-02`…`-07`, que es justo el conjunto relevante: no cambia ningún veredicto.
- **Corrección de una afirmación de la entrada de arranque**: allí escribí que los FR nuevos encajaban en
  **FR-049…FR-054**. Tras el AVISO de `/sdd-lint` sobre granularidad EARS son **8**: **FR-049…FR-056**.
  La entrada de arranque queda como estaba (log append-only); esta línea es la corrección.
- **Docs — tres capas**: (1) **docstrings**: los 4 módulos de arriba; (2) **doc técnica**: `spec.md`,
  `rag-ingestion.md` §4/§6, `adr-index.md` + ADR-0018, `CU-BE-05`, `CU-BE-12`, `api-contract.yaml`;
  (3) **histórico**: este log. Sin superficie de usuario final que documentar (la tarea no cambia
  comportamiento observable: el swap es de `-07`).
- **Ficheros**:
  - Nuevos: `.claude/specs/adr/0018-retrieval-http-de-la-kb-ventana-dedup-y-peso-de-estado.md`,
    `.claude/specs/backend/casos-de-uso/CU-BE-12-consulta-de-la-kb-desde-el-panel.md` (materializado por
    `/plan-task`, revisado y ajustado aquí), este session log.
  - Modificados: `.claude/specs/backend/spec.md`, `.claude/specs/backend/rag-ingestion.md`,
    `.claude/specs/backend/casos-de-uso/CU-BE-05-clasificacion-y-retrieval-rag.md`,
    `.claude/specs/adr/adr-index.md`, `.claude/specs/general/api-contract.yaml`,
    `frontend/src/types/api.ts` (generado), `frontend/src/mocks/contract/openapi.json` (generado),
    `backend/app/domain/ports/vector.py`, `backend/app/infra/db/models/kb.py`,
    `backend/app/api/v1/routers/kb.py`, `backend/app/ingestion/pipeline.py` (los 4 solo docstrings),
    `.claude/tasks/pending/backend/backend-kb-retriever-02.md` (un escenario más en su lista).
  - Movidos: plan y tarea a `active/` (y la tarea a `completed/` al cerrar).
- **Tiempo real**: ~3h (estimado 3h).
- **Follow-ups**:
  1. **Unificar el 502 inline de adjuntos** (`api-contract.yaml`, `/messages/{id}/attachments`) con el
     `components/responses/BadGateway` nuevo. Fuera de alcance aquí: es otro router.
  2. **`-07` debe implementar el `maxLength: 512` de `q`** además de la validación de vacía/espacios —
     el contrato ya lo declara.
  3. **`-02` implementa el 502 de `/kb/documents`** ante fallo de BD: ya está en el contrato y en el CU.
  4. Sigue sin corregir el aviso conocido de `models.design-review: claude-opus-4-8` en
     `.claude/task-pipeline.yml` (id de modelo inválido → la fase cae a `inherit`); lo arregla el owner.
  5. El umbral del índice ANN (50.000 filas en `kb_chunk`) **no tiene alarma**: escrito en ADR-0018 y en
     el docstring de `models/kb.py`, pero nadie lo vigila.
