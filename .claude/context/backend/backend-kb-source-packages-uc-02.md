# Session log — `backend-kb-source-packages-uc-02` — Parser `packages_uc`

> Append-only. Registro canónico de la tarea (task-lifecycle §Cerrar una tarea).

## 2026-08-24 — Arranque

- **Gate TDD comprobado**: rama `plan/backend/kb-source-packages-uc`; `depends_on:
  [backend-kb-source-packages-uc-01]` → **done** (movida a `completed/`, commit `6b38e8a`); única tarea
  `active` del plan.
- **Leído en esta sesión**: el task file entero, `app/ingestion/parser.py` completo (contrato
  `ParsedUC`/`ParseError`/`GLOSARIO_UC_ID_PREFIX` que se reutiliza sin tocar) y el criterio de fences de
  `app/ingestion/chunker.py` (`_FENCE_MARKER_RE = ^\s*```` ` ```` + toggle `in_fence` en
  `_split_sections`), que es lo que la tarea manda leer antes de reimplementar la detección de bloques de
  código para la extracción del H1.
- **Plan de ejecución**: tests rojos (`tests/test_packages_uc_parser.py`) → `parse()` en
  `app/ingestion/packages_uc.py` → cierre (make test, ruff, mypy --strict, cosmic-ray break:80 sobre
  `packages_uc.py`, `/sdd-lint`, `fact-checker`).

## 2026-08-24 — Implementación y cierre

- **TDD**: `tests/test_packages_uc_parser.py` (47 tests) escrito ANTES; rojo confirmado
  (`ImportError: cannot import name 'parse' from 'app.ingestion.packages_uc'`), verde después.
- **Implementado**: `parse(raw, *, kb_root, package_aliases) -> ParsedUC | ParseError` en
  `packages_uc.py`. `parser.py`/`loader.py` **no se tocan** (verificado por `git diff HEAD --stat`).
- **Decisiones de implementación**:
  1. **Discriminador glosario/UC = nombre exacto del directorio padre** (`glossaries`), no el nombre del
     fichero: la ubicación es parte de la convención del tipo de fuente. Un documento en cualquier otro
     directorio se parsea como UC (y falla limpio si su ruta no tiene el segmento de package).
  2. **`_first_h1()` con máquina de estados de fences**, no un regex multilínea: el criterio es el mismo
     que `chunker._split_sections` (`^\s*```` ` ```` + toggle `in_fence`), que la tarea manda leer antes
     de reimplementar. Un fence sin cerrar se traga el resto del documento → sin H1 → malformado (1i),
     que es preferible a un título falso sacado de un comentario de shell.
  3. **`relative_to(kb_root)` protegido**: una ruta que no cuelga de `kb_root` daría `ValueError`; se
     convierte en skip limpio, mismo criterio que los otros tres casos de ruta inválida.
  4. **Título del glosario = su propio H1**, con fallback al sintético `Glosario — <dominio>` si no lo
     tiene (p. ej. un fichero vacío). **Decisión sin precedente en la spec**: el task file no fija el
     `title` del glosario, y `parser._parse_index` solo tiene el sintético porque su `index.md` no
     garantiza H1. El H1 real es más fiel para las citas del retriever.
  5. **`traza` de un escalar no textual** (`traza: 42`) → `["42"]`, coherente con la coerción ya decidida
     por `scenario-coverage` para los elementos de una lista.
- **Tests**: `pytest tests/test_packages_uc_parser.py` → 47 passed. Suite completa → **1023 passed**
  (976 + 47), sin regresión.
