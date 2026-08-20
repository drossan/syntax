"""Tests de app.infra.rate_limit.in_memory (tarea backend-routers-flujo-ia-01).

Nivel unit: `InMemoryRateLimiter` con un `Clock` fake inyectado (ventana fija de 1 minuto,
determinista). Cubre los escenarios de frontera del Gherkin de la tarea (N-ésimo aceptado, expiración
de ventana, aislamiento entre claves/tenants).
"""

from datetime import UTC, datetime, timedelta

from app.infra.rate_limit.in_memory import InMemoryRateLimiter

_T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


class _FakeClock:
    def __init__(self, now: datetime = _T0) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def advance(self, **kwargs: float) -> None:
        self._now += timedelta(**kwargs)


async def test_first_request_within_limit_is_accepted() -> None:
    clock = _FakeClock()
    limiter = InMemoryRateLimiter(limit=10, clock=clock)

    assert await limiter.check_and_increment("tenant-a") is True


async def test_the_nth_request_exactly_at_the_limit_is_accepted() -> None:
    """El disparo número `limit` (el último permitido) se acepta."""
    clock = _FakeClock()
    limiter = InMemoryRateLimiter(limit=3, clock=clock)

    first = await limiter.check_and_increment("tenant-a")
    second = await limiter.check_and_increment("tenant-a")
    third = await limiter.check_and_increment("tenant-a")

    assert (first, second, third) == (True, True, True)


async def test_the_request_beyond_the_limit_is_rejected() -> None:
    clock = _FakeClock()
    limiter = InMemoryRateLimiter(limit=2, clock=clock)

    await limiter.check_and_increment("tenant-a")
    await limiter.check_and_increment("tenant-a")
    third = await limiter.check_and_increment("tenant-a")

    assert third is False


async def test_a_rejected_request_does_not_consume_extra_quota() -> None:
    """Un intento rechazado no sigue incrementando el contador (idempotente respecto a reintentos)."""
    clock = _FakeClock()
    limiter = InMemoryRateLimiter(limit=1, clock=clock)

    await limiter.check_and_increment("tenant-a")
    rejected_1 = await limiter.check_and_increment("tenant-a")
    rejected_2 = await limiter.check_and_increment("tenant-a")

    assert rejected_1 is False
    assert rejected_2 is False


async def test_after_the_window_expires_the_quota_resets() -> None:
    clock = _FakeClock()
    limiter = InMemoryRateLimiter(limit=1, clock=clock)

    await limiter.check_and_increment("tenant-a")
    exhausted = await limiter.check_and_increment("tenant-a")
    clock.advance(seconds=61)
    after_expiry = await limiter.check_and_increment("tenant-a")

    assert exhausted is False
    assert after_expiry is True


async def test_a_request_exactly_at_the_window_boundary_still_counts_as_expired() -> None:
    """Frontera exacta: a los 60s justos, la ventana anterior ya expiró (ventana `< 60`, no `<= 60`)."""
    clock = _FakeClock()
    limiter = InMemoryRateLimiter(limit=1, clock=clock)

    await limiter.check_and_increment("tenant-a")
    clock.advance(seconds=60)
    result = await limiter.check_and_increment("tenant-a")

    assert result is True


async def test_one_tenant_exhausting_its_quota_does_not_affect_another() -> None:
    clock = _FakeClock()
    limiter = InMemoryRateLimiter(limit=1, clock=clock)

    await limiter.check_and_increment("tenant-a")
    tenant_a_second = await limiter.check_and_increment("tenant-a")
    tenant_b_first = await limiter.check_and_increment("tenant-b")

    assert tenant_a_second is False
    assert tenant_b_first is True
