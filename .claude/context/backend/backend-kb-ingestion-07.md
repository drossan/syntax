# Session log — `backend-kb-ingestion-07` — CLI + entry-point (`make ingest`)

> Append-only. Registro canónico de la tarea (task-lifecycle §Cerrar una tarea).

## 2026-08-22 — Implementación y cierre

- **TDD**: `tests/test_cli.py` escrito antes de `cli.py`; rojo confirmado, verde después.
- **Implementado**: `main(argv) -> int` + `_run()`/`_build_parser()`/`_format_report()` en
  `app/ingestion/cli.py`; `app/ingestion/__main__.py` real (delega en `cli.main()`);
  `Settings.kb_source_path` (default `""`) en `app/core/config.py`.
- **Extensión necesaria de `-06`**: `pipeline.ingest()` no soportaba `--dry-run`/`--only`/
  `--reconcile` (la tarea `-06` no los contemplaba). Se extendió su firma con
  `only_domain: str | None = None`, `dry_run: bool = False`, `force_reconcile: bool = False` — los
  tres con default que preserva el comportamiento original de `-06` byte a byte (verificado: los 18
  tests de `-06` siguen en verde sin cambios). Reinterpretación de `--reconcile`: el Gherkin de la
  tarea lo describe con un batch que YA reconcilia sin el flag (caso ya cubierto por el flujo
  normal); la lectura con sentido real es que fuerza la reconciliación en el caso "origen vacío/todo
  malformado", donde `-06` decidió deliberadamente NO tocar la BD (CU-BE-07 4b) — `--reconcile` es la
  vía explícita del operador para anular esa cautela cuando sabe que el vaciado es real.
- **Estrategia de test de la CLI (decisión de esta tarea)**: se mockean `ingest`/`get_embedding_model`
  (nombres importados en `cli.py`) para probar parseo de argumentos/mapeo de código de salida sin
  Postgres real ni red — la lógica de negocio ya la cubre `-06`. Se añadió además UN test end-to-end
  genuino (sin mocks de `ingest`, contra Postgres real vía `migrated_database`) para verificar el
  cableado completo `main→_run→pipeline.ingest→SqlAlchemyKBIndexWriter`. Ese test es una función
  SÍNCRONA a propósito: `cli.main()` gestiona su propio `asyncio.run()`, y llamarlo desde un test
  `async def` (con un event loop ya activo por pytest-asyncio) rompe con "asyncio.run() cannot be
  called from a running event loop".
- **`Settings.kb_source_path`**: vacío por defecto (sin fuente real en esta máquina); la CLI exige que
  el argumento posicional o este campo estén fijados, o falla claro con código 2.
- **sdd-lint**: N/A — no toca spec.md/CU/ADR.
- **Documentación fuera de alcance, anotada**: `IMPLEMENTATION-GUIDE.md`/`README.md` describen el
  backend como "esqueleto doc-only, sin código de negocio" — ya desactualizado por los planes previos
  (`domain-services`, `routers-core`, `routers-flujo-ia`, y ahora `kb-ingestion`), no algo que esta
  tarea concreta haya provocado. Corregir esa narrativa completa excede el alcance de "CLI +
  entry-point"; se deja anotado para una tarea de documentación aparte, no se toca aquí.
- **Mutation testing (cosmic-ray)**: dos módulos, porque esta tarea tocó ambos.
  - `cli.py` (nuevo): 19.15% supervivencia inicial (9/47) → 8.51% final (4/47) tras añadir tests para
    el `commit()` condicional (con una sesión falsa, ya que mockear `ingest()` entero no genera
    actividad real de sesión que distinga las ramas) y para la red de seguridad `except Exception`.
    Supervivientes finales, equivalentes/aceptados: 1× el `*` keyword-only de `_format_report`; 1×
    `expire_on_commit=False`→`True` (no observable sin una sesión ORM real accediendo a atributos
    tras un commit — cubierto en profundidad por `-02`/`-06`, no vale la pena replicar esa
    infraestructura aquí); 2× el fallback `2` de `exc.code if isinstance(exc.code, int) else 2`
    (rama inalcanzable en la práctica — `argparse` siempre da un código entero real, nunca lanza con
    un `code` no-entero).
  - `pipeline.py` (extendido): re-verificado tras los cambios de esta tarea — 3.55% supervivencia
    (5/141), corregido un `continue`→`break` real en el filtro `only_domain` (test con el dominio NO
    coincidente ordenado ANTES que el coincidente). Los 5 supervivientes finales son equivalentes,
    mismo patrón que en `-06` (keyword-only `*` ×2, `len(docs) > 1` vs `!= 1`, `docs[0]` vs `docs[-1]`)
    más uno nuevo: el default `dry_run: bool = False` de `_diff_and_embed` mutado a `True` — equivalente
    porque TODAS las llamadas reales pasan `dry_run=dry_run` explícito, el default nunca se usa.
- **fact-checker** (subagente independiente, agentId `ab53f4c0386987f12`): 10/10 VERIFICADO, 0
  INCORRECTO. Re-ejecutó ambos gates de mutation desde cero (mismos resultados exactos) y confirmó que
  ninguno de los dos ficheros quedó corrupto tras el proceso.
- **DoD**: todos los checkboxes cumplidos. Sin pendientes.
- Excluido de este commit: `backend/docs/domain-services-explicado.md` (cambio no relacionado, de una
  sesión anterior, sigue sin commitear — arrastrado sin tocar durante las 7 tareas de este plan).

## Cierre del plan `kb-ingestion`

Las 7 tareas están completadas. El plan implementa CU-BE-07 (ingestión de la KB) end-to-end: loader →
parser → chunker → diff → embedder → `KBIndexWriter` (pgvector real) → CLI (`make ingest`). Pendiente
explícito, ya documentado como fuera de alcance en el propio plan: ejecutar contra la KB real (no
existe en esta máquina — verificación manual del owner cuando la tenga disponible) y el retriever real
(tarea 14, plan propio). El plan se mueve a `.claude/plans/completed/backend/kb-ingestion.md`.