- **ruff + `mypy app` (strict)**: limpios.
- **Mutation testing (cosmic-ray)** sobre `packages_uc.py`, con `test-command` apuntando ya a los **dos**
  ficheros de test: primera pasada **5.31%** (12/226) → analizados uno a uno, **4 supervivientes reales**
  matados con 3 tests nuevos:
  - `+ 1` → `| 1` / `^ 1` en `parts.index(_PACKAGES_DIR) + 1`: sobrevivían porque en todos los tests
    `packages` estaba en el índice 0 (`0|1 == 0^1 == 0+1`). Test nuevo con el segmento **anidado**
    (`sub/packages/vendor-core/...`).
  - `>=` → `>` / `is` en `package_index >= len(parts)`: sobrevivían porque ningún test tenía una ruta que
    **acabara** en `packages`. Test nuevo con esa frontera degenerada (mata `>`; `is` cae con él).
  - `==` → `<=` en el discriminador de glosario: sobrevivía porque todos los UC del test colgaban de
    `use-cases`, que ordena **después** de `glossaries`. Test nuevo con un directorio (`casos`) que
    ordena antes.
  - Segunda pasada: **3.54% (8/226)**. Los 8 restantes, clasificados y verificados por el `fact-checker`:
    3× el marcador `*` de keyword-only mutado a `/` (artefacto de la herramienta sobre sintaxis que no es
    un operador; ningún llamante pasa `raw` por keyword); `>=`→`==` (**equivalente**: `package_index` no
    puede exceder `len(parts)`); `>=`→`is` y `==`→`is` (funcionan por el caché de enteros pequeños y el
    interning de literales de CPython — **no** estrictamente equivalentes, pero indistinguibles para
    cualquier entrada real, y matarlos exigiría un test que dependa de detalles internos del intérprete);
    2× `count=1`→`2`/`0` en un `re.sub` con patrón anclado `\A` (**equivalentes**: solo puede haber una
    coincidencia).
- **Gate `/sdd-lint`**: mecánico limpio. Semántico acotado a lo que había cambiado desde la auditoría
  completa de la `-01` (`CU-BE-11` nuevo + `FR-033`/`FR-041` de `spec.md`), con un subagente fresco:
  **ningún ERROR**, 3 AVISO. Dos eran de `CU-BE-11` y se **corrigieron aquí** (artefacto propio): falta
  de la fila de frontera estricta del SLA en su `Scenario Outline`, y RN-1 sin fijar qué pasa si el
  sujeto tiene la capacidad en **ambos** ámbitos (gana `global`, verificado en `deps.py`/`analytics.py`).
  El tercero (la ext. **1b** de `CU-BE-07` sigue diciendo "el par" como caso general, contra FR-033, la
  1f y el código) ya estaba **enrutado a la `-03`** desde la `-01`.
- **Gate `fact-checker`** (subagente fresco, `model: sonnet`): **14 VERIFICADO / 0 INCORRECTO / 0 NO
  VERIFICABLE**. Re-ejecutó él mismo la suite (1023 passed), ruff/mypy y el ciclo completo de cosmic-ray
  (3.54%, mismos 8 survivors), y validó uno a uno el razonamiento de equivalencia de cada superviviente.
  Se le avisó explícitamente de **no solapar pytest con `cosmic-ray exec`** (que muta el fichero en
  disco) — la causa de los 22 fallos en falso del `fact-checker` de la `-01`.
- **Docs (3 capas)**: docstrings de `parse` y de todos los helpers, con los tres anti-patrones nuevos
  (`yaml.load` sin `safe_`, importar los privados de `parser.py`, replicar el log
  `kb_package_discrepancia` que en este formato no puede darse); doc técnica → el docstring de módulo de
  `packages_uc.py` describe ya el par `(load, parse)` completo; histórico → este log.
- **Ficheros**: `app/ingestion/packages_uc.py` (M), `tests/test_packages_uc_parser.py` (nuevo),
  `cosmic-ray.toml` (M, `test-command` con los dos ficheros de test),
  `.claude/specs/backend/casos-de-uso/CU-BE-11-resumen-de-analytics.md` (M, dos AVISO de `sdd-lint`).
- **Tiempo real**: ~2.5h (estimado 4h).
- **Follow-ups**: ninguno propio. Los AVISO enrutados a la `-03` ya están escritos en su `## Spec`.
