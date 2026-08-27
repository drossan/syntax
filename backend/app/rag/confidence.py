"""app.rag.confidence — confianza híbrida (similitud + grade), ADR-0009.

Combina **(a)** la similitud CRUDA de los chunks recuperados (`RankedHit.hit.score`, sin el peso de
`estado` que ya aplica `app.rag.reranker`) con **(b)** el juicio del LLM (`grade.suficiente`, nodo
`grade` del grafo). El `grade` actúa como **veto**, no como sumando aritmético: sin contexto suficiente,
la confianza es `0.0` sin importar cuán alta sea la similitud — el agente nunca inventa una respuesta.

Función pura, sin I/O ni puertos.
"""

from app.rag.reranker import RankedHit


def compute_confidence(retrieved: list[RankedHit], grade_suficiente: bool) -> float:
    """Confianza híbrida en `[0.0, 1.0]` para gobernar auto-respuesta vs escalado (nodo `decide`).

    Similitud CRUDA (`hit.score`), no `weighted_score`: si llevara ya el peso de `estado`, éste se
    contaría dos veces (`reranker.py`). Sin hits o con `grade_suficiente=False`, la confianza es `0.0`
    — incluye el caso borde de un LLM que alucina suficiencia sin contexto (`retrieved=[]` con
    `grade_suficiente=True`), que de otro modo lanzaría `ValueError` en `max()` sobre secuencia vacía.
    """
    if not grade_suficiente or not retrieved:
        return 0.0
    return max(ranked.hit.score for ranked in retrieved)
