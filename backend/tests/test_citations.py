"""Tests unit de `app.rag.citations` (tarea `backend-agent-graph-03`).

**Función pura, sin infra**: `build_citations` no toca Postgres ni el LLM — a partir de los `RankedHit`
usados en una respuesta, construye la lista de citas trazables que viaja a `agent_run.sources`.
Escenarios de `agent-graph.md` (CU-BE-05, escenario 5): *cada hit se convierte en una cita trazable*,
*no se citan dos veces la misma sección*, *secciones distintas sí se citan por separado*, *sin hits no
hay citas*, *tres+ duplicados exactos se colapsan*, *el dedup descarta, no reordena*.
"""

import uuid

from app.domain.entities.enums import KbDomain, KbEstado
from app.domain.ports.vector import Hit
from app.rag.citations import build_citations
from app.rag.reranker import RankedHit


def _ranked_hit(
    uc_id: str,
    section_type: str,
    *,
    score: float,
    weighted_score: float | None = None,
    title: str | None = None,
    source_url: str | None = None,
) -> RankedHit:
    hit = Hit(
        uc_id=uc_id,
        chunk_id=uuid.uuid4(),
        section_type=section_type,
        title=title if title is not None else f"Título de {uc_id}",
        source_url=source_url
        if source_url is not None
        else f"packages/x/docs/aiup/use-cases/{uc_id}.md",
        domain=KbDomain.media_and_dam,
        estado=KbEstado.draft,
        score=score,
        content="contenido",
    )
    return RankedHit(
        hit=hit, weighted_score=weighted_score if weighted_score is not None else score
    )


def test_each_hit_becomes_a_traceable_citation() -> None:
    """La cita incluye `uc_id`, `title`, `section_type`, `source_url` y `score` (= `weighted_score`,
    la relevancia mostrada al usuario, consistente con `KBSearchHit.score`)."""
    ranked = _ranked_hit("CU-BE-05", "comportamiento", score=0.5, weighted_score=0.6)
    [citation] = build_citations([ranked])
    assert citation == {
        "uc_id": "CU-BE-05",
        "title": "Título de CU-BE-05",
        "section_type": "comportamiento",
        "source_url": "packages/x/docs/aiup/use-cases/CU-BE-05.md",
        "score": 0.6,
    }


def test_the_same_section_of_the_same_document_is_not_cited_twice() -> None:
    """Dos hits con el mismo `(uc_id, section_type)` pero distinto `chunk_id` → una sola cita."""
    hits = [
        _ranked_hit("CU-BE-05", "comportamiento", score=0.9),
        _ranked_hit("CU-BE-05", "comportamiento", score=0.8),
    ]
    citations = build_citations(hits)
    assert len(citations) == 1


def test_different_sections_of_the_same_document_are_cited_separately() -> None:
    """Mismo `uc_id`, distinto `section_type` → dos citas."""
    hits = [
        _ranked_hit("CU-BE-05", "comportamiento", score=0.9),
        _ranked_hit("CU-BE-05", "reglas-de-negocio", score=0.8),
    ]
    citations = build_citations(hits)
    assert [c["section_type"] for c in citations] == ["comportamiento", "reglas-de-negocio"]


def test_no_hits_yields_no_citations() -> None:
    assert build_citations([]) == []


def test_three_or_more_exact_duplicates_collapse_into_a_single_citation() -> None:
    hits = [
        _ranked_hit("CU-BE-05", "comportamiento", score=0.9),
        _ranked_hit("CU-BE-05", "comportamiento", score=0.8),
        _ranked_hit("CU-BE-05", "comportamiento", score=0.7),
    ]
    citations = build_citations(hits)
    assert len(citations) == 1


def test_dedup_discards_it_does_not_reorder() -> None:
    """`[A(uc1,intro), B(uc2,intro), C(uc1,intro — duplicado de A, no contiguo)]` → `[cita_A, cita_B]`,
    sin reordenar ni insertar C."""
    hit_a = _ranked_hit("uc1", "intro", score=0.9)
    hit_b = _ranked_hit("uc2", "intro", score=0.8)
    hit_c = _ranked_hit("uc1", "intro", score=0.7)
    citations = build_citations([hit_a, hit_b, hit_c])
    assert [c["uc_id"] for c in citations] == ["uc1", "uc2"]


def test_a_duplicate_in_the_middle_does_not_stop_later_distinct_citations() -> None:
    """Un duplicado NO al final del todo: tras descartarlo, el recorrido sigue con los hits
    posteriores (descarta esa entrada, no corta el resto de la lista)."""
    hit_a = _ranked_hit("uc1", "intro", score=0.9)
    hit_a_dup = _ranked_hit("uc1", "intro", score=0.85)
    hit_b = _ranked_hit("uc2", "intro", score=0.8)
    citations = build_citations([hit_a, hit_a_dup, hit_b])
    assert [c["uc_id"] for c in citations] == ["uc1", "uc2"]
