"""app.ingestion.cli — interfaz de línea de comandos de la ingestión.

GUIÓN (→ tarea 13)
------------------
Qué implementar:
  - Parseo de args (ruta de la KB, ``--dry-run``, ``--only <dominio>``, ``--reconcile``).
  - Construye settings + puertos (embeddings 09, vector 08/infra) e invoca ``pipeline.ingest(...)``.
  - Salida legible + código de salida ≠0 si el batch falla (p.ej. ``uc_id`` duplicado).

Lo invoca ``app/ingestion/__main__.py`` (``python -m app.ingestion`` / ``make ingest``).
Anti-patrón: crear clientes/credenciales en import; lógica de negocio aquí (delega en ``pipeline``).
"""
