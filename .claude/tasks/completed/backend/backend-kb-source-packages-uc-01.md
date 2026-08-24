---
id: backend-kb-source-packages-uc-01
package: backend
plan: kb-source-packages-uc
status: done
priority: 1
depends_on: []
estimate: 3h
actual: 3h
created: 2026-08-24
updated: 2026-08-24
---

# Loader `packages_uc` (descubrimiento de ficheros del formato real)

## Description

`app/ingestion/loader.py` implementa el descubrimiento del formato **hipotético** `vitepress-domains`
(`<dominio>/uc/UC-*.md` + `<dominio>/index.md`), que nunca se verificó contra una fuente real. El
formato **real verificado** reparte los UC por subdirectorio de package y pone los glosarios en una
ubicación compartida, un fichero plano por dominio — otro recorrido por completo.

Esta tarea crea `app/ingestion/packages_uc.py` con **solo su `load()`** (el `parse()` es la tarea `-02`),
reutilizando **sin modificar** el dataclass `RawDoc` de `loader.py`: es el contrato ya source-agnostic
que consume el pipeline. `loader.py` **no se toca**.

La fuente real no vive en este repo: todo se testea contra fixtures en
`backend/tests/fixtures/kb_packages_uc/`, fieles a la **estructura** verificada (no a su vocabulario de
marca — los nombres de package de las fixtures son genéricos).

## Spec

- `.claude/specs/backend/rag-ingestion.md` §1/§2 · `.claude/specs/backend/casos-de-uso/CU-BE-07-ingestion-de-la-kb.md`
  (Precondiciones — `packages-uc`; extensión **1k**).
- `packages_uc.py`: `load(root: Path) -> Iterator[RawDoc]`.
  - Descubre **dos** conjuntos, en este orden determinista:
    1. `root/packages/*/docs/aiup/use-cases/UC-*.md` — los UC. El nombre debe empezar por `UC-` y
       acabar en `.md`.
    2. `root/docs/aiup/glossaries/*.md` — un glosario plano por dominio.
  - Los nombres de carpeta (`packages`/`docs`/`aiup`/`use-cases`/`glossaries`) son la **convención fija
    de este `source_type`**, igual que `vitepress-domains` fija `<dominio>/uc/UC-*.md`. No son marca de
    ningún cliente: son la forma estructural que este tipo reconoce.
  - Orden **documentado y estable**: primero **todos** los UC (alfabético por subdirectorio de package y
    por nombre de fichero), después los glosarios (alfabético) — `sorted()` en cada nivel, como el loader
    actual. No basta con que dos pasadas coincidan: el orden concreto es parte del contrato (el `ordinal`
    de los chunks y la reproducibilidad del batch dependen de él).
  - **Solo ficheros**: una entrada que matchea el glob pero es un **directorio** (p. ej. un directorio
    llamado `UC-algo.md`) se ignora sin error — comprobación `is_file()` explícita. `Path.glob` no
    distingue (hallazgo de `scenario-coverage`).
  - **Un solo nivel**, no recursivo: un UC anidado más profundo (`use-cases/sub/UC-1.md`) no se recoge.
    El prefijo `UC-` y la extensión `.md` se comparan **respetando la caja** (el glob de Python es
    case-sensitive en las plataformas de este repo): `uc-001.md` o `UC-001.MD` no se recogen.
  - Un **glosario mal ubicado** (dentro de un package en vez de la ruta compartida) no se recoge como
    glosario: la ubicación es parte de la convención, no solo el nombre.
  - **Streaming por fichero** (generador): nunca carga la KB entera en memoria.
  - Validación **EAGER** de `root` (antes de devolver el iterador, mismo criterio y motivo que
    `loader.load`): `root` inexistente o no-directorio → `FileNotFoundError` con mensaje claro, no un
    iterador vacío silencioso.
  - Fichero illegible (permisos) o con encoding no-UTF8 → **skip + log** (`structlog`), nunca aborta el
    recorrido. Función de lectura **propia** de este módulo: no se importa la privada `_read` de
    `loader.py` (dos implementaciones independientes que solo comparten el contrato de datos).
  - **Directorio** sin permisos de lectura (`PermissionError` al listar, no al leer un fichero) →
    **skip + log** también, mismo criterio que un fichero illegible: el recorrido continúa con el resto.
    Decisión explícita de esta tarea (hallazgo de `scenario-coverage`: `loader.py` tampoco lo cubre, pero
    aquí es código nuevo y toca decidirlo, no heredar la omisión).
  - **Ausencias que no son error**: un subdirectorio de package sin directorio de casos de uso, y la
    ausencia **total** del directorio compartido de glosarios → el recorrido se completa con el resto.
  - `RawDoc.mtime` se captura aquí (`datetime.fromtimestamp(..., tz=UTC)`), no en el parser — mantiene el
    parser puro, mismo criterio que `-03` del plan `kb-ingestion`.
