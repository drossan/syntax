# Session log — `backend-kb-ingestion-04` — Chunker H2 tolerante

> Append-only. Registro canónico de la tarea (task-lifecycle §Cerrar una tarea).

## 2026-08-21 — Implementación y cierre

- **TDD**: `tests/test_chunker.py` escrito antes de `chunker.py`; rojo confirmado, verde después.
  Terminó con 34 tests (crecido en varias rondas por supervivientes reales del gate de mutation,
  no solo por los escenarios iniciales).
- **Implementado**: `app/ingestion/chunker.py` (`Chunk` + `chunk(parsed, *, token_budget, encoding)
  -> list[Chunk]`); `Settings.chunk_token_budget` (`app/core/config.py`, default 800, `gt=0`) + tests
  en `test_config.py`.
- **Decisión de implementación sin precedente explícito en la tarea**: el chunker retira el bloque
  `::: info Trazabilidad` y la línea `Relacionado:` del `body` ANTES de trocear (metadatos, no
  contenido a embeber) — decisión propia, no toca el contrato de `-03` (`ParsedUC.body` sigue
  conteniéndolos; solo este módulo los filtra).
- **Bug real encontrado por TDD (no por mutation)**: primer diseño intercalaba `kb_chunk`+`embedding`
  — no aplica aquí, es de `-02`. Para ESTA tarea: el primer diseño de `_split_into_atomic_blocks`
  usaba un único bucle plano para fences; se rediseñó a un bucle interno dedicado (abrir→acumular→
  cerrar) tras notar que un fence con blancos internos rompía el split por línea-en-blanco genérico.
- **sdd-lint**: N/A — no toca spec.md/CU/ADR.

### Incidente: fiabilidad de `cosmic-ray` en esta sesión

Durante el gate de mutation de esta tarea se dieron dos problemas reales con `cosmic-ray` (recordar:
es la vía de referencia **no verificada** por el plugin `task-pipeline` — solo Stryker está
verificado; ver `mutation` skill):

1. **Un run "exitoso" (exit 0) dejó una mutación aplicada en disco** (`index += 0` en vez de
   `index += 1`, en `_split_into_atomic_blocks`) tras completar. Se detectó al inspeccionar el
   fichero por sospecha, se corrigió de inmediato, y se verificó que los ficheros ya commiteados de
   las tareas `-02`/`-03` (con survivors documentados como equivalentes en sus propios cierres) NO
   tenían ninguna mutación de ese tipo colada — sin corrupción histórica. Causa más probable:
   interrupción del proceso al forzar el paso a background de un comando que superó el timeout del
   shell, no un bug estructural de `cosmic-ray` en sí (su `LocalDistributor` es secuencial, sin
   paralelismo — se inspeccionó el código fuente instalado para confirmarlo).
2. **Dos runs consecutivos, mismo código y mismos tests, dieron tasas de supervivencia muy distintas**
   (0.72% con 1 survivor, luego 20.29% con 28 survivors) antes de estabilizarse en 5.80%/8 survivors
   tras fortalecer los tests. El primer resultado (0.72%) se descartó como no fiable (probablemente
   afectado por el mismo incidente del punto 1); los siguientes 3 runs, ya limpios, convergieron de
   forma consistente y decreciente (20.29% → 10.14% → 7.25% → 5.80%) a medida que se añadían tests,
   lo que sí es el patrón esperado y fiable.
- **Mutation testing (cosmic-ray)**, `module-path = "app/ingestion/chunker.py"`: iterado de 20.29%
  (28 survivors, primer run limpio) a 5.80% (8 survivors) en 4 rondas. Supervivientes reales
  corregidos con tests nuevos: `*`→`>=`/`>`/etc. en varias comparaciones de índice y presupuesto;
  `if current:`→`if not current:` al arrancar un fence; `frozen=True`→`False` en `Chunk`;
  `continue`→`break` en dos bucles distintos; avance de `index` +2 en vez de +1 tras cerrar un fence;
  reset de `current_tokens` a `1`/`-1` en vez de `0` en dos sitios (cada uno necesitó un test POR
  DIRECCIÓN, ya que un baseline erróneo por encima y por debajo de 0 rompen decisiones de
  merge/split en sentidos opuestos); comparación de índice `<` mutada a `is not` en el bucle externo
  y en el bucle del fence — killed con secciones de **> 256 líneas** (fuera del rango de enteros
  cacheados de CPython, -5..256 — mismo patrón que en la tarea `-01`), incluyendo el caso "fence sin
  cierre" (que sí ejercita `index == len(lines)`) frente al caso "fence cerrado" (que no lo hace,
  para antes al encontrar la marca de cierre).
  Supervivientes finales (8), **todos equivalentes**: 2× el `*` keyword-only de las firmas de
  `chunk`/`_chunk_glosario`; 2× `line.strip() == ""` mutado a `<=`/`is` (equivalente: `""` es el
  mínimo lexicográfico, y CPython garantiza que la cadena vacía es un singleton); 3× `index <
  len(lines)` mutado a `!=` (equivalente: `index` solo se incrementa de 1 en 1, nunca puede saltarse
  el límite — a diferencia de `is not`, que sí se pudo matar con inputs > 256); 1× `.group(1)` vs
  `.group(0)` al extraer un título H2 (equivalente: `_slugify` recorta cualquier `##`/espacio
  inicial, el resultado final es idéntico).
- **fact-checker** (subagente independiente, agentId `ac0b3f8d0d7c744c0`): 9/9 VERIFICADO, 0
  INCORRECTO. Re-ejecutó él mismo el gate de mutation desde cero (5.80%, mismos 8 survivors) y
  verificó EXPLÍCITAMENTE que el fichero no quedó con ninguna mutación a medias tras su propia
  ejecución (se le pidió por el incidente del punto 1).
- **DoD**: todos los checkboxes cumplidos. Sin pendientes.
- Excluido de este commit: `backend/docs/domain-services-explicado.md` (cambio no relacionado, de una
  sesión anterior, sigue sin commitear).
