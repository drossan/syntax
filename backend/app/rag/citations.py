"""app.rag.citations — construcción de citas de las fuentes.

GUIÓN (→ tarea 14; spec 04)
---------------------------
Qué implementar:
  - A partir de los hits usados en la respuesta, construir citas: ``uc_id``, ``title``, ``section_type``
    (+ ``source_url`` derivado, ``score``). Deduplicar por ``uc_id``/sección.
  - Formato consumido por: ``AgentRun.sources`` (03, JSONB), la respuesta del agente y el frontend
    (``Citation`` del contrato 06).

Anti-patrón: citar sin ``uc_id`` (no trazable); inventar fuentes no recuperadas.
"""
