"""app.ingestion.loader — descubre y lee los .md de la KB.

GUIÓN (→ tarea 13; spec 04)
---------------------------
Qué implementar:
  - Recorre ``domains/<dominio>/uc/UC-*.md`` (268 UC / 17 dominios) + ``<dominio>/index.md`` (17, para el
    glosario). Ruta **configurable** (``settings`` / arg CLI; default la KB de docs-site).
  - Excluye el ``domains/index.md`` raíz (navegación, sin Glosario).
  - **Fallback documentado** (solo si ``domains/`` no está disponible): ``.vitepress/dist/llms-full.txt``.
  - Devuelve documentos crudos (ruta + contenido) para el parser.

Anti-patrón: asumir rutas fijas hardcodeadas; cargar todo en memoria sin necesidad (streaming por fichero).
"""
