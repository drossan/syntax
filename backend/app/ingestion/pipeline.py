"""app.ingestion.pipeline — orquesta loader→parser→chunker→embedder→upsert.

GUIÓN (→ tarea 13; spec 04)
---------------------------
Qué implementar:
  - ``ingest(path)``: encadena loader → parser → chunker → embedder → **upsert idempotente por ``uc_id``**
    (puerto vector, ``app.infra.vector``): re-ingerir no duplica; refleja cambios.
  - **Reconciliación** de docs retirados: diff del set de ``uc_id`` presentes vs BD → borrar/tombstone de
    ``KBDocument``/``KBChunk``/``Embedding`` huérfanos (cascada 03 §7), no solo-upsert.
  - Reporte final: nº docs procesados/actualizados/omitidos + errores (skip/fail del parser).

Aterriza en ``KBDocument``/``KBChunk``/``Embedding`` (03). Anti-patrón: solo-upsert sin reconciliar;
ingesta no idempotente.
"""
