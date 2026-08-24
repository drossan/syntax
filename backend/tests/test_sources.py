"""Tests de `app.ingestion.sources` (tarea backend-kb-source-packages-uc-03).

Registro de tipos de fuente: `resolve_source(source_type) -> SourceType`. Nivel **unit** — el registro
es una tabla pura, sin BD ni filesystem.
"""

import dataclasses

import pytest
from app.domain.errors import Validation
from app.ingestion import loader, packages_uc, parser
from app.ingestion.sources import SourceType, resolve_source


def test_the_real_format_resolves_to_its_own_loader_and_parser() -> None:
    """Escenario añadido: `El registro de tipos resuelve cada tipo a su propio par de descubrimiento
    y parseo`."""
    source = resolve_source("packages-uc")

    assert source.load is packages_uc.load
    assert source.parse is packages_uc.parse


def test_the_hypothetical_format_resolves_to_the_untouched_original_pair() -> None:
    """`vitepress-domains` sigue apuntando a `loader.py`/`parser.py` **sin tocarlos**."""
    source = resolve_source("vitepress-domains")

    assert source.load is loader.load
    assert source.parse is parser.parse


def test_only_the_real_format_declares_that_it_needs_package_aliases() -> None:
    """El metadato que la CLI usa para decidir si avisa de alias vacíos (extensión 1l) — sin él, la
    única salida era un `if source_type == ...` hardcodeado en la CLI, o un falso positivo."""
    assert resolve_source("packages-uc").requires_package_aliases is True
    assert resolve_source("vitepress-domains").requires_package_aliases is False


def test_a_source_type_is_immutable() -> None:
    source = resolve_source("packages-uc")

    with pytest.raises(dataclasses.FrozenInstanceError):
        source.requires_package_aliases = False  # type: ignore[misc]


@pytest.mark.parametrize(
    "source_type",
    [
        pytest.param("Packages-UC", id="la misma con otra caja"),
        pytest.param("PACKAGES-UC", id="todo en mayusculas"),
        pytest.param("packages_uc", id="con guion bajo"),
        pytest.param("no-existe", id="un nombre que no existe"),
        pytest.param("", id="cadena vacia"),
        pytest.param(" packages-uc", id="con espacio a la izquierda"),
    ],
)
def test_only_the_exact_canonical_form_is_recognised(source_type: str) -> None:
    """CU `Scenario Outline: El tipo de fuente solo se reconoce en su forma canónica` — **no** hay
    alias tolerados: una variante de caja es un valor no registrado, no un sinónimo."""
    with pytest.raises(Validation):
        resolve_source(source_type)


def test_an_unknown_source_type_reports_the_value_and_the_valid_options() -> None:
    """Escenario añadido: `Un tipo de fuente desconocido no expone una traza cruda al operador` — el
    mensaje tiene que bastarle al operador para corregir su configuración."""
    with pytest.raises(Validation) as excinfo:
        resolve_source("packages-us")

    message = str(excinfo.value)
    assert "packages-us" in message
    assert "packages-uc" in message
    assert "vitepress-domains" in message


def test_an_unknown_source_type_carries_a_stable_error_code() -> None:
    """Mismo contrato que el resto de `DomainError` del pipeline: slug estable para telemetría."""
    with pytest.raises(Validation) as excinfo:
        resolve_source("no-existe")

    assert excinfo.value.code == "ingestion.unknown_source_type"


def test_resolving_the_same_type_twice_gives_the_same_descriptor() -> None:
    """El registro es una tabla, no una factoría: resolver no construye nada nuevo."""
    assert resolve_source("packages-uc") is resolve_source("packages-uc")


def test_the_registry_exposes_exactly_the_two_documented_source_types() -> None:
    """Si aparece un tercer tipo sin actualizar specs/CU/ADR, este test lo caza."""
    registered = {"packages-uc", "vitepress-domains"}

    for source_type in registered:
        assert isinstance(resolve_source(source_type), SourceType)
    with pytest.raises(Validation) as excinfo:
        resolve_source("cualquier-otro")
    assert sorted(registered) == sorted(
        part.strip() for part in str(excinfo.value).split("válidos:")[1].split(",")
    )
