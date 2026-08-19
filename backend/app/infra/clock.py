"""app.infra.clock — adaptador real del puerto `Clock`.

Único punto donde el proceso llama al reloj del sistema; el dominio nunca invoca `datetime.now()`
directamente (lo hace inyectable/testeable vía el puerto `app.domain.ports.clock.Clock`).
"""

from datetime import UTC, datetime


class SystemClock:
    """Adaptador de `Clock`: `now()` delega en el reloj real del sistema (UTC)."""

    def now(self) -> datetime:
        return datetime.now(UTC)
