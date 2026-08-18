"""app.domain.ports.clock — puerto de reloj (tiempo inyectable).

Hace testeables las reglas que dependen del tiempo (SLA, expiración de tokens/sesiones) sin depender del
reloj real. Anti-patrón: llamar a `datetime.now()` directamente dentro de la lógica de negocio.
"""

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """Puerto mínimo de tiempo: `now()` devuelve un `datetime` UTC timezone-aware."""

    def now(self) -> datetime:
        """Instante actual, UTC, timezone-aware."""
        ...
