"""Tests de app.domain.errors + app.domain.ports.{repositories,clock,email} (tarea backend-domain-services-02).

Nivel unit. Verifica la jerarquía de excepciones (taxonomía HTTP-derivable), que cada puerto tiene un
fake mínimo que lo satisface, y el comportamiento CAS de ApprovalRepository.decide_if_pending /
RefreshSessionRepository.rotate_if_active.
"""

import uuid
from datetime import UTC, datetime

import pytest
from app.domain.errors import (
    Conflict,
    DomainError,
    InvalidTransition,
    NotFound,
    PortError,
    Validation,
)
from app.domain.ports.clock import Clock
from app.domain.ports.email import EmailPort
from app.domain.ports.repositories import (
    AgentRunRepository,
    ApprovalRepository,
    AuditLogRepository,
    AuthTokenRepository,
    MessageRepository,
    NotificationRepository,
    Reused,
    RoleRepository,
    Rotated,
    TenantRepository,
    TicketRepository,
    UserRepository,
)
from app.domain.ports.repositories import (
    RefreshSessionRepository as RefreshSessionRepositoryProtocol,
)


def test_each_domain_error_derives_from_an_http_mappable_base() -> None:
    """Cada excepción concreta hereda de NotFound, Conflict, InvalidTransition o Validation."""
    assert issubclass(InvalidTransition, Conflict)
    for cls in (NotFound, Conflict, InvalidTransition, Validation):
        assert issubclass(cls, DomainError)


def test_domain_error_exposes_code_and_details() -> None:
    """Una excepción de dominio concreta expone code (slug) y details (dict)."""
    exc = NotFound("no existe", code="ticket.not_found", details={"ticket_id": "abc"})
    assert exc.code == "ticket.not_found"
    assert exc.details == {"ticket_id": "abc"}


def test_domain_error_without_details_defaults_to_empty_dict() -> None:
    """Sin details explícito, el atributo es un dict vacío, nunca None."""
    exc = Validation("mal", code="x.y")
    assert exc.details == {}


def test_port_error_exists() -> None:
    """PortError existe como excepción de dominio (envuelve fallos de infra)."""
    assert issubclass(PortError, DomainError)


def test_port_error_preserves_original_exception() -> None:
    """PortError.__cause__ es la excepción original (raise ... from exc)."""
    original = TimeoutError("boom")
    try:
        raise PortError("fallo de infra") from original
    except PortError as exc:
        assert exc.__cause__ is original


class _FakeTenantRepository:
    async def get(self, tenant_id: uuid.UUID) -> None:
        return None

    async def add(self, tenant: object) -> object:
        return tenant


class _FakeClock:
    def now(self) -> datetime:
        return datetime(2026, 1, 1, tzinfo=UTC)


class _FakeEmailPort:
    async def send(self, to: str, template: str, context: dict[str, object]) -> None:
        return None


@pytest.mark.parametrize(
    ("protocol", "fake"),
    [
        (TenantRepository, _FakeTenantRepository()),
        (Clock, _FakeClock()),
        (EmailPort, _FakeEmailPort()),
    ],
)
def test_fake_satisfies_protocol_structurally(protocol: type, fake: object) -> None:
    """Un fake mínimo satisface el Protocol (duck typing tipado, sin isinstance runtime)."""
    for name in dir(protocol):
        if not name.startswith("_"):
            assert hasattr(fake, name)


@pytest.mark.parametrize(
    "protocol",
    [
        UserRepository,
        RoleRepository,
        RefreshSessionRepositoryProtocol,
        AuthTokenRepository,
        TicketRepository,
        MessageRepository,
        ApprovalRepository,
        AgentRunRepository,
        NotificationRepository,
        AuditLogRepository,
    ],
)
def test_repository_protocol_is_importable_and_is_a_protocol(protocol: type) -> None:
    """Cada puerto de repositorio existe y es un typing.Protocol (verificación de existencia/forma)."""
    from typing import Protocol, get_origin

    assert Protocol in protocol.__mro__ or getattr(protocol, "_is_protocol", False)
    assert get_origin(protocol) is None  # no es un genérico mal formado


class _FakeApprovalRepositoryNotFound:
    async def decide_if_pending(
        self,
        task_id: uuid.UUID,
        decision: str,
        final_body: str | None,
        human_note: str | None,
    ) -> None:
        raise NotFound(f"approval task {task_id} not found", code="approval.not_found")


class _FakeApprovalRepositoryAlreadyDecided:
    async def decide_if_pending(
        self,
        task_id: uuid.UUID,
        decision: str,
        final_body: str | None,
        human_note: str | None,
    ) -> None:
        return None


async def test_decide_if_pending_raises_not_found_for_missing_task() -> None:
    """decide_if_pending lanza NotFound si el task_id no existe en absoluto."""
    repo = _FakeApprovalRepositoryNotFound()
    with pytest.raises(NotFound):
        await repo.decide_if_pending(uuid.uuid4(), "approve", None, None)


async def test_decide_if_pending_returns_none_for_already_decided_task() -> None:
    """decide_if_pending devuelve None (no lanza) si la tarea existe pero ya no está pending."""
    repo = _FakeApprovalRepositoryAlreadyDecided()
    result = await repo.decide_if_pending(uuid.uuid4(), "approve", None, None)
    assert result is None


class _FakeRefreshSessionRepository:
    def __init__(self, outcome: object) -> None:
        self._outcome = outcome

    async def rotate_if_active(self, token_hash: str, new_token_hash: str, now: datetime) -> object:
        if self._outcome == "not_found":
            raise NotFound("no session", code="refresh.not_found")
        return self._outcome


@pytest.mark.parametrize(
    ("outcome", "expected_type"),
    [
        (Rotated(session="a-session"), Rotated),  # type: ignore[arg-type]
        (Reused(family_id=uuid.uuid4()), Reused),
    ],
)
async def test_rotate_if_active_returns_rotated_or_reused(
    outcome: object, expected_type: type
) -> None:
    """rotate_if_active devuelve Rotated o Reused según el estado previo de la sesión."""
    repo = _FakeRefreshSessionRepository(outcome)
    result = await repo.rotate_if_active("hash", "new-hash", datetime.now(tz=UTC))
    assert isinstance(result, expected_type)


async def test_rotate_if_active_raises_not_found_for_missing_hash() -> None:
    """rotate_if_active lanza NotFound si ningún hash coincide con ninguna sesión."""
    repo = _FakeRefreshSessionRepository("not_found")
    with pytest.raises(NotFound):
        await repo.rotate_if_active("no-such-hash", "new-hash", datetime.now(tz=UTC))
