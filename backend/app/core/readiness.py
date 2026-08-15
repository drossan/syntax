"""app.core.readiness — chequeo de readiness de la DB (alcanzable + pgvector + dimensión).

Aislado en su propio módulo (código de comportamiento) para acotar el gate de mutation. Usa
asyncpg directo con un timeout acotado (`asyncio.wait_for`): una DB colgada NO debe hacer que
`/health/ready` cuelgue indefinidamente → se traduce en un fallo controlado (503 en el router).
"""

import asyncio

import asyncpg

_DEFAULT_TIMEOUT = 5.0


class ReadinessError(Exception):
    """Fallo de readiness; el mensaje es el `detail` del chequeo que falló (para el problem+json)."""


def _asyncpg_dsn(database_url: str) -> str:
    """Convierte el DSN SQLAlchemy (`postgresql+asyncpg://…`) al que espera `asyncpg.connect`."""
    return database_url.replace("+asyncpg", "")


async def check_database_ready(
    database_url: str,
    embedding_dim: int,
    timeout: float = _DEFAULT_TIMEOUT,  # noqa: ASYNC109 — probe self-contained: default acotado
) -> None:
    """Verifica DB alcanzable + extensión `vector` + dim de `embedding.vector` == `embedding_dim`.

    :raises ReadinessError: con el detalle del primer chequeo que falla (DB inalcanzable/timeout,
        extensión ausente, tabla no migrada o dimensión desajustada).
    """
    try:
        async with asyncio.timeout(timeout):
            connection = await asyncpg.connect(dsn=_asyncpg_dsn(database_url))
    except (TimeoutError, OSError, asyncpg.PostgresError) as exc:
        raise ReadinessError(f"base de datos no alcanzable: {exc}") from exc

    try:
        has_vector = await connection.fetchval(
            "SELECT count(*) FROM pg_extension WHERE extname = 'vector'"
        )
        if not has_vector:
            raise ReadinessError("la extensión 'vector' (pgvector) no está instalada")

        live_type = await connection.fetchval(
            "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
            "WHERE attrelid = to_regclass('public.embedding') "
            "AND attname = 'vector' AND NOT attisdropped"
        )
        if live_type is None:
            raise ReadinessError("la tabla 'embedding' no existe (¿migración pendiente?)")

        expected = f"vector({embedding_dim})"
        if live_type != expected:
            raise ReadinessError(
                f"la dimensión viva del vector ({live_type}) no coincide con la config ({expected})"
            )
    finally:
        await connection.close()
