"""Tests unit de `app.rag.confidence` (tarea `backend-agent-graph-02`).

**Función pura, sin infra**: `compute_confidence` no toca Postgres ni el LLM — solo combina la similitud
cruda de los `RankedHit` recuperados con el `grade.suficiente` que produce el nodo `grade` del grafo
(ADR-0009). Escenarios de `agent-graph.md`: *contexto suficiente da la similitud máxima como confianza*,
*contexto insuficiente escala con confianza 0*, *sin hits nunca hay confianza aunque el LLM diga que
basta*, *un solo hit determina la confianza si es el único*.
"""

import uuid

import pytest
from app.domain.entities.enums import KbDomain, KbEstado
from app.domain.ports.vector import Hit
from app.rag.confidence import compute_confidence
from app.rag.reranker import RankedHit


def _ranked_hit(score: float, *, weighted_score: float | None = None) -> RankedHit:
    hit = Hit(
        uc_id="CU-BE-05",
        chunk_id=uuid.uuid4(),
        section_type="comportamiento",
        title="Título",
        source_url="packages/x/docs/aiup/use-cases/CU-BE-05.md",
        domain=KbDomain.media_and_dam,
        estado=KbEstado.draft,
        score=score,
        content="contenido",
    )
    return RankedHit(
        hit=hit, weighted_score=weighted_score if weighted_score is not None else score
    )


def test_sufficient_context_gives_the_raw_max_similarity_as_confidence() -> None:
    """El resultado es el score CRUDO máximo de los hits, no el `weighted_score` (contaría el peso de
    `estado` dos veces — ya se aplica en `reranker.py`)."""
    retrieved = [
        _ranked_hit(score=0.3, weighted_score=0.9),
        _ranked_hit(score=0.7, weighted_score=0.75),
    ]
    assert compute_confidence(retrieved, grade_suficiente=True) == 0.7


def test_insufficient_context_scales_to_zero_confidence_regardless_of_score() -> None:
    """`grade_suficiente=False` es un veto: la confianza es 0.0 aunque los scores sean altos."""
    retrieved = [_ranked_hit(score=1.0), _ranked_hit(score=0.95)]
    assert compute_confidence(retrieved, grade_suficiente=False) == 0.0


def test_no_hits_never_yields_confidence_even_if_the_llm_claims_sufficiency() -> None:
    """`retrieved=[]` con `grade_suficiente=True` (el LLM alucina suficiencia sin hits) es insuficiente,
    no un `ValueError` de `max()` sobre secuencia vacía."""
    assert compute_confidence([], grade_suficiente=True) == 0.0


@pytest.mark.parametrize("score", [0.0, 1.0])
def test_a_single_hit_determines_confidence_when_it_is_the_only_one(score: float) -> None:
    assert compute_confidence([_ranked_hit(score=score)], grade_suficiente=True) == score
