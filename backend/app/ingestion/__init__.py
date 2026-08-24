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
nunca verificado** contra una fuente real. ``packages_uc`` implementa el formato **real verificado**
(``packages/<pkg>/docs/aiup/use-cases/UC-*.md`` + glosarios planos por dominio en una ruta compartida),
y es el **default**. ``sources.resolve_source(source_type)`` selecciona el par ``(load, parse)``; lo
consume ``pipeline.ingest()``, y la CLI expone el selector con ``--source-type``.
Decisión: `ADR-0017`; detalle: ``rag-ingestion.md`` §1/§2.
"""
