"""app.rag.reranker — re-ranking de los resultados del retrieval por el peso de `estado`.

**Función pura, deliberadamente fuera del adaptador SQL** (ADR-0018, decisión D3b). Meter el peso en el
`ORDER BY` de `app.infra.vector` tendría tres costes: metería política de negocio en infra, dejaría
**inservible** cualquier índice ANN futuro (un `ORDER BY` con expresiones ponderadas no puede usarlo) y
haría la política intestable sin Postgres.

**El peso es un desempate, no un veto.** El 81% del corpus real está en `estado: draft` (218 de 268):
penalizarlo a ciegas vaciaría el retrieval. Por eso `draft` **no se toca** —solo se premia a `active`—,
con lo que el "suelo" que pide ADR-0010 se cumple por construcción: lo que no se multiplica no baja.

La objeción clásica al re-ranking ("solo reordena dentro de lo ya recuperado") la neutraliza la
**ventana** del camino HTTP (`app.infra.vectorstore.pgvector`): se re-rankea la ventana entera y se
corta a la página, así que un `active` que por coseno crudo caería fuera de la primera página puede
alcanzarla.

Seam futuro (diferido por ADR-0010): re-rank por **cross-encoder**. Iría después de este ajuste, sobre
la misma lista de `RankedHit`; aquí solo se menciona, no se construye.

Anti-patrón: filtrar `draft` por defecto; aplicar el peso dentro del SQL; mutar `Hit.score`.
"""

from dataclasses import dataclass

from app.domain.entities.enums import KbEstado
from app.domain.ports.vector import Hit


@dataclass(frozen=True)
class RankedHit:
    """Un `Hit` con su relevancia re-rankeada, **sin perder la cruda**.

    Los dos scores conviven a propósito (hallazgo C2 del `design-review`):

    - `hit.score` — similitud coseno acotada a `[0, 1]`, **intacta**. La consume la confianza híbrida
      de CU-BE-05; si llevara ya el peso, `estado` se contaría **dos veces**.
    - `weighted_score` — lo que viaja al `KBSearchHit.score` de la API. **Puede superar `1.0`** y por
      tanto ya no es una similitud coseno, sino relevancia (RN-4 de CU-BE-12).
    """

    hit: Hit
    weighted_score: float


def rerank(hits: list[Hit], *, weight: float) -> list[RankedHit]:
    """Ordena `hits` por relevancia descendente aplicando el peso de `estado`.

    `weighted_score = score * (1 + weight)` para `active`; para `draft`, el score **intacto**.

    :param weight: `settings.rag_estado_weight`. **`0.0` es legítimo** —desactiva el desempate y deja
        el orden de la similitud pura—, no un caso degenerado que haya que tratar aparte.
    :returns: lista nueva; ni `hits` ni sus elementos se modifican.

    El orden es **estable** ante empates (`sorted` de Python lo garantiza): dos hits con el mismo
    `weighted_score` conservan su orden de entrada. Importa para la estabilidad de la paginación (RN-6):
    con un orden inestable, dos peticiones de páginas consecutivas podrían repetir un documento o
    perderlo.
    """
    ranked = [RankedHit(hit=hit, weighted_score=_weighted(hit, weight)) for hit in hits]
    return sorted(ranked, key=lambda r: r.weighted_score, reverse=True)


def _weighted(hit: Hit, weight: float) -> float:
    """`score * (1 + weight)` si el documento es `active`; si no, el score sin tocar."""
    if hit.estado is KbEstado.active:
        return hit.score * (1 + weight)
    return hit.score
