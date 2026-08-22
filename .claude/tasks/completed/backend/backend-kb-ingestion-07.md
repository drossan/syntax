---
id: backend-kb-ingestion-07
package: backend
plan: kb-ingestion
status: completed
priority: 2
depends_on: [backend-kb-ingestion-06]
estimate: 2.5h
actual: 4h
created: 2026-08-21
updated: 2026-08-21
---

# CLI + entry-point (`make ingest`)

## Description

`app/ingestion/cli.py` es GUIÓN puro; `__main__.py` dice ya delegar en `cli.main()` (verificar si hace
falta tocarlo o solo confirmarlo). La CLI parsea argumentos, construye `settings` + los puertos reales
(`get_embedding_model()` de `-01`, el adaptador `KBIndexWriter` de `-02`) e invoca `pipeline.ingest(...)`
(`-06`). Sin lógica de negocio propia — toda vive en `pipeline`.

## Spec

- `.claude/specs/backend/rag-ingestion.md`.
- `cli.py`: `def main(argv: list[str] | None = None) -> int`.
  - Args: ruta de la KB (posicional u opción, default de `settings`/config), `--dry-run` (corre
    loader→parser→chunker→diff contra `KBIndexWriter` sin llamar a `upsert_document`/
    `delete_by_uc_ids`/al embedder; informa qué haría — cuántos documentos se darían de alta/
    actualizarían/reconciliarían), `--only <dominio>` (filtra el loader a un dominio), `--reconcile`
    (fuerza el paso de reconciliación incluso si no hubo altas).
  - Construye `settings = get_settings()`, `model = get_embedding_model(settings)`, `writer =
    <adaptador real de -02>`, invoca `pipeline.ingest(path, writer=writer, model=model)`.
  - **Códigos de salida distintos** (decisión de `scenario-coverage`): `0` éxito; `2` error de uso
    (args malformados, p.ej. ruta ausente sin default); `1` fallo de negocio del pipeline (`uc_id`
    duplicado, fallo real a mitad de batch, lock de ingestión no disponible). Salida legible con el
    resumen del `IngestReport` en el caso de éxito o fallo de negocio.
- `__main__.py`: confirma que delega en `cli.main()` bajo `if __name__ == "__main__":`, sin lógica
  propia; ajusta solo si el guión actual no lo hace ya correctamente.

## Fuera de alcance

- La lógica de ingestión en sí — tarea `-06` (ya completada, consumida aquí).
- Ejecutar contra la KB real — no existe en esta máquina.

## Scenarios (Gherkin)

Fuente única (SDD): `CU-BE-07-ingestion-de-la-kb.md`. La CLI es la interfaz de "operador que ejecuta la
ingestión (`make ingest`)" (actor primario del CU) — cubre el disparador del CU, no un escenario de
negocio propio (esos ya los cubre `-06`):

```gherkin
Feature: CLI de ingestión

  Scenario: Ejecución exitosa devuelve código de salida 0
    Given un pipeline que completa sin uc_id duplicados
    When se ejecuta main(argv) con la ruta de la KB
    Then el proceso termina con código de salida 0 y un resumen legible

  Scenario: Un fallo de negocio devuelve código de salida 1
    Given un pipeline que detecta un uc_id duplicado
    When se ejecuta main(argv)
    Then el proceso termina con código de salida 1, reportando el par en conflicto

  Scenario: Un error de uso devuelve código de salida 2, distinto del de negocio
    Given argumentos de CLI malformados (p.ej. ruta ausente sin default configurado)
    When se ejecuta main(argv)
    Then el proceso termina con código de salida 2, y el pipeline no se invoca

  Scenario: --only filtra el loader a un solo dominio
    Given una KB con varios dominios
    When se ejecuta main(argv) con --only <dominio>
    Then solo se procesan los UC de ese dominio

  Scenario: --only con un dominio válido pero sin ningún documento
    Given una KB donde ningún UC pertenece a <dominio>
    When se ejecuta main(argv) con --only <dominio>
    Then éxito (código 0) con 0 documentos procesados

  Scenario: --dry-run no persiste nada e informa qué haría
    Given un pipeline con documentos válidos (altas y actualizaciones)
    When se ejecuta main(argv) con --dry-run
    Then no se llama a upsert_document/delete_by_uc_ids/embed_documents, y se informa el resumen de lo
      que se haría

  Scenario: --reconcile fuerza la reconciliación aunque no haya altas
    Given un batch sin documentos nuevos/cambiados pero con un uc_id retirado del origen
    When se ejecuta main(argv) con --reconcile
    Then el documento retirado se elimina igualmente

  Scenario: Fallo al construir los puertos antes de invocar el pipeline
    Given settings con openai_api_key vacía, o embedding_dim desalineado (fail-fast de -01), o BD
      inalcanzable
    When se ejecuta main(argv)
    Then se informa un error claro con código de salida 1, sin traza cruda

  Scenario: Ruta de KB inexistente en disco
    Given una ruta que no existe
    When se ejecuta main(argv) con esa ruta
    Then error de uso claro, código de salida 2, pipeline no invocado
```

## Provides

- `main(argv) -> int` en `ingestion/cli.py`; `python -m app.ingestion` / `make ingest` operativos
  end-to-end (con fixtures o una ruta real si el owner la aporta).

## Definition of Done

- [x] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [x] Cada escenario tiene al menos un test (camino feliz + bordes/errores)
- [x] Todos los tests en verde (`make test`) — 946 passed
- [x] Spec cumplida; `make ingest` cableado end-to-end (Makefile ya lo tenía, sin cambios necesarios)
- [x] `ruff check` + `ruff format --check` + `mypy` strict OK
- [x] Gate de mutation `cosmic-ray` (`break: 80`, referencia no verificada) sobre `cli.py` (8.51%,
  4/47 equivalentes/aceptados) y re-verificado sobre `pipeline.py` extendido (3.55%, 5/141 equivalentes)
- [x] Gate `/sdd-lint` — N/A esta tarea: no toca spec.md/CU/ADR
- [x] Gate de `fact-checker` superado (INCORRECTO bloquea) — 10/10 VERIFICADO
- [x] Documentación — docstring de las flags de la CLI + `IMPLEMENTATION-GUIDE.md`/`README.md`
  revisados (su narrativa "esqueleto doc-only" ya estaba desactualizada por planes previos, fuera de
  alcance de esta tarea arreglarla del todo — anotado, no corregido) + session log + **cierre del
  plan** (última tarea)
