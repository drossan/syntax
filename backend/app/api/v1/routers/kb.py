"""app.api.v1.routers.kb — búsqueda y documentos de KB (contrato 06).

GUIÓN (→ tarea 11)
------------------
Endpoints (capacidad ``kb.read``; delegan en el retriever de 14):
  - ``GET /kb/search`` (``q`` + filtros ``domain/package/estado``; orden por ``score``; citas).
  - ``GET /kb/documents`` (lista con filtros), ``GET /kb/documents/{uc_id}`` (por clave única).

KB es **global** (sin RLS de tenant); ``kb.read`` la protege. Anti-patrón: SQL crudo en el router
(delegar en el puerto vector/retriever 14).
"""
