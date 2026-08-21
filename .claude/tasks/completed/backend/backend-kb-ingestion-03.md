---
id: backend-kb-ingestion-03
package: backend
plan: kb-ingestion
status: completed
priority: 1
depends_on: []
estimate: 3.5h
actual: 3.5h
created: 2026-08-21
updated: 2026-08-21
---

# Loader + parser (frontmatter + Trazabilidad + glosario)

## Description

`app/ingestion/loader.py` y `parser.py` son GUIÓN puro. El loader recorre `domains/<dominio>/uc/UC-*.md`
+ `<dominio>/index.md` (ruta configurable; excluye el `domains/index.md` raíz, navegación sin
Glosario). El parser extrae `frontmatter` (`title/domain/package/uc`), el bloque `::: info Trazabilidad`
(`Estado`/`Package`/`Traza`), la línea `Relacionado:`, y — solo de `index.md` — el bloque `##
Glosario`. La fuente real (268 UC) no existe en esta máquina: todo se testea contra fixtures `.md` en
`tests/fixtures/kb/domains/...` (mismo layout que la fuente real).

## Spec

- `.claude/specs/backend/rag-ingestion.md` §1/§2.
- `.claude/specs/backend/casos-de-uso/CU-BE-07-ingestion-de-la-kb.md` (extensiones 1a/1c/1d).
- `loader.py`: `load(path: Path) -> Iterator[RawDoc]` (`RawDoc = {path, content}`); recorre
  `<path>/<dominio>/uc/UC-*.md` + `<path>/<dominio>/index.md`; excluye `<path>/index.md`. Streaming por
  fichero (no carga todo en memoria).
- `parser.py`: `parse(raw: RawDoc) -> ParsedUC | ParseError`.
  - Frontmatter sin `uc` o YAML no parseable → `ParseError` (skip+log, no lanza). El YAML se parsea con
    `yaml.safe_load` (nunca `yaml.load`) — un frontmatter con un tag adversario
    (`!!python/object/...`) se rechaza como malformado, nunca ejecuta nada.
  - `package`/`domain` fuera de los 5/17 valores válidos → `ParseError` (mismo tratamiento que
    malformado — decisión de `grilling`).
  - Bloque `::: info Trazabilidad` ausente en un UC que por lo demás es válido → `ParseError` (mismo
    tratamiento que malformado — decisión: la spec asume que los UC siempre lo traen; si un UC editado
    lo pierde, es tan inválido como un frontmatter roto).
  - `package` del frontmatter ≠ Trazabilidad → **gana el frontmatter**; se registra vía `structlog`
    (decisión de `grilling`: solo log, no forma parte del retorno).
  - La línea `Relacionado:` se captura como `ParsedUC.relacionado: list[str]` (opcional, metadato — sin
    consumidor todavía, per `rag-ingestion.md` §2).
  - `index.md`: solo `## Glosario` → chunks candidatos `section_type=glosario`; `## Casos de uso`/`##
    Todos los dominios` se descartan (navegación). Un `index.md` **sin** `## Glosario` en absoluto no es
    `ParseError` — es un `ParsedUC` válido sin chunks candidatos (0 secciones, no un documento roto).
  - `source_url` se **deriva** de la ruta relativa a la raíz de la KB (no hay `url` en frontmatter):
    `str(path.relative_to(kb_root))`, p.ej. `"domains/authoring-and-editor/uc/UC-CORE-001.md"`.
  - `updated` (`kb_document.updated`) se deriva del `mtime` del fichero (`datetime.fromtimestamp(...,
    tz=UTC)`) — sin ninguna fuente mejor documentada en la spec.

## Fuera de alcance

- Chunking (H2 tolerante) — tarea `-04`.
- Embeddings — tarea `-05`.
- Persistencia / reconciliación / detección de `uc_id` duplicado entre ficheros (el parser opera
  fichero a fichero; la unicidad cross-batch la valida el pipeline) — tarea `-06`.
- Recrear la fuente real `domains/*/uc/*.md` — la restaura el owner cuando corresponda.

## Scenarios (Gherkin)

Fuente única (SDD): `CU-BE-07-ingestion-de-la-kb.md`. Esta tarea cubre, a nivel **unit** (sin DB, sin
puertos, fixtures `.md`), la parte de parseo de los siguientes escenarios (el resto — chunks/embeddings/
persistencia — lo completan `-04`/`-05`/`-06`):

- `Ingesta de un UC válido` (parcial: frontmatter + Trazabilidad se extraen correctamente).
- `Documento malformado se salta` (`ParseError`, no lanza).
- `Precedencia del package del frontmatter` (gana frontmatter + log de la discrepancia).
- `package o domain fuera de catálogo se salta` (mismo tratamiento que malformado).

