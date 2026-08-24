# Session log — `backend-kb-source-packages-uc-03` — Registro de tipos de fuente + wiring + docs

> Append-only. Registro canónico de la tarea (task-lifecycle §Cerrar una tarea).

## 2026-08-24 — Arranque

- **Gate TDD comprobado**: rama `plan/backend/kb-source-packages-uc`; `depends_on:
  [backend-kb-source-packages-uc-02]` → **done** (commit `fc8ca73`); única tarea `active` del plan.
- **Leído en esta sesión**: el task file entero, `app/core/config.py` (campos `kb_*`, patrón de
  validación perezosa de `llm_provider`/`kb_source_path`), `app/ingestion/pipeline.py` completo,
  `app/ingestion/cli.py` completo, `app/domain/errors.py` (`DomainError(message, *, code, details)`) y la
  estructura de `tests/test_pipeline.py`.
- **Corrección de un dato del plan (verificado, no asumido)**: el plan y el task file dicen que "~21
  tests de `test_pipeline.py` llaman `ingest()` sin `source_type`" y que hay que añadírselo a cada uno.
  **La realidad es otra**: el fichero tiene **25 tests** que llaman a un **helper propio `_ingest(...)`**
  (26 usos) y solo **7 llamadas directas** a `ingest(` fuera de él (líneas 414-558, las que necesitan
  parámetros que el helper no expone). Añadir el `source_type` explícito son, por tanto, **8 puntos de
  edición**, no 21. Ninguna aserción cambia. Lo registro aquí porque el plan afirmaba lo contrario.
- **Plan de ejecución**: tests rojos → `Settings` + `sources.py` + wiring en `pipeline`/CLI → tests de
  integración end-to-end → docs (rag-ingestion, data-model, CU-BE-07, spec.md, ADR nuevo) → cierre.

## 2026-08-24 — Implementación y cierre

- **TDD**: `tests/test_sources.py` (10) + bloque nuevo en `tests/test_cli.py` (16) +
  `tests/test_pipeline_packages_uc.py` (10, integración real contra Postgres) escritos ANTES; rojo
  confirmado (`ModuleNotFoundError: No module named 'app.ingestion.sources'`), verde después.
- **Implementado**:
  - `app/ingestion/sources.py` (nuevo): `SourceType` (`@dataclass(frozen=True)` con
    `load`/`parse`/`requires_package_aliases`) + `resolve_source()`. Solo la forma canónica exacta se
    reconoce; un tipo no registrado levanta `Validation` con el valor recibido y la lista de válidos.
  - `Settings.kb_source_type: str = "packages-uc"` y `Settings.kb_package_aliases: str = ""` — los dos
    `str` a propósito (validación perezosa), con el porqué en su docstring.
  - `pipeline.ingest()` gana `source_type`/`package_aliases` y resuelve el par por el registro; el
    `parse` se especializa con `functools.partial` **solo** si el tipo lo declara. `pipeline.py` sigue
    sin importar `app.core.config`.
  - `cli.py`: `--source-type` (argumento > settings), parseo del JSON de alias, código **2** para
    ambos errores de uso y aviso por stderr de alias vacíos.
- **Decisiones de implementación**:
  1. **`package_aliases: dict[str, str] | None = None`**, no `= {}` como decía el task file: un default
     mutable lo prohíbe ruff (B006) con razón. `None` ≡ sin alias.
  2. **`ParseFn = Callable[..., ParsedUC | ParseError]`**, con la elipsis **documentada** como
     deliberada: las dos `parse` tienen firmas distintas a propósito, y quien las consume las llama
     siempre con la firma reducida tras el `partial`. No es un `Any` de conveniencia.
  3. **Los dos errores de uso se resuelven ANTES de `_run()`**: el `Validation` de `resolve_source` es
     un `DomainError`, que la CLI mapea a `1` — si escapara desde dentro saldría con el código
     equivocado. Además así un typo no llega a abrir engine ni sesión.
  4. **La validación del JSON de alias solo comprueba los valores**: las claves de un objeto JSON son
     siempre cadenas, así que comprobarlas era una rama muerta (y un superviviente de mutación).
