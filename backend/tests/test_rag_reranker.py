"""Tests unit de `app.rag.reranker` y `app.rag.dedup` (tarea `backend-kb-retriever-05`).

**Sin Postgres y sin red**: son funciones **puras**. Que la política de negocio del retrieval (peso de
`estado`, dedup por documento) sea testeable sin infra es justo el motivo por el que vive aquí y no en
el `ORDER BY` del adaptador SQL (ADR-0018, decisión D3b).

Escenarios de `CU-BE-12` que materializa: *Los borradores participan ponderados, no excluidos*, *Sin
desempate configurado el orden es el de la similitud pura*, *Un documento con varias secciones
relevantes aparece una sola vez*, *Una búsqueda sin coincidencias devuelve vacío, no un error* (a nivel
de función pura). De `CU-BE-05`: *El retrieval no se vacía por el predominio de borradores*.
"""

import uuid

from app.domain.entities.enums import KbDomain, KbEstado
from app.domain.ports.vector import Hit
from app.rag.dedup import dedup_by_uc_id
from app.rag.reranker import RankedHit, rerank


def _hit(
    uc_id: str,
    score: float,
    *,
    estado: KbEstado = KbEstado.draft,
    section_type: str = "comportamiento",
    content: str = "contenido",
) -> Hit:
    return Hit(
        uc_id=uc_id,
        chunk_id=uuid.uuid4(),
        section_type=section_type,
        title=f"Título de {uc_id}",
        source_url=f"packages/x/docs/aiup/use-cases/{uc_id}.md",
        domain=KbDomain.media_and_dam,
        estado=estado,
        score=score,
        content=content,
    )


# ── rerank ──


def test_rerank_boosts_active_documents() -> None:
    """`active` recibe el boost multiplicativo `score * (1 + weight)`."""
    hits = [_hit("UC-1", 0.5, estado=KbEstado.active)]

    ranked = rerank(hits, weight=0.2)

    assert ranked[0].weighted_score == 0.6


def test_rerank_leaves_drafts_untouched() -> None:
    """CU-BE-12 · *Los borradores participan ponderados, no excluidos* — a `draft` **no se le toca el
    score**. El "suelo" bajo el que no puede hundirse (ADR-0010) se cumple **por construcción**: lo que
    no se multiplica no baja."""
    hits = [_hit("UC-1", 0.5, estado=KbEstado.draft)]

    ranked = rerank(hits, weight=0.2)

    assert ranked[0].weighted_score == 0.5


def test_rerank_does_not_mutate_the_raw_score() -> None:
    """El `Hit.score` CRUDO sobrevive al re-ranking (hallazgo C2): la confianza híbrida de CU-BE-05 se
    compone de esa similitud, y si llevara ya el peso contaría `estado` **dos veces**."""
    hits = [_hit("UC-1", 0.5, estado=KbEstado.active)]

    ranked = rerank(hits, weight=0.2)

    assert ranked[0].hit.score == 0.5
    assert ranked[0].weighted_score == 0.6
    assert hits[0].score == 0.5


def test_rerank_keeps_drafts_in_the_result_when_most_of_the_corpus_is_draft() -> None:
    """CU-BE-05 · *El retrieval no se vacía por el predominio de borradores* — con 4 `draft` y 1
    `active`, los 5 siguen en el resultado: el peso es un desempate, no un filtro."""
    hits = [_hit(f"UC-D{i}", 0.5) for i in range(4)] + [_hit("UC-A", 0.5, estado=KbEstado.active)]

    ranked = rerank(hits, weight=0.05)

    assert len(ranked) == 5
    assert {r.hit.uc_id for r in ranked if r.hit.estado is KbEstado.draft} == {
        "UC-D0",
        "UC-D1",
        "UC-D2",
        "UC-D3",
    }


def test_rerank_lets_an_active_overtake_an_equally_relevant_draft() -> None:
    """Con similitud cruda idéntica, el `active` adelanta al `draft`: es el desempate para el que
    existe el peso."""
    hits = [_hit("UC-DRAFT", 0.5), _hit("UC-ACTIVE", 0.5, estado=KbEstado.active)]

    ranked = rerank(hits, weight=0.05)

    assert [r.hit.uc_id for r in ranked] == ["UC-ACTIVE", "UC-DRAFT"]


def test_rerank_does_not_let_an_active_overtake_a_clearly_more_relevant_draft() -> None:
    """Un `draft` **claramente** más relevante NO lo adelanta un `active`: con `weight=0.05` el boost
    es del 5%, así que una ventaja mayor sobrevive al re-ranking. Es lo que hace del peso un desempate
    y no un veto encubierto."""
    hits = [_hit("UC-DRAFT", 0.90), _hit("UC-ACTIVE", 0.60, estado=KbEstado.active)]

    ranked = rerank(hits, weight=0.05)

    assert [r.hit.uc_id for r in ranked] == ["UC-DRAFT", "UC-ACTIVE"]


def test_rerank_with_zero_weight_orders_by_pure_similarity() -> None:
    """CU-BE-12 · *Sin desempate configurado el orden es el de la similitud pura* — `weight=0.0` es un
    valor legítimo (desactiva el desempate), no un valor inválido."""
    hits = [_hit("UC-ACTIVE", 0.4, estado=KbEstado.active), _hit("UC-DRAFT", 0.7)]

    ranked = rerank(hits, weight=0.0)

    assert [r.hit.uc_id for r in ranked] == ["UC-DRAFT", "UC-ACTIVE"]
    assert [r.weighted_score for r in ranked] == [0.7, 0.4]


