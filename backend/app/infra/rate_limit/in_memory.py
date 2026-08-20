"""app.infra.rate_limit.in_memory — adaptador STUB-como-real de `RateLimiter` (tarea 12).

Ventana fija de 1 minuto, contador `dict[str, tuple[int, float]]` (`count`, `window_start` en epoch
segundos) **en memoria del proceso** — no compartido entre workers/instancias. Limitación documentada,
no resuelta en esta tarea (rate-limiting distribuido, Redis/almacén compartido, queda fuera de este
plan): con más de un proceso el límite real es `N × nº de procesos`.

Debe construirse **una sola vez por proceso** (singleton, `app.core.deps.get_agent_service`) — una
instancia nueva por request reiniciaría el contador en cada petición y el límite nunca se alcanzaría.
"""

from app.domain.ports.clock import Clock
from app.infra.clock import SystemClock

_WINDOW_SECONDS = 60.0


class InMemoryRateLimiter:
    """Adaptador de `RateLimiter`: ventana fija de 60s, contador por clave en memoria de proceso."""

    def __init__(self, limit: int, *, clock: Clock | None = None) -> None:
        self._limit = limit
        self._clock = clock if clock is not None else SystemClock()
        self._counters: dict[str, tuple[int, float]] = {}

    async def check_and_increment(self, key: str) -> bool:
        now = self._clock.now().timestamp()
        count, window_start = self._counters.get(key, (0, now))
        if now - window_start >= _WINDOW_SECONDS:
            count, window_start = 0, now
        if count >= self._limit:
            self._counters[key] = (count, window_start)
            return False
        self._counters[key] = (count + 1, window_start)
        return True
