"""conftest.py — fixtures y configuración compartida de pytest (árbol `tests/`).

pytest carga este fichero **automáticamente** (no se importa a mano): todo lo que se
defina aquí —sobre todo *fixtures*— queda disponible para cualquier test del árbol.

De momento es un placeholder. La tarea 03 (settings) añadirá aquí la fixture que
resetea el cache de ``get_settings()`` (``lru_cache``) entre tests, para que cada test
inyecte su propia configuración sin contaminación entre suites.
"""