> Añadido para esta tarea (loader, sin escenario propio en el CU):
> ```gherkin
> Scenario: El loader descubre los UC y los index.md de dominio, no el índice raíz
>   Given un árbol con domains/<d>/uc/UC-*.md, domains/<d>/index.md y domains/index.md
>   When se ejecuta load(path)
>   Then se devuelven los UC y los index.md de dominio, pero NO domains/index.md
>
> Scenario: index.md solo aporta el bloque Glosario
>   Given un index.md con ## Glosario, ## Casos de uso y ## Todos los dominios
>   When se parsea
>   Then solo el contenido de ## Glosario se conserva como candidato a chunk
>
> Scenario Outline: Clases de equivalencia de "documento malformado"
>   Given un documento con <variante>
>   When se parsea
>   Then devuelve ParseError
>
>   Examples:
>     | variante                                                        |
>     | sin bloque frontmatter (el fichero no empieza con --- ... ---)  |
>     | frontmatter con YAML sintácticamente inválido                   |
>     | frontmatter válido pero sin la clave uc                         |
>     | frontmatter válido con uc: "" (clave presente, valor vacío)     |
>     | frontmatter válido pero sin el bloque de Trazabilidad           |
>
> Scenario: Un frontmatter con un tag YAML adversario se rechaza sin ejecutar nada
>   Given un frontmatter con un tag tipo !!python/object
>   When se parsea con yaml.safe_load
>   Then se rechaza como ParseError, sin ejecutar ningún código
>
> Scenario: index.md sin ningún bloque Glosario no es un error
>   Given un index.md con solo ## Casos de uso y ## Todos los dominios
>   When se parsea
>   Then devuelve un ParsedUC válido sin chunks candidatos (no ParseError)
>
> Scenario: source_url se deriva de la ruta relativa a la raíz de la KB
>   Given un UC en <kb_root>/domains/<dominio>/uc/UC-XXX-001.md
>   When se parsea
>   Then source_url == "domains/<dominio>/uc/UC-XXX-001.md"
>
> Scenario: Fichero illegible o con encoding inválido se salta con log
>   Given un fichero sin permisos de lectura, o con bytes no-UTF8
>   When se intenta cargar/parsear
>   Then se salta con log (no lanza una excepción sin control)
>
> Scenario: load() con una ruta raíz inexistente falla claro
>   Given un path que no existe en disco
>   When se llama a load(path)
>   Then se lanza un error claro (no un iterador vacío silencioso)
> ```
>
> **Verificación del log** (decisión de `scenario-coverage`): todo escenario "se salta con log" / "se
> registra la discrepancia" se testea con `pytest caplog` — `structlog` configurado para reenviar al
> `logging` estándar de Python, para que `caplog` capture el evento real (nivel + campos), no solo el
> efecto observable (skip / frontmatter-gana). Patrón nuevo en este repo; documentarlo como tal.

## Provides

- `load(path) -> Iterator[RawDoc]` (`loader.py`), `parse(raw) -> ParsedUC | ParseError` (`parser.py`).
- Fixtures `.md` en `backend/tests/fixtures/kb/domains/...` (caso feliz, H2 renombrado/ausente,
  frontmatter malformado, `uc_id` duplicado entre dos ficheros, sección grande con tabla, `index.md` con
  Glosario, `domains/index.md` raíz) — reutilizadas por `-04`/`-06`.
- Consumido por `-04` (chunker) y `-06` (pipeline).

## Definition of Done

- [x] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [x] Cada escenario tiene al menos un test (camino feliz + bordes/errores)
- [x] Todos los tests en verde (`make test`) — 838 passed
- [x] Spec cumplida; `Provides` disponible para `-04`/`-06`
- [x] `ruff check` + `ruff format --check` + `mypy` strict OK
- [x] Gate de mutation `cosmic-ray` (`break: 80`, referencia no verificada) sobre `loader.py`/`parser.py`
  — 4.59% supervivencia (9/196, los 9 documentados como equivalentes)
- [x] Gate `/sdd-lint` — N/A esta tarea: no toca spec.md/CU/ADR (el `::: info Trazabilidad` exacto es
  una interpretación documentada de `rag-ingestion.md` §2, sin fuente real disponible para verificar)
- [x] Gate de `fact-checker` superado (INCORRECTO bloquea) — 10/10 VERIFICADO
- [x] Documentación — docstrings (anti-patrones: leer `url` inexistente, silenciar un doc no parseable)
  + session log
