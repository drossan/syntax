"""Tests de app.ingestion.embedder (tarea backend-kb-ingestion-05). `EmbeddingModel` fake puro, sin
mocks de BD — mismo patrón que `_FakeChatModel` en `tests/test_classification.py`.
"""

import dataclasses

import pytest
from app.domain.errors import PortError
from app.ingestion.chunker import Chunk
from app.ingestion.embedder import ChunkWithVector, embed


class _FakeEmbeddingModel:
    def __init__(
        self,
        *,
        vectors_per_call: list[list[list[float]]] | None = None,
        raises: Exception | None = None,
    ) -> None:
        self.calls: list[list[str]] = []
        self._vectors_per_call = vectors_per_call
        self._raises = raises

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        if self._raises is not None:
            raise self._raises
        if self._vectors_per_call is not None:
            return self._vectors_per_call[len(self.calls) - 1]
        return [[0.1, 0.2] for _ in texts]


def _chunk(ordinal: int, content: str = "contenido") -> Chunk:
    return Chunk(
        content=content,
        section_type="comportamiento",
        token_count=len(content.split()),
        ordinal=ordinal,
        uc_id="UC-CX-001",
        domain="authoring-and-editor",
        package="syntax-cx",
        estado="active",
    )


async def test_embed_returns_one_chunk_with_vector_per_input_in_order() -> None:
    chunks = [_chunk(0, "uno"), _chunk(1, "dos"), _chunk(2, "tres")]
    model = _FakeEmbeddingModel()

    result = await embed(chunks, model, batch_size=100)

    assert len(result) == 3
    assert [r.chunk.ordinal for r in result] == [0, 1, 2]
    assert all(isinstance(r, ChunkWithVector) for r in result)
    assert all(r.vector == [0.1, 0.2] for r in result)


async def test_embed_calls_the_provider_once_when_under_batch_size() -> None:
    chunks = [_chunk(i) for i in range(5)]
    model = _FakeEmbeddingModel()

    await embed(chunks, model, batch_size=100)

    assert len(model.calls) == 1
    assert model.calls[0] == [c.content for c in chunks]


async def test_embed_splits_into_sub_batches_over_the_limit() -> None:
    chunks = [_chunk(i) for i in range(5)]
    model = _FakeEmbeddingModel(
        vectors_per_call=[[[0.1] for _ in range(2)], [[0.2] for _ in range(2)], [[0.3]]]
    )

    result = await embed(chunks, model, batch_size=2)

    assert len(model.calls) == 3
    assert [len(c) for c in model.calls] == [2, 2, 1]
    assert [r.chunk.ordinal for r in result] == [0, 1, 2, 3, 4]
    assert [r.vector for r in result] == [[0.1], [0.1], [0.2], [0.2], [0.3]]


async def test_embed_with_empty_list_does_not_call_the_provider() -> None:
    model = _FakeEmbeddingModel()

    result = await embed([], model, batch_size=100)

    assert result == []
    assert model.calls == []


async def test_embed_with_a_single_chunk_makes_one_call_with_one_text() -> None:
    chunks = [_chunk(0, "único")]
    model = _FakeEmbeddingModel()

    result = await embed(chunks, model, batch_size=100)

    assert len(model.calls) == 1
    assert model.calls[0] == ["único"]
    assert len(result) == 1


async def test_embed_propagates_provider_failure() -> None:
    chunks = [_chunk(0)]
    model = _FakeEmbeddingModel(raises=PortError("fallo del proveedor"))

    with pytest.raises(PortError):
        await embed(chunks, model, batch_size=100)


async def test_embed_detects_vector_count_mismatch_in_a_sub_batch() -> None:
    chunks = [_chunk(0), _chunk(1), _chunk(2)]
    model = _FakeEmbeddingModel(vectors_per_call=[[[0.1], [0.2]]])  # 2 vectores para 3 textos

    with pytest.raises(PortError):
        await embed(chunks, model, batch_size=100)


async def test_embed_does_not_assign_vectors_to_the_wrong_chunks_on_a_mismatch() -> None:
    """El desajuste se detecta ANTES de construir cualquier `ChunkWithVector` de ese sub-lote — no
    debe haber resultados parciales con vectores mal emparejados."""
    chunks = [_chunk(0), _chunk(1), _chunk(2), _chunk(3)]
    model = _FakeEmbeddingModel(
        vectors_per_call=[
            [[0.1], [0.2]],
            [[0.3], [0.4], [0.5]],
        ]  # 2º sub-lote: 3 vectores, 2 textos
    )

    with pytest.raises(PortError):
        await embed(chunks, model, batch_size=2)


def test_chunk_with_vector_is_immutable() -> None:
    instance = ChunkWithVector(chunk=_chunk(0), vector=[0.1])

    with pytest.raises(dataclasses.FrozenInstanceError):
        instance.vector = [0.2]  # type: ignore[misc]


async def test_embed_with_a_large_batch_over_256_items_does_not_falsely_detect_a_mismatch() -> None:
    """> 256 elementos: fuera del rango de enteros cacheados de CPython (-5..256) — descarta un
    `!=` mutado a `is not` en la comprobación de conteo, que compararía por identidad de objeto en
    vez de por valor y podría dar un falso positivo de desajuste con dos cuentas iguales pero de
    objetos `int` distintos."""
    chunks = [_chunk(i) for i in range(300)]
    model = _FakeEmbeddingModel()

    result = await embed(chunks, model, batch_size=1000)

    assert len(result) == 300
