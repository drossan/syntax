---
id: backend-kb-source-packages-uc-03
package: backend
plan: kb-source-packages-uc
status: pending
priority: 1
depends_on: [backend-kb-source-packages-uc-02]
estimate: 4.5h
actual:
created: 2026-08-24
updated: 2026-08-24
---

# Registro de tipos de fuente + wiring (`Settings`, `sources.py`, `pipeline`, CLI) + docs

## Description

`-01` y `-02` dejaron el par `(load, parse)` del formato real, pero **nadie lo llama**: hoy
`pipeline.ingest()` importa `load`/`parse` directamente de `loader.py`/`parser.py`, sin ninguna
indirección. Esta tarea cierra el plan: un registro de tipos de fuente, la config que lo selecciona, el
wiring hasta la CLI, y la **inversión del default** para que el formato real verificado sea el de
producción y el hipotético el opt-in.

Cierra también la documentación de las tres capas (`rag-ingestion.md`, `data-model.md`, ADR nuevo) y es la
única tarea del plan que toca ficheros ya existentes de producción.

## Spec

- `.claude/specs/backend/rag-ingestion.md` §1/§2 · `.claude/specs/backend/casos-de-uso/CU-BE-07-ingestion-de-la-kb.md`
  (Precondiciones; extensiones **1g**/**1l**; reglas **RN-4**/**RN-5**) · `.claude/specs/backend/data-model.md` §4.3.
- **`app/core/config.py`**:
  - `kb_source_type: str = "packages-uc"` — **`str`, no `Literal`**: la validación es **perezosa**, en
    `resolve_source()`/CLI. Un `Literal` estricto haría que un typo en esa env var tumbase el arranque de
    **toda** la app (auth, tickets…), no solo la ingestión; `config.py` ya evita eso a propósito con
    `llm_provider`/`kb_source_path`.
  - `kb_package_aliases: str = ""` — el **JSON crudo**, **no** un `dict[str, str]`
    (`KB_PACKAGE_ALIASES='{"vendor-render":"syntax-render"}'`). Un `dict` tipado lo valida
    pydantic-settings de forma **eager** al construir `Settings()`: un JSON malformado tumbaría el
    arranque de **toda** la app (auth, tickets…), no solo la ingestión — el mismo riesgo que motivó
    declarar `kb_source_type` como `str` y no `Literal` (hallazgo de `scenario-coverage`). Vacío por
    defecto → sin configurar, este tipo de fuente no ingiere nada (extensión 1l).
  - Docstrings de ambos campos, como el resto de `Settings`, explicando **por qué** son `str`.
- **`app/ingestion/sources.py`** (nuevo): `resolve_source(source_type: str) -> SourceType`.
  - `SourceType` es un `@dataclass(frozen=True)` con `load`, `parse` y
    **`requires_package_aliases: bool`** — **no** una tupla desnuda (decisión de `scenario-coverage`): la
    CLI necesita ese metadato para decidir si emite el aviso de la extensión 1l, y sin él la única salida
    era un `if source_type == "packages-uc"` hardcodeado en la CLI o un **falso positivo** avisando de
    alias vacíos con `vitepress-domains` (que no los usa y cuyo default de alias es vacío). Ajusta la
    firma que había fijado `design-review` #1; la inyección de alias sigue siendo por `ingest()` +
    `functools.partial`.
  - `"packages-uc"` → `packages_uc.load`/`packages_uc.parse`, `requires_package_aliases=True`;
    `"vitepress-domains"` → `loader.load`/`parser.parse` (**sin tocar** esos módulos),
    `requires_package_aliases=False`.
  - `source_type` no registrado → `app.domain.errors.Validation` (el mismo tipo que ya usa
    `pipeline.ingest` para `uc_id` duplicado), con el valor recibido y la lista de válidos en el mensaje.
    **Solo la forma canónica exacta** se reconoce: `"Packages-UC"` es un valor no registrado, no un alias
    tolerado.
  - Alias de tipos (`LoadFn`/`ParseFn`) declarados aquí; las dos `parse` tienen firmas distintas
    (`packages_uc.parse` exige `package_aliases`), así que el tipo debe admitirlo sin romper
    `mypy --strict` — resolverlo con el `Protocol`/alias que haga falta, sin `Any` silencioso.
- **`app/ingestion/pipeline.py`**: `ingest()` gana `source_type: str = "packages-uc"` y
  `package_aliases: dict[str, str] = {}`.
  - Dentro: `load_fn, parse_fn = resolve_source(source_type)`; el `parse_fn` se especializa con
    `functools.partial(parse_fn, package_aliases=package_aliases)` **solo** para los tipos que lo
    declaran. Sustituye los 2 call-sites que hoy usan `load`/`parse` importados directamente.
  - `pipeline.py` **sigue sin importar `app.core.config`**: los alias los inyecta el llamante, igual que
    ya inyecta `token_budget`/`encoding`/`batch_size`/`embedding_model_name`.
