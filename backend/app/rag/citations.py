"""app.rag.citations — construcción de citas trazables de las fuentes (CU-BE-05, escenario 5).

A partir de los `RankedHit` usados en una respuesta del agente, construye la lista de citas que viaja a
`agent_run.sources` (JSONB) y que el router `agent.py` deserializa como `Citation(**source)`.

**No reutiliza `app.rag.dedup.dedup_by_uc_id`**: ese módulo documenta que su único consumidor es el
camino HTTP, donde colapsa a un hit por `uc_id` (pierde qué secciones se usaron). Las citas del agente
necesitan trazar cada **sección** citada, no solo el documento — de ahí el dedup propio por
`(uc_id, section_type)`.

Función pura, sin I/O ni puertos.
"""

from typing import Any

from app.rag.reranker import RankedHit


def build_citations(hits: list[RankedHit]) -> list[dict[str, Any]]:
    """Construye las citas de `hits`, deduplicadas por `(uc_id, section_type)`.

    Conserva la **primera** aparición de cada par — `hits` ya llega ordenado por relevancia desde
    `rerank()` — y descarta el resto sin reordenar. `score` es el `weighted_score` (la relevancia
    mostrada al usuario, consistente con `KBSearchHit.score` del camino HTTP), no el score crudo.

    `list[dict]`, no un modelo Pydantic propio: el consumidor directo es `agent_run.sources`
    (`list[dict[str, Any]]`, `business.py`), y un tipo intermedio solo serializaría sin más uso.
    """
    seen: set[tuple[str, str]] = set()
    citations: list[dict[str, Any]] = []
    for ranked in hits:
        key = (ranked.hit.uc_id, ranked.hit.section_type)
        if key in seen:
            continue
        seen.add(key)
        citations.append(
            {
                "uc_id": ranked.hit.uc_id,
                "title": ranked.hit.title,
                "section_type": ranked.hit.section_type,
                "source_url": ranked.hit.source_url,
                "score": ranked.weighted_score,
            }
        )
    return citations
