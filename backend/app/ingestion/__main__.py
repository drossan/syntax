"""app.ingestion.__main__ — entry-point del comando ``python -m app.ingestion``.

GUIÓN (→ tarea 13)
------------------
Es el objetivo de ``make ingest`` (Makefile: ``$(PY) -m app.ingestion``). Debe delegar en
``app.ingestion.cli`` (p.ej. ``from app.ingestion.cli import main; raise SystemExit(main())`` bajo
``if __name__ == "__main__":``). Sin lógica propia.

Anti-patrón: duplicar el parseo de args aquí; ejecutar la ingesta a nivel de import.
"""
