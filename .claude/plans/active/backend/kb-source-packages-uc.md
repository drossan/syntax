---
id: backend-kb-source-packages-uc
package: backend
status: active
branch: plan/backend/kb-source-packages-uc
created: 2026-08-22
updated: 2026-08-24
---

# Ingestión de la KB — nuevo `source_type` genérico para fuentes "UC por package"

> **REANUDADO (2026-08-24)** — estuvo aparcado unas horas mientras se evaluaba adoptar **Use-Case 3.0**
> (Jacobson/Spence/de Mendonca, mayo 2024) como estándar del documento fuente de la KB. Evaluación
> cerrada: **no se adopta** (ver Registro de cambios). El plan sigue tal cual, con todas las decisiones
> de `grilling` + `design-review` ya consolidadas abajo.

## Contexto y problema

El plan `kb-ingestion` (cerrado 2026-08-22, 946 tests) implementó loader/parser/chunker/embedder/CLI
completos, pero contra un formato **hipotético, nunca verificado**: `<dominio>/uc/UC-*.md` +
frontmatter `title`/`domain`/`package`/`uc` + bloque `::: info Trazabilidad`. La fuente real
(`~/Documents/Desarrollo/syntax/docs-site/domains/`) no existía en esa máquina.

Verifiqué el formato real leyendo un repo de documentación real disponible localmente (proceso de
este plan; el propio backend no referencia ese repo por nombre — ver nota de scope más abajo). Tres
hallazgos verificados cambian el diagnóstico:

1. **El layout real no es `<dominio>/uc/*.md`**: los 268 UC (mismo conteo que documenta
   `rag-ingestion.md`) viven repartidos por subdirectorio de package
   (`packages/<pkg>/docs/aiup/use-cases/UC-*.md`, 5 packages en la fuente verificada), y los
   glosarios en una ubicación compartida, un fichero plano por dominio
   (`docs/aiup/glossaries/<dominio>.md`; 16 de 17 dominios — 1 dominio no tiene glosario propio y cae
   a un fallback compartido que este plan decide NO ingerir).
2. **El frontmatter real es distinto**: solo `id`/`dominio`/`estado`/`traza` (`traza` ya como lista
   YAML, salvo el caso defensivo de venir como string único). No hay `title` (el título es el primer
   H1 del cuerpo), no hay `package` en el frontmatter (se deriva de en qué subdirectorio de package
   vive el fichero), y no hay bloque `::: info Trazabilidad`.
3. **Existe un generador** (build de un site de docs) que transforma esos crudos en algo parecido al
   formato que el parser actual espera — pero, verificado contra su código, ni así funcionaría: emite
   el callout de trazabilidad con la negrita en otra posición, valores entre backticks, y sobre todo
   el `package` con el nombre de marca real del cliente (no el valor `syntax-*` del enum). Depender de
   ese build añade una dependencia externa (otro runtime, otro repo) para un problema que se resuelve
   leyendo los `.md` crudos directamente.

