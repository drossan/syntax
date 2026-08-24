---
id: backend-kb-source-packages-uc-02
package: backend
plan: kb-source-packages-uc
status: done
priority: 1
depends_on: [backend-kb-source-packages-uc-01]
estimate: 4h
actual: 2.5h
created: 2026-08-24
updated: 2026-08-24
---

# Parser `packages_uc` (frontmatter real, H1→título, alias de package, glosario íntegro)

## Description

El parser actual (`app/ingestion/parser.py`) espera frontmatter `title`/`domain`/`package`/`uc` + un
bloque `::: info Trazabilidad` — una **interpretación no verificada** de `rag-ingestion.md` §2. El
formato real trae **solo** `id`/`dominio`/`estado`/`traza`: no hay `title` (es el primer H1), no hay
`package` (se deriva del subdirectorio, traducido por alias de configuración) y no existe el bloque de
Trazabilidad.

Esta tarea añade el `parse()` de `app/ingestion/packages_uc.py` (el `load()` lo dejó `-01`),
reutilizando **sin modificar** los dataclasses `ParsedUC`/`ParseError` y la constante
`GLOSARIO_UC_ID_PREFIX` de `parser.py`. `parser.py` **no se toca**: los dos tipos de fuente son
implementaciones independientes que comparten solo el contrato de datos, no detalles internos (por eso
`_VALID_DOMAINS`/`_VALID_ESTADOS` se derivan de nuevo aquí desde los enums, en vez de importar los
privados del otro módulo).

## Spec

- `.claude/specs/backend/rag-ingestion.md` §2/§3 · `.claude/specs/backend/casos-de-uso/CU-BE-07-ingestion-de-la-kb.md`
  (extensiones **1h**/**1i**/**1j**/**2a**; reglas **RN-4**/**RN-5**).
