"""app.ingestion.parser — frontmatter + Trazabilidad + glosario.

GUIÓN (→ tarea 13; spec 04)
---------------------------
Qué implementar:
  - **Frontmatter** YAML: ``title``, ``domain``, ``package``, ``uc`` (NO hay ``url`` → ``source_url`` se
    **deriva** de la ruta).
  - Bloque **``::: info Trazabilidad``**: ``Estado`` (``draft``/``active``), ``Package``, ``Traza`` (rutas
    de código). **Precedencia ``package``**: gana el frontmatter; **log** si difiere de Trazabilidad.
  - Línea **``Relacionado:``** → grafo de relacionados (metadato opcional).
  - **``index.md``**: extraer solo ``## Glosario`` (``section_type=glosario``); ``## Casos de uso`` /
    ``## Todos los dominios`` = navegación (se descartan).

**Refuerzos (04)**: frontmatter malformado / ``uc_id`` ausente → **skip + log** (nunca silencioso);
``uc_id`` **duplicado** entre ficheros → **fail** del batch (colisiona la clave de upsert).

Anti-patrón: leer ``url`` del frontmatter (no existe); silenciar un doc no parseable.
"""