- **`app/ingestion/cli.py`**:
  - Flag `--source-type`, precedencia **argumento > settings** (mismo patrón que `path` vs
    `settings.kb_source_path`).
  - Un `source_type` no registrado sale con **código 2** (error de uso), no 1 (extensión 1g): el
    `Validation` de `resolve_source` es un `DomainError`, que hoy la CLI mapea a `1` — hay que
    distinguirlo, o resolver el tipo **antes** de entrar en `_run`, o mapearlo explícitamente. Que no
    escape una traza cruda.
  - **Parseo del JSON de alias** (`settings.kb_package_aliases`, que llega como `str`): inválido →
    código **2** con mensaje claro, acotado a la ingestión (extensión 1m). El resultado parseado
    (`dict[str, str]`) es lo que se pasa a `ingest(package_aliases=...)`.
  - **Aviso por stderr** si `SourceType.requires_package_aliases` y los alias están vacíos (extensión
    1l): sin él, `report=0 procesados` es indistinguible de un origen vacío legítimo (4b). Si el tipo
    **no** los requiere, **no** se avisa (evita el falso positivo con `vitepress-domains`).
- **Tests existentes**: los de `tests/test_pipeline.py` que llaman `ingest()` sin `source_type` (21
  funciones de test en el fichero; usan fixtures del formato `vitepress-domains`) reciben
  `source_type="vitepress-domains"` explícito. **Ninguna aserción cambia** — solo se añade el parámetro.
  Consecuencia declarada y aceptada de invertir el default (`design-review` #2).
- **Tests de integración nuevos** (contra Postgres+pgvector de Docker, patrón de `test_pipeline.py`):
  el camino end-to-end del formato real — un UC de fixture queda como `kb_document` + `kb_chunk` +
  `embedding` reales; el glosario también; el árbol hermano no aparece; el aviso de alias vacío se emite
  (y **no** se emite con `vitepress-domains`); y la **transición entre formatos** (extensión 4c): una BD
  ya ingerida con un `source_type` y una segunda ejecución con el otro → los documentos del formato
  anterior que no reaparecen se reconcilian. Este último es el escenario operacional que la inversión del
  default hace posible, y hasta ahora la regresión solo probaba cada formato **por separado**.
- **Documentación**:
  - `rag-ingestion.md` §1/§2: documenta los **dos** tipos por separado — `packages-uc` (real verificado:
    layout, frontmatter, título desde H1, alias de package) y `vitepress-domains` (hipótesis original, no
    verificada, tal cual queda). Corrige la ruta de fuente primaria: la de `docs-site/domains/` **no
    existe** y este plan no la genera. Actualiza la redacción de "mismo hash" si aún queda algún resto.
    **Advierte al operador** de la transición entre formatos (extensión 4c): cambiar el `source_type`
    sobre la misma BD reconcilia los documentos del formato anterior. Declara explícitamente que el
    **espacio de nombres de `uc_id` es compartido** entre tipos de fuente (hoy solo se usa un tipo por
    invocación, pero la afirmación no estaba en ningún fichero).
  - `data-model.md` §4.3: nota de una frase — la precedencia `package` frontmatter-vs-Trazabilidad es
    **específica de `vitepress-domains`**, no una regla universal de `kb_document.package`
    (`design-review` #4).
  - **ADR nuevo y corto** (siguiente número libre según `.claude/specs/adr/adr-index.md`, formato MADR,
    entrada en el índice): registro de tipos de fuente **en código** (mapeo declarativo genérico
    descartado por falta de un segundo caso real) + alias de package como **configuración de
    deployment**. Registra además como **deuda explícita** (`design-review` #7) que `vitepress-domains`
    se mantiene como opción de primera clase sin corresponder a ninguna fuente real confirmada, y **cuál
    es el criterio para borrarlo**.
  - **Ningún fichero de producto** (código, `rag-ingestion.md`, `data-model.md`, `CU-BE-07`, ADR) menciona
    el nombre del cliente/proyecto del que se verificó el formato — `grep` de guardia antes de cerrar.

## Fuera de alcance

- **Modificar `loader.py`/`parser.py`** (`vitepress-domains`): quedan tal cual; solo sus **tests** reciben
  el `source_type` explícito.
- **Parsear los wiki-links `[[UC-XXX-NNN]]` a `relacionado`**: recortado del plan (`design-review` #5).
- **Ejecutar `make ingest` contra una fuente real**: fuera del gate de esta tarea (coste real de
  embeddings, requiere `OPENAI_API_KEY`) — verificación manual del owner tras cerrar el plan.
- **Tocar el repo de documentación externo** verificado: no se ejecuta ningún build suyo ni se modifica
  su código.
- **Migración de esquema**: ninguna hace falta — `Package`/`KbDomain`/`KbEstado` ya cubren, tras el alias,
  todos los valores reales verificados.
- **Retriever real (`search`) y `OpenAIChatModel`**: siguen fuera, como en `kb-ingestion`.
- **Mapeo declarativo genérico por-tenant**: descartado (el ADR registra por qué).
- **Escribir la spec de un estándar propio de documento de KB**: follow-up reconocido del plan, no de
  esta tarea.
- **Ingerir contenido narrativo multi-package** (flows) y **fallback al glosario compartido**.

## Scenarios (Gherkin)

Fuente única (SDD): [`CU-BE-07-ingestion-de-la-kb.md`](../../../specs/backend/casos-de-uso/CU-BE-07-ingestion-de-la-kb.md).

Esta tarea cubre estos escenarios del CU, ahora **end-to-end** (integración real contra
Postgres+pgvector en Docker, no unit):

- `Un tipo de fuente no reconocido falla como error de uso` (extensión 1g) — íntegro aquí.
- `El tipo de fuente solo se reconoce en su forma canónica` (`Scenario Outline`, incluida la variante de
  caja) — íntegro aquí.
- `Una configuración de alias con JSON inválido falla acotada a la ingestión` (extensión 1m) — íntegro
  aquí.
- `Sin ningún alias configurado no se ingiere nada y se avisa` (extensión 1l) — íntegro aquí.
- `Un tipo de fuente que no usa alias no dispara el aviso de alias vacío` — íntegro aquí.
- `Cambiar el tipo de fuente entre ejecuciones reconcilia el formato anterior` (extensión 4c) — íntegro
  aquí.
- `Ingesta de un UC del formato real` — cierre end-to-end: el documento, sus chunks y sus embeddings
  quedan realmente en BD (`-02` solo verificaba el `ParsedUC`).
- `El glosario del formato real se ingiere íntegro` — cierre end-to-end.
- `Un árbol hermano con otra convención de carpeta nunca se recoge` — cierre end-to-end (`-01` lo
  verificaba a nivel de descubrimiento).
- Además, **toda la batería ya existente del CU** (idempotencia, `uc_id` duplicado todo-o-nada,
  reconciliación, advisory lock, origen vacío…) sigue verde con `source_type="vitepress-domains"`
  explícito: es la regresión que protege que la indirección no cambió el comportamiento.

> Añadido para esta tarea (wiring y config, sin escenario propio en el CU):
> ```gherkin
> Scenario: El tipo de fuente por defecto es el formato real verificado
>   Given una configuración que no especifica el tipo de fuente
>   When se ingiere la KB
>   Then se usa el formato real verificado, no el hipotético
>
> Scenario: El argumento de la CLI tiene precedencia sobre la configuración
>   Given una configuración con un tipo de fuente y una invocación que indica otro
>   When se ejecuta la ingestión
>   Then se usa el indicado en la invocación
>
> Scenario: El registro de tipos resuelve cada tipo a su propio par de descubrimiento y parseo
>   Given uno de los tipos de fuente registrados
>   When se resuelve ese tipo
>   Then se obtiene el par de funciones de descubrimiento y parseo de ese tipo
>
> Scenario: Un tipo de fuente desconocido no expone una traza cruda al operador
>   Given una invocación con un tipo de fuente que no existe
>   When se ejecuta la ingestión
>   Then el mensaje de error indica el valor recibido y los tipos válidos
> ```

## Provides

- `make ingest` / `python -m app.ingestion` funcionando **contra el formato real** de la KB — el objetivo
  del plan. Habilita la verificación manual del owner contra la fuente real (fuera del gate).
- `resolve_source()` como punto de extensión para un tercer tipo de fuente futuro (añadir un módulo +
  una entrada, sin tocar `pipeline`/CLI).
- ADR nuevo con la decisión y su deuda explícita, referenciable por la tarea 14 (retriever).

## Definition of Done

- [ ] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [ ] Cada escenario Gherkin tiene al menos un test (camino feliz + bordes/errores)
- [ ] Todos los tests en verde (`make test`) — incluidos los existentes tras añadirles `source_type`
  explícito, **sin cambiar ninguna aserción**
- [ ] Spec cumplida; lo declarado en `Provides` queda realmente disponible
- [ ] `ruff check` + `ruff format --check` + `mypy --strict` OK (incluido el tipado de `LoadFn`/`ParseFn`
  con firmas distintas, sin `Any` silencioso)
- [ ] Gate de mutation testing (`cosmic-ray`, `break: 80`) sobre `sources.py` + `cli.py` + la parte
  tocada de `pipeline.py` — survivors documentados como equivalentes si quedan
- [ ] Gate `/sdd-lint` superado — sin ERROR (AVISO reconocido). Esta tarea **sí** toca artefactos SDD
  (`CU-BE-07` ya extendido en planificación, `rag-ingestion.md`, `data-model.md`, ADR nuevo + índice)
- [ ] Gate de `fact-checker` superado — afirmaciones de la sesión verificadas (INCORRECTO bloquea)
- [ ] `grep` de guardia: ningún fichero de producto menciona el nombre del cliente/proyecto verificado
- [ ] Documentación — docstrings de todo símbolo público + doc técnica (`rag-ingestion.md`,
  `data-model.md`, ADR nuevo + `adr-index.md`) + session log en
  `.claude/context/backend/backend-kb-source-packages-uc-03.md`
- [ ] `.env.example` actualizado con `KB_SOURCE_TYPE` y `KB_PACKAGE_ALIASES` (doc de dev: sin ellos, un
  operador no sabe que existen)
