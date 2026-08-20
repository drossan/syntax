"""app.domain.ports.rate_limiter — puerto `RateLimiter` (rate-limiting mínimo, tarea 12).

Recortado a una sola operación: `check_and_increment` decide Y consume cupo en un solo acto (evita un
`check`+`increment` en dos pasos que un llamante podría usar de forma inconsistente). El `key` es
responsabilidad del llamante (p.ej. `str(tenant_id)` para un límite por tenant) — este puerto no conoce
tenants ni tickets, solo cuenta contra una clave arbitraria.
"""

from typing import Protocol


class RateLimiter(Protocol):
    """Puerto de rate-limiting por ventana fija."""

    async def check_and_increment(self, key: str) -> bool:
        """Registra una petición para `key` y decide si cabe en la ventana actual.

        :returns: `True` si la petición cabe (y queda consumida); `False` si excede el límite (la
            petición NO se descuenta dos veces por un reintento del llamante — cada llamada es un
            intento nuevo).
        """
        ...
