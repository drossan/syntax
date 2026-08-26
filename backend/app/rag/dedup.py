"""app.rag.dedup — colapso de chunks al documento que los contiene.

**Módulo propio, y no una función más de `reranker.py`**, porque su consumidor es distinto: `rerank` lo
usan **los dos** caminos del retrieval (el del agente y el HTTP), mientras que `dedup_by_uc_id` lo llama
**solo el adaptador HTTP** (`app.infra.vectorstore.pgvector`). Ponerlos en el mismo módulo sugeriría que
van en pareja e invitaría a llamarlos siempre juntos — justo lo que la decisión D3a prohíbe: el camino
del agente consume chunks **sin deduplicar**, porque varias secciones del mismo UC son varias piezas de
contexto legítimas para el prompt.

Por el mismo motivo **no hay un flag `dedup: bool`**: un booleano cuyas dos ramas tienen cada una su
propio consumidor es una función distinta llamada desde sitios distintos, no un parámetro (hallazgo A1).

**Por qué el camino HTTP sí deduplica**: `KBSearchHit` no expone `chunk_id` (id interno que el contrato
oculta a propósito), así que dos hits del mismo `uc_id` serían dos tarjetas que enlazan al mismo sitio
— y el front usa `key={hit.uc_id}`, con lo que además serían claves React duplicadas.
"""

from app.rag.reranker import RankedHit


def dedup_by_uc_id(ranked: list[RankedHit]) -> list[RankedHit]:
    """Deja un solo `RankedHit` por `uc_id`: el **primero** de cada documento.

    Opera sobre una lista **ya ordenada por relevancia** (la que devuelve `rerank`), así que "el
    primero" es "el de mayor `weighted_score`" — es decir, el documento queda representado por su mejor
    sección, con el `score`, el `section_type` y el texto de esa sección (RN-1 de CU-BE-12).

    **No reordena**: conserva el orden de entrada y se limita a descartar repetidos. Reordenar aquí
    duplicaría una responsabilidad que ya es de `rerank`.

    :returns: lista nueva; la de entrada no se modifica.
    """
    seen: set[str] = set()
    deduped: list[RankedHit] = []
    for item in ranked:
        if item.hit.uc_id in seen:
            continue
        seen.add(item.hit.uc_id)
        deduped.append(item)
    return deduped