- `packages_uc.py`: `parse(raw: RawDoc, *, kb_root: Path, package_aliases: dict[str, str]) -> ParsedUC | ParseError`.
  - `package_aliases` se **inyecta** (no se lee de `Settings`: el módulo no importa `app.core.config`,
    mismo criterio que el resto de `app.ingestion`). Quién lo pasa es `-03`.
  - **UC** (fichero bajo `.../use-cases/`):
    - Frontmatter con `yaml.safe_load` (**nunca** `yaml.load`: un tag adversario `!!python/object/...`
      se rechaza como malformado, jamás ejecuta código). Sin bloque frontmatter, YAML inválido, o
      frontmatter que no es un mapeo → `ParseError` (skip + log).
    - `id` → `uc_id`. Ausente, vacío, o **de tipo no textual** (`id: 123`) → `ParseError`.
    - `dominio` → `domain`. Fuera del catálogo `KbDomain` (17) → `ParseError`.
    - `estado`. Fuera del catálogo `KbEstado` (`draft`/`active`) → `ParseError`.
    - `traza` → `list[str]`: lista YAML tal cual; **string único → lista de un elemento**; lista vacía
      → lista vacía; ausente → lista vacía; **elementos no textuales → su representación textual**
      (decisión de `scenario-coverage` **sin precedente en la spec**: `traza` es metadato opcional sin
      consumidor hoy, y coercionar nunca pierde información ni aborta; ninguno de los 268 UC reales
      verificados presenta este caso — es defensivo). **No** es malformado en ninguno de esos casos
      (extensión 1j).
    - `title` = **primer H1** del cuerpo. **Sin H1 → `ParseError`** (extensión 1i): este formato no trae
      `title` en frontmatter, así que no hay de dónde derivarlo. Con **varios H1**, gana el **primero**.
      - ⚠️ **El regex ingenuo `^#\s+(.+?)\s*$` (multiline) NO sirve**: matchea una línea `# comentario`
        **dentro de un bloque de código** (` ``` `), muy probable en UC reales (ejemplos de shell/Python,
        bloques `mermaid`). Hallazgo de `scenario-coverage`; es riesgo nuevo de esta tarea, porque en
        `parser.py` el `title` viene del frontmatter y nunca de un regex sobre el cuerpo. La extracción
        debe **ignorar el contenido de los bloques de código delimitados por fences**. Reutiliza el
        criterio ya resuelto en `chunker.py` para no partir bloques de código (leerlo antes de
        reimplementar la detección de fences).
    - `package`: se toma el segmento `packages/<pkg>/` de la ruta y se traduce con `package_aliases`.
      Tres casos dan `ParseError` (skip + log), nunca una excepción sin control:
      - (a) `<pkg>` **no tiene entrada** en `package_aliases` (extensión 1h).
      - (b) su entrada apunta a un valor que **no es miembro de `Package`** (extensión 1h). Es el
        hallazgo #6 de `design-review`: sin validarlo aquí, un typo de configuración llegaría a
        `pipeline._to_draft()` → `Package(...)` sin protección → `ValueError` → `except Exception`
        genérico de la CLI ("error inesperado"), rompiendo la paridad con el resto de malformados.
      - (c) la ruta **no contiene** el segmento `packages/<pkg>/` en absoluto (posible al construir un
        `RawDoc` a mano, o si el loader cambiara): `ParseError` limpio, **nunca** un
        `IndexError`/`ValueError` de un `split()`/`index()` ingenuo (hallazgo de `scenario-coverage`,
        mismo criterio que (b)).
    - `body` = el cuerpo **sin el bloque frontmatter**, **sin ninguna limpieza cosmética**: las etiquetas
      `**ACn**` de las viñetas se conservan tal cual (decisión de `grilling`; no se replica el
      `stripAcLabels` del generador de site de la fuente).
    - `relacionado` = **lista vacía** (ver Fuera de alcance).
    - `source_url` se **deriva** de la ruta relativa a `kb_root`, igual que en `parser.py`.
    - `updated` = el `mtime` que capturó el loader en `-01` (el parser no toca el filesystem).
    - **No hay discrepancia de `package` que loguear** en este formato (RN-4): el `package` tiene una
      sola fuente (la ruta + alias). No se replica el log `kb_package_discrepancia` de `parser.py`.
  - **Glosario** (fichero bajo `.../glossaries/`):
    - `domain` = nombre del fichero sin extensión, validado contra `KbDomain` → `ParseError` si no está
      en el catálogo.
    - `body` = **contenido íntegro** del fichero (extensión 2a) — a diferencia de `vitepress-domains`,
      donde solo se conserva el bloque `## Glosario` de un `index.md`. Estos ficheros no traen
      frontmatter ni sección `## Glosario`: son el glosario entero. Un fichero **vacío** (0 bytes) es un
      glosario válido con `body=""`, **no** un `ParseError` (hallazgo de `scenario-coverage`).
    - `uc_id` = `f"{GLOSARIO_UC_ID_PREFIX}{domain}"` — se **reutiliza** la constante y el esquema de
      `uc_id` sintético que ya existen, sin cambiarlos.
    - `package`/`estado` = `""` (igual que `parser._parse_index`): es el pipeline quien decide qué
      persistir para un glosario, y esa decisión ya está tomada y cerrada en `-06` del plan anterior.

## Fuera de alcance

- **Parsear los wiki-links `[[UC-XXX-NNN]]` a `relacionado`**: recortado del plan por `design-review`
  #5 — el campo no se persiste (`KBDocumentDraft` no lo tiene) ni se lee fuera de `parser.py`. Se añade
  cuando el retriever (tarea 14) lo necesite de verdad. `ParsedUC.relacionado` queda como lista vacía.
- `Settings.kb_source_type`/`kb_package_aliases`, el registro `sources.py`, el wiring en
  `pipeline.ingest()`/CLI, la inversión del default y el aviso de alias vacío — tarea `-03`.
- **Modificar `loader.py`/`parser.py`** (`vitepress-domains`): quedan tal cual.
- **Chunking / embeddings / persistencia / reconciliación**: ya implementados y cerrados por el plan
  `kb-ingestion`; esta tarea solo produce `ParsedUC`, que es su entrada.
- **Ejecutar `make ingest` contra una fuente real**: verificación manual del owner, fuera del gate.
- **Ingerir contenido narrativo multi-package** (flows) y **fallback al glosario compartido**: no se
  ingieren.

## Scenarios (Gherkin)

Fuente única (SDD): [`CU-BE-07-ingestion-de-la-kb.md`](../../../specs/backend/casos-de-uso/CU-BE-07-ingestion-de-la-kb.md).

Esta tarea cubre, a nivel **unit** (sin BD, sin puertos, `RawDoc` construidos desde fixtures), estos
escenarios del CU — íntegros en su parte de parseo (la persistencia end-to-end la verifica `-03`):

- `Ingesta de un UC del formato real` (título desde el H1 + package resuelto por alias).
- `Normalización de la traza según cómo venga declarada` (`Scenario Outline`, extensión 1j — incluidas
  las filas de lista vacía y de elementos no textuales).
- `Un package sin alias configurado se salta` (extensión 1h, caso a).
- `Un alias que apunta a un package inexistente se salta` (extensión 1h, caso b).
- `Un UC sin encabezado principal se salta` (extensión 1i).
- `Una línea de comentario dentro de un bloque de código no se confunde con el título` — el riesgo real
  de bug de esta tarea.
- `Con varios encabezados principales se toma el primero`.
- `Una ruta que no sigue la convención de package se salta como malformado`.
- `Un identificador de tipo no textual se salta como malformado`.
- `Un glosario vacío se ingiere como glosario sin contenido`.
- `El glosario del formato real se ingiere íntegro` (extensión 2a) — la parte de parseo: el `body` es el
  contenido completo y el `uc_id` es el sintético del dominio.

> Añadido para esta tarea (comportamiento del parser sin escenario propio en el CU — mismo patrón que
> `backend-kb-ingestion-03`):
> ```gherkin
> Scenario Outline: Clases de equivalencia de "UC malformado" en el formato real
>   Given un UC con <variante>
>   When se parsea
>   Then se salta como documento malformado
>
>   Examples:
>     | variante                                                       |
>     | sin bloque frontmatter                                         |
>     | frontmatter con YAML sintácticamente inválido                  |
>     | frontmatter que no es un mapeo (una lista, un escalar)          |
>     | sin la clave del identificador                                 |
>     | con identificador presente pero vacío                          |
>     | con un dominio que no está en el catálogo                      |
>     | con un estado que no está en el catálogo                       |
>
> Scenario: Un frontmatter con un tag YAML adversario se rechaza sin ejecutar nada
>   Given un frontmatter con un tag tipo !!python/object
>   When se parsea
>   Then se rechaza como malformado, sin ejecutar ningún código
>
> Scenario: El cuerpo conserva las etiquetas de criterio de aceptación
>   Given un UC cuyas viñetas de reglas empiezan por una etiqueta de criterio de aceptación
>   When se parsea
>   Then el cuerpo las conserva tal cual, sin limpieza cosmética
>
> Scenario: La ruta de origen se deriva de la ruta relativa a la raíz de la KB
>   Given un UC dentro de un subdirectorio de package
>   When se parsea
>   Then su ruta de origen es la del fichero relativa a la raíz de la KB
>
> Scenario: Un glosario de un dominio fuera del catálogo se salta
>   Given un fichero de glosario cuyo nombre no corresponde a ningún dominio del catálogo
>   When se parsea
>   Then se salta como documento malformado
>
> Scenario: En este formato no existe discrepancia de package que registrar
>   Given un UC válido del formato real
>   When se parsea
>   Then no se registra ninguna discrepancia de package, porque su única fuente es la ruta
> ```
>
> **Verificación del log**: los escenarios "se salta con log" se testean con `pytest caplog` +
> `structlog` reenviando al `logging` estándar (patrón ya establecido en `kb-ingestion`).

## Provides

- `parse(raw, *, kb_root, package_aliases) -> ParsedUC | ParseError` en `app/ingestion/packages_uc.py`
  — el par `(load, parse)` que `-03` registra en `sources.py` queda completo.
- La tabla de validación del alias (valor ∈ `Package`) que evita que un typo de configuración escape
  como "error inesperado" de la CLI.

## Definition of Done

- [x] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [x] Cada escenario Gherkin tiene al menos un test (camino feliz + bordes/errores)
- [x] Todos los tests en verde (`make test`), sin regresión en los existentes
- [x] Spec cumplida; lo declarado en `Provides` queda disponible para `-03`
- [x] `ruff check` + `ruff format --check` + `mypy --strict` OK
- [x] Gate de mutation testing (`cosmic-ray`, `break: 80`) sobre `packages_uc.py` — survivors
  documentados como equivalentes si quedan
- [x] Gate `/sdd-lint` superado — **sin ERROR**; 3 AVISO reconocidos. Matiz: la tarea arrancó sin tocar
  artefactos SDD, pero **sí acabó modificando `CU-BE-11`** (los 2 AVISO sobre ese artefacto, creado en
  la `-01`, se corrigieron aquí). El tercero está enrutado a la `-03`
- [x] Gate de `fact-checker` superado — **14 VERIFICADO / 0 INCORRECTO / 0 NO VERIFICABLE**
- [x] Documentación — docstrings de todo símbolo público (incluidos los anti-patrones: usar `yaml.load`;
  importar los privados de `parser.py`; replicar el log de discrepancia de `package`, que en este
  formato no puede darse) + doc técnica donde aplique + session log en
  `.claude/context/backend/backend-kb-source-packages-uc-02.md`
