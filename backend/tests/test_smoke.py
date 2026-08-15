"""Smoke test de arranque del scaffold.

No es un test de negocio: solo confirma que el entorno y el paquete ``app`` están
sanos (import correcto + versión de Python esperada). Entra por el *carve-out* de
``testing.md`` §1 (scaffold de arranque, sin test rojo previo). Las tareas 03+ escriben
los tests TDD reales (rojo → verde → refactor) sobre este mismo scaffold.
"""

import sys


def test_python_is_312_or_newer() -> None:
    """El intérprete es Python 3.12+ (paridad con pyproject/Dockerfile)."""
    assert sys.version_info >= (3, 12)


def test_app_package_importable() -> None:
    """El paquete ``app`` se importa sin errores (esqueleto sano)."""
    import app

    assert app.__name__ == "app"