def test_rerank_sorts_by_weighted_score_descending() -> None:
    hits = [_hit("UC-BAJO", 0.1), _hit("UC-ALTO", 0.9), _hit("UC-MEDIO", 0.5)]

    ranked = rerank(hits, weight=0.05)

    assert [r.hit.uc_id for r in ranked] == ["UC-ALTO", "UC-MEDIO", "UC-BAJO"]


def test_rerank_is_stable_on_exact_ties() -> None:
    """Un empate exacto de `weighted_score` conserva el **orden de entrada** (orden estable).

    No tiene escenario propio en el CU porque es detalle de implementación, pero sostiene la
    estabilidad de paginación que exige RN-6: con un orden inestable, dos peticiones de páginas
    consecutivas podrían devolver el mismo documento dos veces o ninguna.
    """
    hits = [_hit("UC-A", 0.5), _hit("UC-B", 0.5), _hit("UC-C", 0.5)]

    ranked = rerank(hits, weight=0.05)

    assert [r.hit.uc_id for r in ranked] == ["UC-A", "UC-B", "UC-C"]


def test_rerank_ties_between_active_and_draft_are_also_stable() -> None:
    """El empate puede producirse **tras** aplicar el peso (un `draft` de 0.525 empata con un `active`
    de 0.5 y `weight=0.05`): también ahí manda el orden de entrada."""
    hits = [_hit("UC-DRAFT", 0.525), _hit("UC-ACTIVE", 0.5, estado=KbEstado.active)]

    ranked = rerank(hits, weight=0.05)

    assert [r.hit.uc_id for r in ranked] == ["UC-DRAFT", "UC-ACTIVE"]
    assert ranked[0].weighted_score == ranked[1].weighted_score


def test_rerank_on_an_empty_list_returns_empty() -> None:
    """CU-BE-12 · *Una búsqueda sin coincidencias devuelve vacío, no un error* — a nivel de la función
    pura: lista vacía es un resultado legítimo."""
    assert rerank([], weight=0.05) == []


def test_rerank_preserves_every_hit_field() -> None:
    """El `RankedHit` envuelve el `Hit` original sin copiarlo campo a campo: nada se pierde por el
    camino (el `content` lo necesita el snippet de `-06` y el prompt de `generate`)."""
    hit = _hit("UC-1", 0.5, section_type="reglas", content="texto completo del chunk")

    ranked = rerank([hit], weight=0.05)

    assert ranked[0].hit is hit
    assert ranked[0].hit.content == "texto completo del chunk"
    assert ranked[0].hit.section_type == "reglas"


# ── dedup_by_uc_id ──


def test_dedup_keeps_only_the_best_chunk_of_each_document() -> None:
    """CU-BE-12 · *Un documento con varias secciones relevantes aparece una sola vez* — lo representa
    su sección de mayor score (la primera, sobre una lista **ya ordenada**)."""
    ranked = rerank(
        [
            _hit("UC-1", 0.9, section_type="reglas"),
            _hit("UC-1", 0.7, section_type="comportamiento"),
            _hit("UC-2", 0.5),
        ],
        weight=0.05,
    )

    deduped = dedup_by_uc_id(ranked)

    assert [r.hit.uc_id for r in deduped] == ["UC-1", "UC-2"]
    assert deduped[0].hit.section_type == "reglas"
    assert deduped[0].weighted_score == 0.9


def test_dedup_preserves_the_incoming_order() -> None:
    """No reordena: opera sobre una lista ya re-rankeada y solo descarta repetidos."""
    ranked = rerank([_hit("UC-B", 0.9), _hit("UC-A", 0.7), _hit("UC-B", 0.3)], weight=0.05)

    deduped = dedup_by_uc_id(ranked)

    assert [r.hit.uc_id for r in deduped] == ["UC-B", "UC-A"]


def test_dedup_on_an_empty_list_returns_empty() -> None:
    """Frontera con lista vacía (la pide explícitamente el `## Scenarios` de la tarea)."""
    assert dedup_by_uc_id([]) == []


def test_dedup_leaves_a_list_without_repeats_untouched() -> None:
    ranked = rerank([_hit("UC-1", 0.9), _hit("UC-2", 0.5)], weight=0.05)

    assert [r.hit.uc_id for r in dedup_by_uc_id(ranked)] == ["UC-1", "UC-2"]


def test_dedup_collapses_a_document_whose_chunks_are_all_relevant() -> None:
    """Todos los chunks del mismo documento colapsan en uno: sin `chunk_id` en `KBSearchHit`, dos hits
    del mismo UC serían dos tarjetas que enlazan al mismo sitio (y claves React duplicadas)."""
    ranked = rerank([_hit("UC-1", s) for s in (0.9, 0.8, 0.7, 0.6)], weight=0.05)

    deduped = dedup_by_uc_id(ranked)

    assert len(deduped) == 1
    assert deduped[0].weighted_score == 0.9


def test_dedup_returns_ranked_hits_not_plain_hits() -> None:
    """La salida conserva el `weighted_score`: es lo que viaja al `KBSearchHit.score` de la API."""
    ranked = rerank([_hit("UC-1", 0.5, estado=KbEstado.active)], weight=0.2)

    deduped = dedup_by_uc_id(ranked)

    assert isinstance(deduped[0], RankedHit)
    assert deduped[0].weighted_score == 0.6
