"""app.ingestion.chunker — troceo por sección H2 TOLERANTE.

GUIÓN (→ tarea 13; spec 04)
---------------------------
Qué implementar:
  - Partir cada UC por sus **H2**, **sin asumir estructura fija**: H2 casi-uniformes pero **no
    universales** (verificado: `Comportamiento`/`Fidelidad` en los 268; `Conceptos` solo 257; etc.).
    **Tolerar H2 ausentes** (no falla, no rellena) y **renombrados/sueltos** (normalizar a ``section_type``:
    slug del título; variantes conocidas → sección base, p.ej. `Reglas e invariantes*` → ``reglas``).
  - **No partir tablas** ni bloques de código; contenido antes del 1er H2 → ``section_type=intro``.
  - Sección que excede el presupuesto de tokens → sub-partir por párrafos/listas preservando ``ordinal`` y
    heredando ``section_type``.
  - **Metadatos por chunk (5 facetas)**: ``uc_id``, ``domain`` (17), ``package`` (5), ``estado``,
    ``section_type``.

Anti-patrón: asumir las 5 secciones fijas; cortar una tabla a mitad.
"""
