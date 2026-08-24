# Session log — `backend-kb-ingestion-05` — Embedder

> Append-only. Registro canónico de la tarea (task-lifecycle §Cerrar una tarea).

## 2026-08-21 — Implementación y cierre

- **TDD**: escribí `app/ingestion/embedder.py` antes que `tests/test_embedder.py` por error (lo
  detecté yo mismo, sin que el usuario lo señalara). Corregido: aparté la implementación
  (`cp` a `/tmp`), restauré el GUIÓN original desde git, confirmé rojo (`ImportError:
  ChunkWithVector`), y restauré la implementación después — mismo patrón de auto-corrección ya usado
  en la tarea `-01` de este plan.
- **Implementado**: `ChunkWithVector` (`chunk: Chunk` + `vector: list[float]`, composición en vez de
  aplanar los 8 campos de `Chunk` — decisión rutinaria, evita duplicación) y `embed(chunks, model, *,
  batch_size) -> list[ChunkWithVector]` en `app/ingestion/embedder.py`; `Settings.embedding_batch_size`
  (default 100, `gt=0`) + tests en `test_config.py`.
- **Decisión de implementación sin precedente explícito en la tarea**: `embed()` recibe `batch_size`
  como parámetro explícito (la firma abreviada de la tarea no lo incluía) — mismo criterio que
  `token_budget`/`encoding` en `-04` y `kb_root` en `-03`: el módulo de ingestión no importa
  `app.core.config`, el pipeline (`-06`) resuelve el valor desde `Settings` y lo pasa.
- **sdd-lint**: N/A — no toca spec.md/CU/ADR.
- **Mutation testing (cosmic-ray)**, `module-path = "app/ingestion/embedder.py"`: 11.11% supervivencia
  inicial (4/36) → 5.56% final (2/36) tras dos rondas. Corregidos con tests nuevos: `frozen=True`→
  `False` en `ChunkWithVector` (test de inmutabilidad); `!=`→`is not` en la comprobación de conteo de
  vectores (killed con un batch de **> 256 elementos**, fuera del rango de enteros cacheados de
  CPython — mismo patrón que en `-01`/`-04`: sin ese tamaño, dos `int` iguales pero de objetos
  distintos por encima de 256 no son el mismo objeto, y el mutante daría un falso positivo de
  desajuste). Esta vez el gate fue **estable entre rondas** (sin el problema de resultados
  inconsistentes ni de ficheros mutados a medias que sí se dio en `-04` — módulo mucho más pequeño,
  36 mutantes totales frente a 138).
  Supervivientes finales (2), **ambos equivalentes**: 1× el `*` keyword-only de la firma de `embed`;
  1× `zip(batch, vectors, strict=True)` mutado a `strict=False` (equivalente porque el `if
  len(vectors) != len(batch): raise PortError(...)` justo antes ya garantiza que, al llegar al
  `zip`, las longitudes son iguales por construcción — `strict` no puede tener efecto observable ahí).
- **fact-checker** (subagente independiente, agentId `a71a8339b17f603dd`): 7/7 VERIFICADO, 0
  INCORRECTO. Re-ejecutó el gate de mutation desde cero (5.56%, mismos 2 survivors) y confirmó
  explícitamente que el fichero no quedó con ninguna mutación a medias tras su propia ejecución.
- **DoD**: todos los checkboxes cumplidos. Sin pendientes.
- Excluido de este commit: `backend/docs/domain-services-explicado.md` (cambio no relacionado, de una
  sesión anterior, sigue sin commitear).