- Fixtures nuevas en `backend/tests/fixtures/kb_packages_uc/`: al menos un UC válido en dos
  subdirectorios de package distintos, un glosario, y un **árbol hermano con otra convención de carpeta**
  (para la extensión 1k). Cada fixture cita en comentario qué aspecto del formato real reproduce.

## Fuera de alcance

- **Parsear** el contenido (frontmatter, H1→título, alias de package, glosario) — tarea `-02`.
- `Settings.kb_source_type`/`kb_package_aliases`, el registro `sources.py`, el wiring en
  `pipeline.ingest()`/CLI y la inversión del default — tarea `-03`.
- **Modificar `loader.py`/`parser.py`** (`vitepress-domains`): quedan tal cual.
- **Parsear los wiki-links `[[UC-XXX-NNN]]` a `relacionado`**: recortado del plan (`design-review` #5) —
  el campo no se persiste ni se consume en ningún sitio.
- **Ejecutar `make ingest` contra una fuente real**: verificación manual del owner, fuera del gate.
- **Tocar el repo de documentación externo** del que se verificó el formato: solo lectura, y ni siquiera
  como dependencia de test (las fixtures son propias).
- **Ingerir contenido narrativo multi-package** (flows que cruzan packages): no es UC ni glosario.
- **Fallback al glosario compartido** cuando un dominio no tiene glosario propio: no se ingiere.

## Scenarios (Gherkin)

Fuente única (SDD): [`CU-BE-07-ingestion-de-la-kb.md`](../../../specs/backend/casos-de-uso/CU-BE-07-ingestion-de-la-kb.md).

Esta tarea cubre, a nivel **unit** (sin BD, sin puertos, fixtures `.md` en `tmp_path`), la parte de
**descubrimiento de ficheros** de estos escenarios del CU:

- `Un árbol hermano con otra convención de carpeta nunca se recoge` (extensión **1k**) — íntegro aquí.
- `El orden de descubrimiento sigue la convención documentada` — íntegro aquí.
- `Entradas que matchean el patrón pero no son documentos ingeribles` (`Scenario Outline`: directorio
  con nombre de UC, fichero sin prefijo, UC demasiado anidado, glosario mal ubicado, caja distinta) —
  íntegro aquí.
- `Ausencias en el árbol de origen no rompen el recorrido` (`Scenario Outline`) — íntegro aquí.
- `Un directorio sin permisos de lectura se salta con log` — íntegro aquí.
- `Ingesta de un UC del formato real` — parcial: solo que el fichero se descubre y se lee (el parseo de
  sus metadatos es `-02`, la persistencia `-03`).
- `El glosario del formato real se ingiere íntegro` — parcial: solo que el fichero de glosario se
  descubre (su parseo íntegro es `-02`).

> Añadido para esta tarea (comportamiento del loader, sin escenario propio en el CU — mismo patrón que
> `backend-kb-ingestion-03`):
> ```gherkin
> Scenario: El loader descubre los UC de todos los subdirectorios de package y los glosarios
>   Given un árbol con UC en dos subdirectorios de package distintos y un glosario de dominio
>   When se descubren los documentos de la KB
>   Then se devuelven los UC de ambos subdirectorios y el glosario
>
> Scenario: Una raíz inexistente falla claro en la propia llamada
>   Given una ruta raíz que no existe en disco
>   When se pide descubrir los documentos de la KB
>   Then falla de inmediato con un error claro, no con un iterador vacío silencioso
>
> Scenario: Un fichero illegible o con encoding inválido se salta con log
>   Given un fichero sin permisos de lectura, o con bytes no-UTF8
>   When se descubren los documentos de la KB
>   Then ese fichero se salta con log y el resto del recorrido se completa
>
> Scenario Outline: Fronteras del número de documentos descubiertos
>   Given un árbol con <origen>
>   When se descubren los documentos de la KB
>   Then se devuelven <esperado>
>
>   Examples:
>     | origen                                              | esperado            |
>     | ningún subdirectorio de package ni glosario         | cero documentos     |
>     | un único UC y ningún glosario                       | ese único documento |
>     | varios UC repartidos y varios glosarios             | todos ellos         |
> ```
>
> **Verificación del log**: los escenarios "se salta con log" se testean con `pytest caplog` +
> `structlog` reenviando al `logging` estándar — patrón ya establecido en el plan `kb-ingestion`
> (tareas `-03`…`-06`), no nuevo aquí.

## Provides

- `app/ingestion/packages_uc.py` con `load(root: Path) -> Iterator[RawDoc]` — lo consume `-02` (para sus
  tests de parseo con `RawDoc` reales) y `-03` (lo registra en `sources.py`).
- Fixtures `backend/tests/fixtures/kb_packages_uc/` (UC en dos packages, glosario, árbol hermano de otra
  convención) — reutilizadas por `-02` y `-03`.

## Definition of Done

- [x] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [x] Cada escenario Gherkin tiene al menos un test (camino feliz + bordes/errores)
- [x] Todos los tests en verde (`make test`), sin regresión en los 946 existentes
- [x] Spec cumplida; lo declarado en `Provides` queda disponible para `-02`/`-03`
- [x] `ruff check` + `ruff format --check` + `mypy --strict` OK
- [x] Gate de mutation testing (`cosmic-ray`, `break: 80`) sobre `packages_uc.py` — survivors
  documentados como equivalentes si quedan
- [x] Gate `/sdd-lint` superado — mecánico limpio; el semántico destapó **2 ERROR PREEXISTENTES** (no
  introducidos por esta tarea, que arrancó sin tocar spec/CU/ADR) y, **por decisión del owner, se
  corrigieron aquí**: `CU-BE-11-resumen-de-analytics.md` (nuevo, cierra `FR-041` sin CU) y `spec.md:84`
  (`FR-033` alineado con la ext. 1f de `CU-BE-07`). Los AVISO quedan reconocidos y enrutados a la `-03`.
  → La afirmación original de esta línea ("esta tarea no modifica spec/CU/ADR") **ya no es cierta**
- [x] Gate de `fact-checker` superado — 14 VERIFICADO / 1 INCORRECTO / 0 NO VERIFICABLE. El INCORRECTO es
  una afirmación mía sobre los 2 ERROR de `sdd-lint` que quedó desfasada porque los corregí **mientras**
  el verificador corría; **corregida** en el session log. Su reserva sobre la suite (22 fallos por
  "`pytest-randomly` + orden") se investigó y se **descartó**: ese plugin no está instalado
- [x] Documentación — docstrings de todo símbolo público (incluido el anti-patrón: importar la privada
  `_read` de `loader.py`, o asumir el layout `<dominio>/uc/`) + doc técnica donde aplique + session log
  en `.claude/context/backend/backend-kb-source-packages-uc-01.md`
