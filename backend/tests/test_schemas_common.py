"""Tests de app.api.v1.schemas.common (tarea backend-routers-core-03) — Page[T] + Problem."""

from app.api.v1.schemas.common import Page, Problem


def test_page_serializes_exactly_the_four_contract_keys() -> None:
    """Page(items, page, page_size, total) serializa exactamente esas 4 claves con esos valores."""
    page = Page[int](items=[1, 2, 3], page=1, page_size=20, total=3)

    dumped = page.model_dump()

    assert dumped == {"items": [1, 2, 3], "page": 1, "page_size": 20, "total": 3}


def test_page_is_generic_over_item_type() -> None:
    """Page[str] valida/serializa items como str, no como el tipo por defecto."""
    page = Page[str](items=["a", "b"], page=2, page_size=10, total=12)

    assert page.model_dump()["items"] == ["a", "b"]


def test_problem_matches_the_contract_shape() -> None:
    """Problem expone type/title/status/detail/instance/errors, con type por defecto about:blank."""
    problem = Problem(title="No encontrado", status=404, detail="no existe")

    dumped = problem.model_dump()

    assert dumped["type"] == "about:blank"
    assert dumped["title"] == "No encontrado"
    assert dumped["status"] == 404
    assert dumped["detail"] == "no existe"
    assert dumped["instance"] is None
    assert dumped["errors"] is None


def test_problem_errors_field_accepts_field_message_code_entries() -> None:
    """Problem.errors[] acepta entradas {field, message, code} (shape del contrato)."""
    problem = Problem(
        title="Error de validación",
        status=422,
        errors=[{"field": "priority", "message": "valor inválido", "code": "x.invalid"}],
    )

    assert problem.model_dump()["errors"] == [
        {"field": "priority", "message": "valor inválido", "code": "x.invalid"}
    ]
