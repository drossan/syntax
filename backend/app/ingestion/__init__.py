"""app.ingestion — pipeline de ingestión de la KB.

GUIÓN (→ tarea 13)
------------------
Entry-point CLI idempotente (``python -m app.ingestion``) que ingesta la KB real
(``domains/*/uc/*.md`` de docs-site). Ver `rag-ingestion` (tarea 04).

Etapas:
  - loader   → recorre ``domains/*/uc/*.md`` (+ ``index.md`` para el glosario).
  - parser   → frontmatter ``title/domain/package/uc`` + bloque ``::: info Trazabilidad``
               (``Estado``/``Traza``). Maneja frontmatter malformado / ``uc-id`` duplicado / huérfanos.
  - chunker  → por sección **H2 tolerante** (H2 casi-uniformes con variantes y H2 sueltos:
               NO asumir estructura rígida).
  - embedder → embeddings (``EMBEDDING_MODEL``) → ``app.infra.vector``.
  - upsert   → **idempotente por ``uc-id``** (re-ingesta no duplica; refleja cambios).

``estado`` (draft ≈218 / active ≈50) es **señal de retrieval con peso explícito**, NO se
penaliza draft a ciegas (es el 81% del corpus).

Tipos de fuente
---------------
El GUIÓN de arriba describe el formato ``vitepress-domains`` (``loader``/``parser``), **hipotético y
nunca verificado** contra una fuente real. ``packages_uc`` implementa el descubrimiento del formato
**real verificado** (``packages/<pkg>/docs/aiup/use-cases/UC-*.md`` + glosarios planos por dominio en
una ruta compartida). Su parser y la selección del tipo de fuente (registro + ``Settings``/CLI) son las
tareas ``-02``/``-03`` del plan ``kb-source-packages-uc``.
"""