- **Corrección de un dato del plan** (ya anotada en el arranque): la adaptación de los tests existentes
  fueron **8 puntos de edición** en `test_pipeline.py` (un helper `_ingest` + 7 llamadas directas), no
  "~21 tests". **Más uno que el plan no había visto**: el test end-to-end de `test_cli.py`, que también
  dependía del default y ahora pasa `--source-type vitepress-domains`. Ninguna aserción cambió.
- **Tests**: suite completa **1064 passed** (1023 → 1058 con los 35 nuevos, +1 tras el gate `sdd-lint`,
  +5 tras endurecer la validación de alias). Sin regresión.
- **ruff + `mypy app` (strict)**: limpios.
- **Mutation testing (cosmic-ray)**, **tres pasadas** (una por fichero tocado, re-apuntando
  `module-path`/`test-command` entre ellas):
  - `sources.py` → **0.00% (0/17)**.
  - `cli.py` → 7.89% (6/76) en la primera pasada. **Un superviviente real y mío**:
    `isinstance(key, str) and isinstance(value, str)` → `or` sobrevivía porque ningún test daba un
    objeto JSON con un **valor** no textual. Se simplificó la comprobación (las claves JSON son siempre
    cadenas) y se añadió un `Scenario Outline` de formas equivocadas → **6.67% (5/75)**. Los 5
    restantes: `expire_on_commit` y 2× el `else 2` del `SystemExit` de argparse (preexistentes; el
    segundo, además, inalcanzable — argparse siempre fija un int), y 2× el marcador `*` de
    keyword-only, de los cuales **uno es código nuevo de esta tarea** (la firma de `_run()`, que se
    reescribió para recibir `source_type`/`package_aliases`). Sigue siendo un artefacto de la
    herramienta sobre sintaxis que no es un operador —todas las llamadas usan keywords—, pero **no** es
    preexistente: lo corrigió el `fact-checker` sobre una afirmación mía demasiado tajante.
  - `pipeline.py` → **3.25% (5/154)**. Los 5 son preexistentes y equivalentes: 2× el marcador `*`;
    `len(docs) > 1`→`!= 1` y `docs[0]`→`docs[-1]` (tras descartar duplicados cada lista tiene
    exactamente un elemento); y un default `dry_run` que siempre se pasa explícito.
- **Gate `/sdd-lint`**: mecánico limpio. Semántico (subagente fresco) sobre los 6 artefactos SDD que
  toca la tarea: **2 ERROR**, ambos **míos y reales**, verificados por mí antes de corregir:
  1. La extensión **1l** y su escenario decían que sin alias "no se procesa ningún documento". **Falso**:
     los glosarios no dependen de los alias y **sí se ingieren** — mi propio test lo aseveraba (y su
     nombre, `..._nothing_is_ingested`, era engañoso; renombrado). Peor aún, el subagente encadenó la
     consecuencia que yo no había visto: como el run **no** queda vacío, la salvaguarda de 4b/RN-6 no se
     activa y **los UC ya persistidos se reconcilian (se borran)**. Corregido en 1l, en el escenario, en
     `rag-ingestion.md` §7, y **fijado con un test nuevo** (`report.deleted == 3`).
  2. **FR-046** afirmaba "no reconciliar nada" sin el calificador de `force_reconcile`/`--reconcile`,
     que el código implementa y ya tenía test. Corregido.
  - **AVISO corregidos también** (todos verificados contra el código): FR-048 pasa de un guardián
    state-driven no observable a ubicuo; 4b decía "no toca la base de datos" cuando sí toma el advisory
    lock (ahora "no escribe nada"); el paso 2 del escenario principal decía "glosario del `index.md`"
    en el camino común; la contranota de ADR-0010 exceptúa ahora la cláusula del glosario, que **sí**
    era específica del formato hipotético, y su Confirmación acota qué parte de `rag-ingestion.md`
    sigue valiendo; `data-model.md` §4.3 documenta los **placeholders** de `package`/`estado` de los
    glosarios; ADR-0017 gana los pros/contras de la opción elegida; y CU-BE-07 gana escenarios para el
    default, la precedencia argumento>config y la forma del JSON de alias (extensión **1n**).
  - **AVISO reconocidos sin cambio**: FR-032 sigue empaquetando cuatro comportamientos (forma
    preexistente, fiel al código); y el subagente marcó como **no verificables en este repo** los
    conteos de la fuente real (268 UC, 17 dominios, 16 glosarios) — correcto: la fuente no vive aquí.
