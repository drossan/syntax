"""app.infra.db.alembic_url — resolución de la URL de migraciones (superuser).

Aislado en su propio módulo para poder testear el fallo claro sin arrancar Alembic.
`MIGRATION_DATABASE_URL` (rol superuser) NO es campo de `Settings` (least-privilege): la
API nunca arranca con esas credenciales; solo Alembic las lee del entorno (plan L1).
"""

import os

MIGRATION_DATABASE_URL_ENV = "MIGRATION_DATABASE_URL"


def get_migration_database_url() -> str:
    """DSN superuser para Alembic, leído del entorno.

    :raises RuntimeError: si la variable no está definida o está vacía — con un
        mensaje accionable en vez de un ``KeyError`` críptico.
    """
    url = os.environ.get(MIGRATION_DATABASE_URL_ENV)
    if not url:
        raise RuntimeError(
            f"{MIGRATION_DATABASE_URL_ENV} no está definida: expórtala con el DSN del rol "
            "superuser (p.ej. postgresql+asyncpg://syntax:syntax@localhost:5432/syntax) "
            "antes de correr Alembic. La API runtime usa DATABASE_URL (rol syntax_app)."
        )
    return url
