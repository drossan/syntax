"""app.rag.reranker — re-ranking de resultados (peso de estado).

GUIÓN (→ tarea 14; spec 04)
---------------------------
Qué implementar:
  - Re-ordena los hits del retriever aplicando el **peso de ``estado`` explícito** (``RAG_ESTADO_WEIGHT``,
    config): ``active`` recibe un boost leve; ``draft`` **no** se hunde por debajo de un suelo (el 81% del
    corpus es draft — penalizarlo a ciegas vaciaría el retrieval). Es un **desempate**, no un veto.
  - Seam para un **cross-encoder** futuro (diferido); en Fase 1 solo el ajuste por ``estado``.

Anti-patrón: filtrar draft por defecto; peso de estado oculto/implícito.
"""
