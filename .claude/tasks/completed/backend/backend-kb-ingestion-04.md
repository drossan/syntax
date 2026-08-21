---
id: backend-kb-ingestion-04
package: backend
plan: kb-ingestion
status: completed
priority: 2
depends_on: [backend-kb-ingestion-03]
estimate: 3h
actual: 5h
created: 2026-08-21
updated: 2026-08-21
---

# Chunker H2 tolerante

## Description

`app/ingestion/chunker.py` es GUIÓN puro. Parte cada UC ya parseado (`-03`) por sus encabezados **H2**,
**sin asumir estructura fija**: H2 casi-uniformes pero no universales (verificado contra la KB real:
`Comportamiento`/`Fidelidad` en los 268 UC; `Conceptos` falta en 11); tolera H2 ausentes (no falla, no
rellena) y renombrados/sueltos (normaliza a `section_type` = slug del título; variantes conocidas →
sección base, p.ej. cualquier `Reglas e invariantes*` → `reglas`). No parte tablas ni bloques de código a
mitad. Contenido antes del primer H2 → `section_type=intro`. Sección que excede el presupuesto de tokens
→ sub-partición por párrafos/listas, preservando `ordinal` y heredando `section_type`.

**Presupuesto de tokens** (hallazgo de `scenario-coverage`: no existía ningún valor ni tokenizador
fijado en spec/código): nuevo `Settings.chunk_token_budget` (elige aquí un default sensato, p.ej. 800 —
documentarlo en `rag-ingestion.md` §3) + conteo con `tiktoken` (ya en `requirements.txt`), encoding del
modelo de embeddings (`settings.embedding_model`).

## Spec

- `.claude/specs/backend/rag-ingestion.md` §3.
- `core/config.py`: añade `chunk_token_budget: int = Field(default=..., gt=0)` a `Settings`.
- `chunker.py`: `chunk(parsed: ParsedUC) -> list[Chunk]` (`Chunk = {content, section_type, token_count,
  ordinal}`, metadatos `uc_id/domain/package/estado` heredados del documento).
  - H2 ausente: no falla, no rellena — simplemente no hay chunk de esa sección.
  - H2 renombrado/variante: normaliza al `section_type` base (tabla de variantes conocidas, ver
    `rag-ingestion.md` §3).
  - Tabla o bloque de código: nunca se corta a mitad, aunque la sección exceda el presupuesto — el
    corte por presupuesto solo ocurre en párrafos/listas.
  - Un párrafo único (sin separadores naturales) que por sí solo excede el presupuesto **no se parte a
    mitad de frase**: queda como un único chunk por encima del presupuesto (con log de aviso).
  - Un bloque de código sin cierre (fence sin su par en el resto del fichero) se trata como cerrado al
    final del documento — nunca "traga" el resto del fichero como si fuera código.
  - `index.md` (Glosario): un solo chunk `section_type=glosario` con el bloque completo (ya filtrado por
    el parser en `-03`); un `index.md` sin Glosario (ya resuelto en `-03` como `ParsedUC` sin secciones)
    produce `chunk(parsed) == []`.

## Fuera de alcance

- Parseo de frontmatter/Trazabilidad — tarea `-03` (ya completada, consumida aquí).
- Embeddings — tarea `-05`.
- Persistencia — tarea `-06`.

## Scenarios (Gherkin)

Fuente única (SDD): `CU-BE-07-ingestion-de-la-kb.md`. Esta tarea cubre la parte de chunking de `Ingesta
de un UC válido`. El detalle de tolerancia H2 es de `rag-ingestion.md` §3 (sin escenario propio en el
CU), así que se añade aquí:

```gherkin
Feature: Chunking H2 tolerante

  Scenario: Un UC con las secciones H2 estándar produce un chunk por sección
    Given un UC parseado con Comportamiento/Fidelidad/Reglas e invariantes/Conceptos
    When se chunkea
    Then hay un chunk por sección, con su section_type y ordinal correctos

  Scenario Outline: Tolerancia a variaciones de H2
    Given un UC parseado con <variacion>
    When se chunkea
    Then <resultado>

    Examples:
      | variacion                                              | resultado                                        |
      | sección Conceptos ausente                              | no hay chunk de esa sección; el resto se chunkea |
      | "Reglas e invariantes (draft — comportamiento esperado)"| se normaliza a section_type=reglas               |
      | contenido antes del primer H2                          | ese contenido es un chunk con section_type=intro |

  Scenario: Una sección con una tabla que excede el presupuesto de tokens no se parte a mitad
    Given una sección H2 con una tabla markdown grande, por encima del presupuesto de tokens
    When se chunkea
    Then la tabla completa queda en un único chunk (o el chunk que la contiene no la corta a mitad)

  Scenario: Una sección de texto largo sin tabla se sub-parte preservando el orden
    Given una sección H2 de solo párrafos/listas que excede el presupuesto de tokens
    When se chunkea
    Then se generan varios chunks con el mismo section_type y ordinal creciente, sin huecos

  Scenario: Un documento sin ningún H2 y sin contenido intro produce lista vacía
    Given un ParsedUC cuyo cuerpo está vacío tras el frontmatter
    When se chunkea
    Then chunk(parsed) devuelve []

  Scenario Outline: Frontera exacta del presupuesto de tokens
    Given una sección de tamaño <tokens>
    When se chunkea
    Then <resultado>

    Examples:
      | tokens         | resultado                                |
      | budget - 1     | un solo chunk                            |
      | budget         | un solo chunk (límite inclusive)         |
      | budget + 1     | se sub-particiona                        |

  Scenario: Un párrafo único que por sí solo excede el presupuesto no se parte a mitad de frase
    Given una sección de un solo párrafo sin separadores naturales, por encima del presupuesto
    When se chunkea
    Then queda como un único chunk por encima del presupuesto, con un log de aviso

  Scenario: Un bloque de código sin cierre no traga el resto del documento
    Given una sección con un fence de código abierto sin su cierre en el resto del fichero
    When se chunkea
    Then el fence se trata como cerrado al final del documento; el resto de secciones se chunkea con normalidad
```

## Provides

- `chunk(parsed) -> list[Chunk]` en `ingestion/chunker.py`.
- `Settings.chunk_token_budget`.
- Consumido por `-05` (embedder) y `-06` (pipeline).

## Definition of Done

- [x] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [x] Cada escenario tiene al menos un test (camino feliz + bordes/errores)
- [x] Todos los tests en verde (`make test`) — 879 passed
- [x] Spec cumplida; `Provides` disponible para `-05`/`-06`
- [x] `ruff check` + `ruff format --check` + `mypy` strict OK
- [x] Gate de mutation `cosmic-ray` (`break: 80`, referencia no verificada) sobre `chunker.py` — 5.80%
  supervivencia (8/138, los 8 documentados como equivalentes)
- [x] Gate `/sdd-lint` — N/A esta tarea: no toca spec.md/CU/ADR
- [x] Gate de `fact-checker` superado (INCORRECTO bloquea) — 9/9 VERIFICADO
- [x] Documentación — docstring de la tabla de normalización de `section_type` + anti-patrones (asumir
  las 5 secciones fijas, cortar una tabla a mitad) + session log