**Decisión de scope (grilling, este plan): el backend no lleva ninguna referencia al nombre del
cliente/proyecto cuya documentación verifiqué.** Ni en nombres de módulo, ni en el valor del
`source_type`, ni en fixtures, ni en `rag-ingestion.md`/`CU-BE-07`/ADR — todo se describe de forma
genérica y reutilizable para cualquier proyecto con este layout ("UC repartidos por subdirectorio de
package + glosarios planos por dominio"). Sí se permite citar la fuente real de verificación en este
plan y su Registro de cambios (trazabilidad de proceso, no algo que el producto "lleve puesto"): la
verifiqué contra `~/Documents/Desarrollo/www/SECUOYAS/griddo-chore-docs` (solo lectura, repo ajeno a
`syntax`).

Decisión ya tomada con el owner antes de este documento: en vez de un mapeo YAML declarativo genérico
pensado para tenants futuros hipotéticos, `Settings` indica un `kb_source_type` y cada tipo de fuente
tiene su propio módulo de loader+parser **en código**.

## Objetivos

1. **`Settings`/CLI seleccionan el tipo de fuente por código, no por mapeo declarativo.**
   - *Criterio de éxito*: `Settings.kb_source_type: str = "packages-uc"` (validación perezosa en
     `resolve_source()`/CLI, **no** `Literal` — un `Literal` estricto tumbaría el arranque de toda la
     app por un typo en una env var que solo usa la ingestión, algo que `config.py` ya evita a
     propósito para `llm_provider`/`kb_source_path`); un valor no reconocido (p. ej. vía
     `--source-type` de la CLI, con la misma precedencia que `path`: argumento > settings) falla claro
     con código de salida `2`, nunca con una traza cruda. **El default es el formato real verificado**
     (`packages-uc`), no el hipotético — decisión de `design-review` #2, ver Registro de cambios.
2. **Un UC real (formato "packages-uc") se ingiere correctamente.**
   - *Criterio de éxito*: test de integración con una fixture fiel al formato verificado (frontmatter
     `id`/`dominio`/`estado`/`traza`, sin `title`/`package`, bajo un directorio de package genérico de
     fixture) produce un `KBDocumentDraft` con `title` = el H1, `package` traducido vía
     `Settings.kb_package_aliases` (dict configurado en el test), `traza` = la lista YAML tal cual (o
     envuelta en lista si llega como string único).
3. **Un directorio de package sin alias configurado, un alias que apunta a un `Package` inválido, o un
   UC sin H1, se saltan como malformados** — igual criterio que cualquier otro documento mal formado
   (skip + log, nunca aborta el batch). Sin ningún alias configurado (`kb_package_aliases` vacío, el
   default), esta fuente no ingiere nada — comportamiento esperado, no un bug: fuerza a configurar
   explícitamente el vocabulario del deployment real antes de ingerir, y **se avisa por stderr** para
   que no se confunda con "no había nada que ingerir" (`design-review` #3).
   - *Criterio de éxito*: tests 1:1 con los escenarios Gherkin nuevos de `CU-BE-07` para este tipo,
     incluido el del **valor** de alias fuera del enum `Package` (`design-review` #6: hoy
     `pipeline._to_draft()` haría `Package(...)` sin protección → `ValueError` → `except Exception`
     genérico de la CLI, rompiendo la paridad que promete este objetivo).
4. **Los glosarios de este tipo de fuente (fichero plano por dominio, sin `## Glosario` ni
   frontmatter) se ingieren íntegros.**
   - *Criterio de éxito*: test — el cuerpo completo del fichero se persiste bajo el `uc_id` sintético
     `__glosario__:<dominio>` ya existente (reutilizado sin cambios de `app.ingestion.parser`).
5. **Un árbol hermano legacy (una convención de carpeta distinta a la reconocida por este tipo) nunca
   se recoge**, verificado con un test explícito — no solo "por construcción" del glob.
   - *Criterio de éxito*: fixture con ambos árboles (el reconocido + un hermano con nombre de carpeta
     distinto, simulando una convención legacy real); el resultado nunca incluye contenido del
     hermano.

## Alcance y fuera de alcance

### Dentro del alcance

- `app/core/config.py`:
  - `Settings.kb_source_type: str = "packages-uc"` (validación perezosa, no `Literal`).
  - `Settings.kb_package_aliases: str = ""` — el **JSON crudo** (`KB_PACKAGE_ALIASES='{"vendor-render":
    "syntax-render"}'`), **no** un `dict` tipado. Decisión de `scenario-coverage` (hallazgo -03/errores):
    un `dict[str, str]` lo valida pydantic-settings de forma **eager** al construir `Settings()`, así que
    un JSON malformado tumbaría el arranque de **toda** la app (auth, tickets…), no solo la ingestión —
    exactamente el riesgo que ya evitamos a propósito declarando `kb_source_type` como `str`. Se parsea y
    valida **donde se usa** (extensión 1m del CU): JSON inválido → error de uso, código `2`, acotado a
    `make ingest`. Vacío por defecto.
- `app/ingestion/sources.py` (nuevo, pequeño): registro `resolve_source(source_type: str) -> SourceType`,
  donde `SourceType` es un `@dataclass(frozen=True)` con `load`, `parse` y
  **`requires_package_aliases: bool`** — no una tupla desnuda. Decisión de `scenario-coverage` (hallazgo
  -03/spec implícita): la CLI necesita saber si el tipo seleccionado usa alias para decidir si emite el
  aviso de la extensión 1l, y sin ese metadato la única salida era un `if source_type == "packages-uc"`
  hardcodeado en la CLI, o un **falso positivo** avisando de "alias vacíos" con `vitepress-domains` (que
  no los usa y cuyo default de alias es vacío). El conocimiento vive junto al tipo; un tercer tipo futuro
  trae el suyo sin tocar la CLI. (Ajusta la firma que había fijado `design-review` #1 — la inyección de
  los alias sigue siendo por `ingest()` + `functools.partial`, sin cambios.)
  - `"packages-uc"` → `packages_uc.load`/`packages_uc.parse`, `requires_package_aliases=True`;
    `"vitepress-domains"` → `loader.load`/`parser.parse` (**sin tocarlos**),
    `requires_package_aliases=False`.
  - `source_type` no registrado levanta `app.domain.errors.Validation` (mismo tipo de error que ya usa
    `pipeline.ingest` para `uc_id` duplicado), con el valor recibido y la lista de válidos. **Solo la
    forma canónica exacta se reconoce**: una variante de caja (`"Packages-UC"`) es un valor no
    registrado, no un alias tolerado.
- `app/ingestion/packages_uc.py` (nuevo — nombre genérico, describe la forma del layout, no ningún
  cliente): `load(root: Path) -> Iterator[RawDoc]` + `parse(raw: RawDoc, *, kb_root: Path,
  package_aliases: dict[str, str]) -> ParsedUC | ParseError`, reutilizando **sin modificar** los
  dataclasses `RawDoc`/`ParsedUC`/`ParseError` y la constante `GLOSARIO_UC_ID_PREFIX` de
  `loader.py`/`parser.py` — son el contrato ya source-agnostic que consume `pipeline.py`.
  - Loader: descubre `root/packages/*/docs/aiup/use-cases/UC-*.md` (glob) +
    `root/docs/aiup/glossaries/*.md`; ordenado igual que el loader actual; fichero illegible → skip+log
    (mismo criterio, función propia — no importa la privada `_read` de `loader.py` entre módulos
    independientes). El nombre de carpeta `aiup`/`packages`/`glossaries`/`use-cases` es la convención
    fija de ESTE tipo de fuente (igual que `vitepress-domains` fija `<dominio>/uc/UC-*.md`) — no es
    marca de ningún cliente, es la forma estructural que este `source_type` reconoce.
  - Parser (UC): `yaml.safe_load` del frontmatter (`id`→`uc_id`, `dominio`→`domain`, `estado`, `traza`
    como lista, o string único envuelto en lista de un elemento); `title` = primer H1 del cuerpo
    (regex `^#\s+(.+?)\s*$`); sin H1 → skip+log. `package` se deriva del segmento
    `packages/<pkg>/` de la ruta, traducido por `package_aliases` (inyectado); un `<pkg>` sin entrada
    en `package_aliases`, **o con una entrada cuyo valor no es un miembro válido de `Package`** →
    skip+log (mismo criterio que domain/estado fuera de catálogo). El `body` se persiste **sin**
    limpiar las etiquetas `**ACn**` (jerga de spec del origen; no se replica ninguna transformación
    cosmética). Sin `::: info Trazabilidad`: no hay concepto de discrepancia `package` que loguear para
    este tipo (el `package` solo tiene una fuente, la ruta). **`relacionado` se deja vacío** — ver
    Fuera de alcance.
  - Parser (glosario): `domain` = nombre de fichero sin extensión (validado contra `KbDomain`); `body`
    = contenido íntegro (sin extraer ningún `## Glosario`, a diferencia de `vitepress-domains`); mismo
    `uc_id` sintético que ya existe.
  - `_VALID_DOMAINS`/`_VALID_ESTADOS` se derivan de forma independiente en este módulo (no se importan
    los privados de `parser.py`): los dos tipos de fuente son implementaciones independientes que
    comparten solo el contrato de datos, no detalles internos.
- `app/ingestion/pipeline.py`: `ingest()` gana `source_type: str = "packages-uc"` y
  `package_aliases: dict[str, str] = {}`; dentro, `load_fn, parse_fn = resolve_source(source_type)` y
  el `parse_fn` se especializa con `functools.partial(parse_fn, package_aliases=...)` **solo** para los
  source types que lo declaran (decisión de `design-review` #1, alternativa (b) elegida por el owner:
  mantiene `resolve_source` con firma limpia y deja la inyección donde `ingest()` ya inyecta
  `token_budget`/`encoding`/`batch_size`, coherente con que `pipeline.py` no importe
  `app.core.config`).
- `app/ingestion/cli.py`: lee `settings.kb_source_type`/`settings.kb_package_aliases`, admite
  `--source-type` (mismo patrón de precedencia que `path`: argumento > settings), **parsea el JSON de
  alias** (inválido → código `2`, extensión 1m) y lo pasa a `ingest(...)`; **avisa por stderr** si
  `SourceType.requires_package_aliases` y los alias están vacíos (`design-review` #3 + extensión 1l), y
  **no** avisa si el tipo no los usa.
- **Transición entre formatos documentada y fijada por test** (extensión 4c, decisión de
  `scenario-coverage`): cambiar el `source_type` sobre la misma BD reconcilia —borra— los documentos del
  formato anterior que no reaparecen, porque la reconciliación compara `uc_id` origen-vs-BD sin distinguir
  la procedencia (verificado en `pipeline.ingest`: `existing_uc_ids() - origin_uc_ids`). Es el
  comportamiento **esperado**, pero la inversión del default (`design-review` #2) permite dispararlo sin
  quererlo → escenario en el CU + test de integración + advertencia al operador en `rag-ingestion.md` y en
  el ADR nuevo. El **espacio de nombres de `uc_id` es compartido** entre tipos de fuente: se declara
  explícitamente en la spec en vez de dejarlo implícito.
- Fixtures nuevas en `backend/tests/fixtures/kb_packages_uc/` (raíz separada de
  `tests/fixtures/kb/domains/`, que sigue siendo la de `vitepress-domains` sin tocar): un layout
  `packages/<pkg>/docs/aiup/use-cases/UC-*.md` + `docs/aiup/glossaries/*.md` mínimo, con nombres de
  package de fixture genéricos (no el nombre real del cliente verificado), fiel a la ESTRUCTURA real
  verificada. Incluye una fixture con un árbol hermano de nombre distinto para el Objetivo 5.
- **Adaptación de los tests existentes de `test_pipeline.py`** que hoy dependen implícitamente del
  default `vitepress-domains`: pasan `source_type="vitepress-domains"` explícito. Consecuencia
  aceptada de invertir el default (`design-review` #2) — son ~21 tests que hoy llaman `ingest()` sin
  ese parámetro; **el plan NO puede afirmar "los 946 tests siguen en verde sin modificarlos"**, sí
  "siguen en verde tras añadirles el parámetro explícito, sin cambiar ninguna aserción".
- Extiende `CU-BE-07` con los escenarios de este tipo de fuente (parseo UC real, glosario íntegro,
  alias de package vía config, `<pkg>` sin alias, alias con valor fuera del enum, UC sin H1,
  `source_type` desconocido en la CLI, árbol hermano no reconocido nunca se recoge, aviso de alias
  vacío).
- Corrige `rag-ingestion.md` §1/§2: documenta **ambos** tipos de fuente por separado —
  `vitepress-domains` (hipótesis original, no verificada, tal cual queda) y `packages-uc` (formato
  real verificado, descrito de forma genérica: layout, frontmatter, y las 3 discrepancias del
  generador de site que se descartó como intermediario). Corrige la ruta de fuente primaria (la de
  `docs-site/domains/` no existe; no se genera como parte de este plan). Sin mencionar el nombre del
  cliente/proyecto de verificación.
- Corrige `data-model.md` §4.3 (`design-review` #4): la precedencia `package` frontmatter-vs-Trazabilidad
  está documentada como regla universal de `kb_document.package`, pero es **específica de
  `vitepress-domains`** — en `packages-uc` no existe bloque Trazabilidad. Nota de una frase.
- ADR nuevo y corto (número siguiente libre en `adr-index.md`, a resolver al implementar): registro de
  tipos de fuente en código + alias de package como configuración de deployment — mapeo declarativo
  genérico descartado por falta de un segundo caso real; sin nombres de cliente. **Registra también
  como deuda explícita** (`design-review` #7) que `vitepress-domains` se mantiene como opción de
  primera clase sin corresponder a ninguna fuente real confirmada, y cuál es el criterio para
  borrarlo.

### Fuera de alcance

- **Parsear los wiki-links `[[UC-XXX-NNN]]` a `relacionado`** — recortado del plan por
  `design-review` #5 (decisión del owner): `relacionado` **no se persiste ni se consume en ningún
  sitio** (`KBDocumentDraft` no tiene el campo; `ParsedUC.relacionado` no se lee fuera de
  `parser.py`), así que parsearlo ahora es trabajo sin consumidor — la misma especulación que este
  plan rechaza en otros puntos. Se añade cuando el retriever (tarea 14) lo necesite de verdad, con el
  contexto de uso real delante.
- **Ejecutar `make ingest` de verdad contra una fuente real**: sigue fuera del gate de cualquier
  tarea (coste real de embeddings, requiere `OPENAI_API_KEY`) — verificación manual del owner tras
  cerrar el plan, igual criterio que el plan `kb-ingestion`.
- **Tocar el repo de documentación externo verificado**: no se ejecuta ningún build suyo ni se
  modifica su código — la ingestión lee los `.md` crudos directamente, sin depender de ese build.
- **Ingerir contenido narrativo multi-package** (flows/capacidades que cruzan varios packages): no es
  un UC ni un glosario — no encaja en el modelo `KBDocumentDraft` actual. Extensión futura si hace
  falta, no de este plan.
- **Fallback al glosario compartido** cuando un dominio no tiene glosario propio: decisión explícita
  de no ingerirlo (evita atribuir contenido compartido a un solo dominio).
- **Mapeo declarativo genérico por-tenant** (la opción descartada en la conversación previa): sin un
  segundo tipo de fuente real confirmado, sería diseño especulativo. La configurabilidad de
  `kb_package_aliases` es un dict de traducción de nombres, no un mapeo de campos/estructura.
- **Migración de esquema**: no hace falta ninguna — `Package`/`KbDomain`/`KbEstado` ya cubren, tras el
  alias, todos los valores reales verificados.
- **Retriever real (`search`), `OpenAIChatModel`**: igual que en `kb-ingestion`, siguen fuera.
- **Modificar `vitepress-domains`** (`loader.py`/`parser.py` actuales): quedan tal cual, referenciados
  sin cambios desde el registro nuevo (sus tests sí reciben el `source_type` explícito, ver Alcance).
- **Adoptar Use-Case 3.0 como estándar de la capa SDD del repo**: evaluación aparte, en curso
  (2026-08-24) — este plan está aparcado hasta que cierre, pero es independiente de ella.

## Recursos externos

- `~/Documents/Desarrollo/www/SECUOYAS/griddo-chore-docs` (repo real, fuera de `syntax` — solo
  lectura, citado aquí como trazabilidad de proceso, sin réplica de su nombre en código/specs del
  producto): `packages/*/docs/aiup/use-cases/UC-*.md` (268 ficheros, verificado); `docs/aiup/glossaries/`
  (16 ficheros); `docs-site/scripts/lib/{transform,emit,collect,domains}.mjs` (generador de site,
  confirma por qué no sirve como intermediario).
- `backend/app/ingestion/{loader,parser,pipeline,cli}.py` + `app/domain/ports/vector.py` +
  `app/domain/entities/enums.py` + `app/core/config.py` — código real ya cerrado, leído para este plan.
- `backend/tests/test_pipeline.py` — 21 tests que llaman `ingest()` con ficheros reales en `tmp_path`;
  ninguno monkeypatchea `load`/`parse` (verificado por mí y por el subagente de `design-review`), pero
  todos dependen del default de `source_type` → reciben el parámetro explícito (ver Alcance).
- `.claude/specs/backend/rag-ingestion.md`, `.claude/specs/backend/casos-de-uso/CU-BE-07-ingestion-de-la-kb.md`,
  `.claude/specs/backend/data-model.md` §4.3, `.claude/specs/adr/0010-...md`, `adr-index.md`.
- `.claude/plans/completed/backend/kb-ingestion.md` — plan predecesor, mismo dominio.

## Estimación global

- **Tareas totales**: 3.
- **Esfuerzo estimado**: 10-13h / 3 sesiones — más pequeño que `kb-ingestion` (sin migración, sin
  puertos nuevos, reutiliza el contrato `RawDoc`/`ParsedUC`/`ParseError` ya existente). Subió desde la
  estimación inicial (6-9h) en dos pasadas: `design-review` (inversión del default → adaptar ~21 tests
  existentes; validación del valor de alias) y `scenario-coverage` (extracción de título consciente de
  bloques de código, descriptor `SourceType`, parseo perezoso del JSON de alias, test de transición entre
  formatos, y ~15 fronteras/errores nuevos). Bajó algo por recortar `relacionado`.
- **Recursos**: ninguno externo; sin `OPENAI_API_KEY` real necesaria para el gate (fixtures, no la KB
  real); acceso de solo-lectura al repo externo de verificación para fixtures fieles a la estructura
  real (no a su vocabulario de marca).

## Criterios de calidad y verificación

- TDD con pytest; tests antes de la implementación en cada tarea.
- `make test` (pytest) + `ruff check`/`ruff format --check` + `mypy strict` en verde tras cada tarea.
- Gate de mutation testing (`cosmic-ray`, `break: 80`, vía `stack.packages.backend.mutation-command`)
  sobre los ficheros que toca cada tarea.
- Arquitectura hexagonal sin cambios: `packages_uc.py`/`sources.py` no importan infra; siguen siendo
  funciones puras igual que `loader.py`/`parser.py`.
- Regresión: los 946 tests backend existentes siguen en verde **tras añadir `source_type` explícito a
  los ~21 de `test_pipeline.py`** (consecuencia declarada de invertir el default); ninguna aserción
  existente cambia.
- Ningún fichero de producto (código, `rag-ingestion.md`, `CU-BE-07`, `data-model.md`, ADR) contiene el
  nombre del cliente/proyecto usado para verificar el formato — grep de guardia antes de cerrar el plan.
- Fixtures nuevas verificadas contra la estructura real (no inventadas, pero con nombres de package
  genéricos) — cada fixture cita en un comentario de test qué aspecto del formato real reproduce.

## Tasks

- [x] `backend-kb-source-packages-uc-01` (P1) — Loader `packages_uc` (descubrimiento de ficheros:
  `packages/*/docs/aiup/use-cases/UC-*.md` + `docs/aiup/glossaries/*.md`; exclusión verificada de un
  árbol hermano no reconocido) · depends_on: —
- [x] `backend-kb-source-packages-uc-02` (P1) — Parser `packages_uc` (frontmatter real, H1→title,
  alias de package vía `package_aliases` inyectado + validación del valor contra `Package`, `traza`
  defensiva, glosario íntegro) · depends_on: `backend-kb-source-packages-uc-01`
- [ ] `backend-kb-source-packages-uc-03` (P1) — `Settings.kb_source_type`/`kb_package_aliases` +
  registro `app/ingestion/sources.py` + wiring en `pipeline.ingest()` (`functools.partial`)/CLI
  (`--source-type` + aviso de alias vacío) + inversión del default y adaptación de los tests
  existentes + tests de integración end-to-end + docs (`rag-ingestion.md`/`data-model.md`/`CU-BE-07`/
  ADR nuevo) · depends_on: `backend-kb-source-packages-uc-02`

## Registro de cambios del plan

- 2026-08-22: creado (draft, plan mode), tras investigación verificada contra un repo real de
  documentación (no solo la spec): confirmados los 268 UC repartidos por subdirectorio de package, el
  frontmatter real (`id`/`dominio`/`estado`/`traza`), la existencia y las 3 discrepancias del
  generador de site intermedio (posición de negrita, backticks, nombre de marca en `package`), y la
  cobertura 100% de `dominio:`/`estado:` contra los enums existentes (sin necesidad de tocar el modelo
  de dominio ni migrar esquema).
- 2026-08-22: `grilling` (owner) — decisiones:
  1. **Sin referencias al cliente/proyecto verificado dentro del producto**: ni en código, ni en
     `source_type`, ni en fixtures, ni en specs — renombrado `"griddo-aiup"`→`"packages-uc"`,
     `griddo_aiup.py`→`packages_uc.py`, `kb_griddo_aiup/`→`kb_packages_uc/`, plan renombrado de
     `kb-source-griddo-aiup`→`kb-source-packages-uc`. Este plan y su Registro de cambios sí pueden
     citar la fuente real de verificación (trazabilidad de proceso).
  2. **Alias de package → configuración (`Settings.kb_package_aliases`, JSON desde `.env`), no tabla
     hardcodeada en código** — es vocabulario específico del deployment, no de la estructura del
     formato; vacío por defecto.
  3. **`Settings.kb_source_type: str`** (no `Literal`) — validación perezosa, para no tumbar el
     arranque de toda la app por un typo en una env var que solo usa la ingestión.
  4. **CLI `--source-type`**, precedencia argumento > settings (mismo patrón que `path`).
  5. **Body sin limpiar**: no se replica el `stripAcLabels` del generador de referencia.
  6. **Directorio de package sin alias configurado → skip+log**, mismo criterio que domain/estado
     fuera de catálogo.
  7. **`relacionado` anclado** a `\[\[(UC-[A-Z]+-\d+)\]\]` (posteriormente **recortado del plan** por
     `design-review` #5 — ver abajo).
  8. **`traza` no-lista → se envuelve** en lista de un elemento, no se trata como malformado.
  9. **ADR nuevo y corto**, no se amplía el ADR-0010.
  10. **Test explícito** de exclusión de un árbol hermano con convención de carpeta distinta (no solo
      "por construcción" del glob).
  Todas mis recomendaciones se confirmaron tal cual, salvo el naming (decisión 1, iniciada por el
  owner, no una recomendación mía original).
- 2026-08-24: `design-review` (subagente fresco, sin `model` explícito — `models.design-review` en
  `task-pipeline.yml` vale `claude-opus-4-8`, que **no es un id de modelo válido**; se avisó y se cayó
  a inherit, mismo aviso que en los planes anteriores; **el fichero de config sigue sin corregir**).
  Veredicto: NO daba el visto bueno sin cambios. Hallazgos y resolución:
  1. **[Bloqueante, resuelto — decisión del owner]** `resolve_source(source_type) -> (LoadFn, ParseFn)`
     no podía producir el `parse_fn` de `packages-uc`, que necesita el parámetro obligatorio extra
     `package_aliases` que `vitepress-domains` no tiene; el plan admitía el hueco sin cerrarlo.
     Resuelto con la alternativa (b): `ingest()` gana `package_aliases` y especializa el `parse_fn` con
     `functools.partial`; `resolve_source` mantiene su firma de un solo argumento.
  2. **[Riesgo real, corregido — decisión del owner]** El default `"vitepress-domains"` dejaba el
     formato hipotético nunca verificado como producción por defecto: un despliegue con la ruta real
     pero sin `KB_SOURCE_TYPE` corría el loader equivocado y terminaba "con éxito" reportando 0
     procesados, indistinguible de "no había nada". **Default invertido a `"packages-uc"`**; coste
     aceptado y declarado: ~21 tests de `test_pipeline.py` reciben `source_type="vitepress-domains"`
     explícito, y el criterio de regresión del plan se corrigió (ya NO afirma "sin modificarlos").
  3. **[Corregido]** Con `kb_package_aliases={}` la ingestión saltaba todo con éxito y `report=0`,
     mismo output visible que un origen vacío legítimo → **aviso explícito por stderr**.
  4. **[Corregido]** `data-model.md` §4.3 documenta la precedencia de `package` como regla universal;
     con `packages-uc` deja de serlo (no hay Trazabilidad) y ese fichero no estaba en la lista de docs
     a corregir → **añadido al alcance**.
  5. **[Corregido — decisión del owner]** El objetivo de wiki-links → `relacionado` invertía diseño y
     tests en un campo sin ningún consumidor (`KBDocumentDraft` no tiene el campo; `ParsedUC.relacionado`
     no se lee fuera de `parser.py`) — la misma especulación que el plan rechaza en otros puntos.
     **Recortado del plan** y movido a Fuera de alcance hasta que el retriever lo necesite.
  6. **[Corregido]** Nada validaba que el **valor** de un alias fuera un miembro real de `Package`: un
     typo llegaba a `pipeline._to_draft()` → `Package(...)` sin protección → `ValueError` → `except
     Exception` genérico de la CLI ("error inesperado"), rompiendo la paridad prometida en el
     Objetivo 3. **Validación añadida en el parser** (skip+log).
  7. **[Anotado en el ADR]** Mantener `vitepress-domains` como opción de primera clase sin
     corresponder a ninguna fuente real confirmada es especulación perpetuada en el árbol de selección
     de producción; se registra como **deuda explícita** con su criterio de borrado, no como "se deja
     tal cual".
  Hallazgos que resistieron (sin cambios): ausencia de migración de esquema, la disciplina de no
  referenciar al cliente, el rechazo del mapeo declarativo genérico, y la reutilización sin tocar de
  `RawDoc`/`ParsedUC`/`ParseError`/`GLOSARIO_UC_ID_PREFIX` como contrato compartido.
- 2026-08-24: **evaluación de Use-Case 3.0** (Jacobson/Spence/de Mendonca, mayo 2024) pedida por el
  owner antes de arrancar, como posible **estándar del documento fuente de la KB** ("nosotros aplicamos
  el estándar que queremos y el cliente se adapta"). Leídas las páginas 1-14 de 76 del ebook oficial
  (principios + conceptos núcleo; **no** leídos los capítulos "Practices" p43 ni "Work Products" p65).
  **Resultado: no se adopta.** Razón, con el criterio correcto (calidad de *retrieval*, no de spec de
  equipo): la estructura de UC 3.0 —`Basic Flow` como pasos numerados (`1. Browse Products`) y
  `Alternate Flows` como etiquetas (`Alt1 – Keyword search`)— produce **chunks que no responden a
  nada**: un paso aislado es inútil sin los anteriores y no contiene la explicación. El formato real
  verificado es mejor para RAG precisamente en lo contrario: `## Comportamiento` es un párrafo narrativo
  autocontenido que lee como una respuesta de helpdesk, `## Conceptos` es término→definición, y
  `## Reglas e invariantes` son reglas completas (`AC1..ACn`). Adoptar UC 3.0 **empeoraría** el RAG.
  Decisión adicional del owner: **no** escribir todavía la spec de un estándar propio de documento de KB
  (aunque la necesidad se reconoce como real y no resuelta — no existe hoy ningún estándar propio
  documentado que dar a un cliente); prioridad a ingerir la fuente real que ya existe. Queda como
  follow-up, no como parte de este plan.
  - **Nota descartada por el camino** (evaluación inicial, sobre la pregunta equivocada): también se
    valoró UC 3.0 para nuestros propios `CU-BE-*`/`CU-FE-*`. Ahí hay además un **blocker duro**: el
    check mecánico de `sdd-lint` exige secciones **Cockburn+Gherkin** en los CU con severidad **ERROR**
    (bloquea el cierre de toda tarea), y esa skill vive en el plugin `task-pipeline`, no en este repo.
    Y no habría hueco que llenar: `## Escenario principal` ≡ Basic Flow, `## Extensiones` (`2a`, `2b`)
    ≡ Alternate Flows —con el anclaje al paso de origen, que UC 3.0 pierde con su `Alt N` plano—,
    `spec.md` → `## Casos de uso` ≡ use-case model, y plan → `## Tasks` ≡ slices.
- 2026-08-24: **plan reanudado**, forma de las tareas sin cambios (3 tareas horizontales:
  loader → parser → wiring). Se consideró re-slicearlas en vertical siguiendo el Principio 10 de UC 3.0
  (cada tarea entrega ingestión end-to-end) y se descartó: `loader`/`parser` son funciones puras con
  tests propios, la forma horizontal es la que usó el plan predecesor `kb-ingestion` (7 tareas, 946
  tests en verde), y re-slicear obligaría a re-pasar `design-review` por cambio material de
  descomposición.
- 2026-08-24: `CU-BE-07` **extendido** (Paso 5 de `/plan-task`, con `features.sdd` on el CU es la fuente
  única del Gherkin y las tareas enlazan a él): Precondiciones ahora describen **ambos** `source_type`;
  el paso 1 del escenario principal se generalizó al tipo configurado; extensiones nuevas **1g-1l** y
  **2a**; reglas de negocio nuevas **RN-4** (el `source_type` determina de dónde sale cada metadato; la
  precedencia 1c es específica de `vitepress-domains`) y **RN-5** (los alias son configuración de
  deployment, no tabla en código); 9 escenarios Gherkin nuevos, incluido un `Scenario Outline` para las
  formas de `traza`.
- 2026-08-24: `scenario-coverage` (subagente QA fresco, `model: sonnet` — `models.scenario-coverage` sí
  es un alias válido, a diferencia de `models.design-review`). Recorrió las 8 dimensiones sobre el set
  completo de las 3 tareas + el CU enlazado. **Sección (B) — huecos fuera del alcance declarado:
  ninguno** (el subagente confirmó qué plan leyó y contra qué bullets contrastó). Decisiones del owner
  sobre (A):
  1. **[Aplicado, diseño]** `kb_package_aliases` como `dict[str, str]` se valida **eager** en
     `Settings()`: un JSON malformado en `.env` tumbaría el arranque de **toda** la app, el mismo riesgo
     que ya evitamos declarando `kb_source_type` como `str` — incoherencia nuestra. Resuelto: el campo
     pasa a **`str` (JSON crudo) con parseo perezoso** en el punto de uso; JSON inválido → error de uso
     código `2`, acotado a la ingestión (nueva extensión **1m** del CU).
  2. **[Aplicado, diseño]** No estaba definido **cómo sabe la CLI que un `source_type` requiere alias**
     para el aviso de 1l: `resolve_source() -> tuple[LoadFn, ParseFn]` no lleva ese metadato, así que la
     única salida era un `if source_type == "packages-uc"` hardcodeado, o un **falso positivo** avisando
     de alias vacíos con `vitepress-domains`. Resuelto: `resolve_source()` devuelve un **descriptor
     `SourceType`** (`load`/`parse`/`requires_package_aliases`) en vez de una tupla. Ajusta la firma que
     fijó `design-review` #1; la inyección de alias sigue siendo por `ingest()` + `functools.partial`.
  3. **[Aplicado]** Hallazgo transversal: **cambiar el `source_type` entre ejecuciones sobre la misma BD
     reconcilia (borra) los documentos del formato anterior** — verificado en `pipeline.ingest`
     (`existing_uc_ids() - origin_uc_ids`, sin distinguir procedencia). Es correcto (el origen es la
     verdad) pero la inversión del default (`design-review` #2) permite dispararlo sin quererlo, y la
     regresión solo probaba los dos formatos por separado, nunca la transición. Resuelto: nueva extensión
     **4c** + escenario + test de integración + advertencia al operador en `rag-ingestion.md`/ADR. Se
     descartó añadir un guardarraíl por volumen de borrado (umbral + flag) por no ampliar el alcance.
  4. **[Aplicado, riesgo real de bug]** El regex de título (`^#\s+(.+?)\s*$`, multiline) **matchea una
     línea `# comentario` dentro de un bloque de código** — muy probable en UC reales, y nuevo en este
     plan (en `parser.py` el título viene del frontmatter, nunca de un regex sobre el cuerpo). Escenario
     añadido, más el de "varios H1 → se toma el primero".
  5. **[Aplicado]** Una `RawDoc` cuya ruta **no contiene** el segmento de package debe saltarse como
     malformado, no lanzar `IndexError`/`ValueError` sin control (mismo criterio que el hallazgo #6 de
     `design-review` sobre el valor del alias).
  6. **[Aplicado]** Un **directorio** cuyo nombre matchea `UC-*.md` entra en el glob → hace falta
     `is_file()` propio. Añadidos también: orden **documentado** (UC antes que glosarios, alfabético)
     y no solo estable; ausencia total del directorio de glosarios; permisos denegados en un
     **directorio** (no solo en un fichero); glosario mal ubicado dentro de un package; UC anidado más
     profundo que la convención; sensibilidad a la caja del prefijo/extensión; `--source-type` con otra
     caja → no reconocido (sin alias tolerados).
  7. **[Aplicado]** Fronteras del parser: `traza: []` como clase propia; `id` de tipo no textual →
     malformado; fichero de glosario vacío → glosario con cuerpo vacío, no malformado.
  8. **[Decisión mía, sin precedente en la spec — declarada como tal]** `traza` con elementos **no
     textuales** (`[1, true]`): se convierten a su representación textual en vez de descartarlos o
     tratar el documento como malformado. Criterio: `traza` es metadato opcional sin consumidor hoy, y
     coercionar nunca pierde información ni aborta; ninguno de los 268 UC reales verificados presenta
     este caso (es defensivo).
  9. **[Aplicado]** El **espacio de nombres de `uc_id` es compartido** entre tipos de fuente: se declara
     explícitamente en la spec en vez de quedar implícito.
  Dimensiones descartadas por el subagente con su porqué: **concurrencia** y **ciclo de vida/reentrada**
  (`load`/`parse`/`resolve_source` son puras; la única concurrencia real —dos `ingest()` simultáneos— ya
  la resuelve el advisory lock de `kb-ingestion` y este plan no la toca).
- 2026-08-24: **plan arrancado** (`status: active`) y tarea `-01` ejecutada. El gate `/sdd-lint` del
  cierre de la `-01` destapó **2 ERROR preexistentes** (ninguno introducido por la tarea, que no toca
  artefactos SDD) y varios AVISO. Decisión del owner: **arreglar los dos ERROR ahora**.
  1. **[ERROR, resuelto]** `FR-041` (resumen de analytics) no estaba referenciado en **ningún** caso de
     uso → trazabilidad rota. Se crea **`CU-BE-11-resumen-de-analytics.md`**, fiel al comportamiento ya
     implementado (`app/domain/services/analytics.py`, `app/infra/db/repositories/analytics.py`), y se
     enlaza desde `spec.md`. **Supersede** la decisión de `grilling` del plan `routers-flujo-ia` de dejar
     FR-041 "sin CU dedicado" — el docstring de `app/api/v1/routers/analytics.py` se actualiza para no
     seguir afirmando lo contrario.
  2. **[ERROR, resuelto]** `FR-033` ordenaba fallar el batch "reportando **el par**", mientras `CU-BE-07`
     (ext. **1f** y su escenario) exige **todos** los ficheros en conflicto — el CU endureció el
     comportamiento (ya testeado en `test_pipeline.py`) y el FR se quedó atrás. `spec.md:84` alineado con
     el CU.
  3. **[AVISO, enrutado a la `-03`]** `FR-032` describe solo el formato hoy declarado hipotético
     (`title/domain/package/uc` + Trazabilidad) y **7 comportamientos de `CU-BE-07` no tienen FR**
     (selección de `source_type` + código 2, config de alias inválida, advisory lock, run vacío, abort
     ante fallo real, cambio de `source_type` entre ejecuciones). El plan preveía **no tocar `spec.md`**;
     se corrige: la `-03` añade los FR que falten junto al resto de docs. **Amplía el alcance de la `-03`.**
  4. **[AVISO, enrutado a la `-03`]** **ADR-0010** llama "fuente verificada" al formato que `CU-BE-07`
     declara "nunca verificado"; `rag-ingestion.md:7` repite la afirmación. La `-03` ya corrige
     `rag-ingestion.md` §1/§2 y escribe el ADR nuevo → **añade la contranota en ADR-0010** en vez de
     dejar la contradicción en pie (matiza la decisión de `grilling` #9, que solo decía "no ampliar" el
     ADR-0010; una contranota de trazabilidad no es ampliarlo).
  5. **[AVISO, enrutado a la `-03`]** Contradicción interna en `CU-BE-07`: la ext. **4b** (origen vacío
     "no toca la base de datos") es una **excepción no declarada** a la reconciliación del paso 4 /
     FR-034 (con origen vacío, *todos* los `uc_id` de BD están ausentes). El comportamiento
     implementado es 4b; falta declararlo como regla de negocio. La `-03` lo formaliza.
  6. **[AVISO, aceptado sin cambio]** Escenarios de `CU-BE-07` que nombran etapas internas
     (`When se descubren los documentos`, `When se parsea`): son los bloques que las tareas `-01`/`-02`
     testean a nivel unit; se acepta la fuga de estructura a cambio de trazabilidad 1:1 test↔escenario.
     Igual para el orden de extensiones no-Cockburn y los escenarios con más de una propiedad en el
     `Then` — no se re-numera un CU vivo a mitad de plan.