- **Docs (3 capas)**: docstrings de todo lo nuevo (incl. el porqué de la elipsis de `ParseFn` y de
  validar los alias fuera de `Settings`); doc técnica → `rag-ingestion.md` §1/§2 reescritas con los dos
  tipos por separado, `data-model.md` §4.3, `CU-BE-07`, `spec.md` (FR-032 + FR-042…FR-048), **ADR-0017**
  nuevo + índice, contranota en ADR-0010; dev → `.env.example` con `KB_SOURCE_TYPE`/`KB_PACKAGE_ALIASES`
  y la advertencia del borrado al cambiar de tipo; histórico → este log.
- **Ficheros**: `app/ingestion/sources.py` (nuevo), `app/ingestion/{pipeline,cli,__init__}.py` (M),
  `app/core/config.py` (M), `.env.example` (M), `cosmic-ray.toml` (M), `tests/test_sources.py` y
  `tests/test_pipeline_packages_uc.py` (nuevos), `tests/{test_cli,test_pipeline}.py` (M),
  `.claude/specs/backend/{spec,rag-ingestion,data-model}.md` (M),
  `.claude/specs/backend/casos-de-uso/CU-BE-07-...md` (M), `.claude/specs/adr/0017-...md` (nuevo),
  `.claude/specs/adr/{0010-...,adr-index}.md` (M).
- **Gate `fact-checker`** (subagente fresco, `model: sonnet`): **16 VERIFICADO / 2 INCORRECTO / 0 NO
  VERIFICABLE**. Los dos INCORRECTO son **afirmaciones mías**, no defectos del código, y quedan
  corregidas:
  1. Afirmé que esta tarea modificó `packages_uc.py`. **Falso**: ese fichero es de la `-02` y ya está
     commiteado (`fc8ca73`); la `-03` no lo toca. Lo tocado aquí es `sources.py` (nuevo), `pipeline.py`,
     `cli.py`, `config.py`, `__init__.py`, `.env.example`, `cosmic-ray.toml` y los tests.
  2. Afirmé que **ninguno** de los supervivientes de mutación estaba en código nuevo. **Falso**: el
     marcador `*` de la firma de `_run()` sí lo es (ver arriba, ya corregido en la entrada del gate de
     mutation). Benigno, pero mi afirmación era demasiado tajante.
  Re-ejecutó él mismo la suite (1064 passed), ruff/mypy y **las tres pasadas de cosmic-ray en serie**,
  con los mismos números (0.00% / 6.67% / 3.25%). Se le avisó de no solapar pytest con `cosmic-ray exec`.
- **Tiempo real**: ~4h (estimado 4.5h).
- **Follow-ups**: (a) **verificación manual del owner** — `make ingest` real contra la fuente, con
  `KB_PACKAGE_ALIASES` configurado (fuera del gate: cuesta embeddings reales); (b) el guardarraíl por
  volumen de borrado (umbral + flag) sigue descartado y anotado en ADR-0017 como candidato si el caso se
  da en real; (c) `models.design-review` en `.claude/task-pipeline.yml` sigue con un id de modelo
  inválido (`claude-opus-4-8`).
