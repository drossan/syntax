"""Tests de app.domain.services.auth_service (tarea backend-domain-services-06).

Nivel unit, con UserRepository/RefreshSessionRepository/AuthTokenRepository/EmailPort fakes en memoria.
Traza a CU-BE-01 (login/refresh/logout) y CU-BE-02 (reset/invitación). `app.core.security` se consume
como primitivas puras: `secret`/`ttl` se pasan como parámetros, el servicio no lee `get_settings()`.
"""

import dataclasses
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.core.security import hash_password
from app.core.security import hash_token as _hash_token
from app.domain.entities.enums import AuthTokenKind, RefreshSessionStatus, UserStatus
from app.domain.entities.identity import AuthToken, RefreshSession, User
from app.domain.errors import Conflict, NotFound, Validation
from app.domain.ports.repositories import Reused, Rotated
from app.domain.services.auth_service import (
    _AUTH_TOKEN_TTL_HOURS,
    _REFRESH_SESSION_TTL_DAYS,
    AuthResult,
    AuthService,
)

SECRET = "x" * 32
ALGORITHM = "HS256"
TTL = 900
_NOW = datetime(2026, 1, 1, tzinfo=UTC)
_TENANT = uuid.UUID(int=1)
_OTHER_TENANT = uuid.UUID(int=2)


class _FakeClock:
    def now(self) -> datetime:
        return _NOW


class _FakeEmailPort:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, dict[str, object]]] = []

    async def send(self, to: str, template: str, context: dict[str, object]) -> None:
        self.sent.append((to, template, context))


class _FakeUserRepository:
    def __init__(self) -> None:
        self.store: dict[uuid.UUID, User] = {}

    def seed(self, user: User) -> None:
        self.store[user.id] = user

    async def get(self, user_id: uuid.UUID) -> User | None:
        return self.store.get(user_id)

    async def get_by_email(self, tenant_id: uuid.UUID, email: str) -> User | None:
        for user in self.store.values():
            if user.tenant_id == tenant_id and user.email == email:
                return user
        return None

    async def add(self, user: User) -> User:
        self.store[user.id] = user
        return user

    async def update(self, user: User) -> User:
        self.store[user.id] = user
        return user


class _FakeRefreshSessionRepository:
    def __init__(self) -> None:
        self.store: dict[uuid.UUID, RefreshSession] = {}
        self.revoked_families: list[uuid.UUID] = []

    async def add(self, session: RefreshSession) -> RefreshSession:
        self.store[session.id] = session
        return session

    async def rotate_if_active(self, token_hash: str, new_token_hash: str, now: datetime) -> object:
        for session in self.store.values():
            if session.token_hash == token_hash:
                if session.status is not RefreshSessionStatus.active:
                    return Reused(family_id=session.family_id)
                rotated = RefreshSession(
                    id=uuid.uuid4(),
                    user_id=session.user_id,
                    token_hash=new_token_hash,
                    family_id=session.family_id,
                    parent_id=session.id,
                    status=RefreshSessionStatus.active,
                    expires_at=session.expires_at,
                )
                session.status = RefreshSessionStatus.rotated
                self.store[rotated.id] = rotated
                return Rotated(session=rotated)
        raise NotFound("no session", code="refresh.not_found")

    async def revoke_family(self, family_id: uuid.UUID) -> None:
        self.revoked_families.append(family_id)
        for session in self.store.values():
            if session.family_id == family_id:
                session.status = RefreshSessionStatus.revoked

    async def revoke(self, session_id: uuid.UUID) -> None:
        session = self.store.get(session_id)
        if session is not None:
            session.status = RefreshSessionStatus.revoked

    async def revoke_by_hash(self, token_hash: str) -> None:
        for session in self.store.values():
            if session.token_hash == token_hash:
                session.status = RefreshSessionStatus.revoked


class _FakeAuthTokenRepository:
    def __init__(self) -> None:
        self.store: dict[uuid.UUID, AuthToken] = {}

    async def add(self, token: AuthToken) -> AuthToken:
        self.store[token.id] = token
        return token

    async def get_by_token_hash(self, token_hash: str) -> AuthToken | None:
        for token in self.store.values():
            if token.token_hash == token_hash:
                return token
        return None

    async def mark_used(self, token_id: uuid.UUID, used_at: datetime) -> AuthToken:
        token = self.store[token_id]
        token.used_at = used_at
        return token


def _make_user(
    *,
    status: UserStatus = UserStatus.active,
    tenant_id: uuid.UUID = _TENANT,
    password_hash: str | None,
) -> User:
    return User(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        email="user@example.com",
        password_hash=password_hash,
        status=status,
    )


@pytest.fixture
def context() -> tuple:
    users = _FakeUserRepository()
    sessions = _FakeRefreshSessionRepository()
    tokens = _FakeAuthTokenRepository()
    email = _FakeEmailPort()
    svc = AuthService(
        users=users, refresh_sessions=sessions, auth_tokens=tokens, email=email, clock=_FakeClock()
    )
    return svc, users, sessions, tokens, email


def _kwargs() -> dict[str, object]:
    return {"secret": SECRET, "algorithm": ALGORITHM, "ttl": TTL}


async def test_login_with_valid_credentials_issues_access_and_refresh(context: tuple) -> None:
    """Login con credenciales válidas: access token + refresh session en cookie httpOnly (CU-BE-01)."""

    svc, users, sessions, *_ = context
    user = _make_user(password_hash=hash_password("correct-password"))
    users.seed(user)
    result = await svc.login(_TENANT, user.email, "correct-password", **_kwargs())
    assert result.access_token
    assert result.refresh_token
    assert len(sessions.store) == 1


async def test_login_with_invalid_password_is_rejected(context: tuple) -> None:
    """Login con contraseña incorrecta se rechaza con error genérico."""

    svc, users, *_ = context
    user = _make_user(password_hash=hash_password("correct-password"))
    users.seed(user)
    with pytest.raises(Validation):
        await svc.login(_TENANT, user.email, "wrong-password", **_kwargs())


@pytest.mark.parametrize("status", [UserStatus.invited, UserStatus.disabled])
async def test_login_with_non_active_user_is_rejected_like_invalid_credentials(
    context: tuple, status: UserStatus
) -> None:
    """Login con usuario no-active se rechaza con el MISMO error genérico."""

    svc, users, *_ = context
    user = _make_user(status=status, password_hash=hash_password("correct-password"))
    users.seed(user)
    with pytest.raises(Validation):
        await svc.login(_TENANT, user.email, "correct-password", **_kwargs())


@pytest.mark.parametrize(
    "attacker_tenant", [_OTHER_TENANT, uuid.UUID(int=0)]
)  # ambos órdenes relativos a _TENANT
async def test_login_with_wrong_tenant_is_rejected(
    context: tuple, attacker_tenant: uuid.UUID
) -> None:
    """Login con tenant_id que no corresponde al usuario se rechaza (no revela en qué tenant existe)."""
    svc, users, *_ = context
    user = _make_user(password_hash=hash_password("correct-password"))
    users.seed(user)
    with pytest.raises(Validation):
        await svc.login(attacker_tenant, user.email, "correct-password", **_kwargs())


async def test_login_with_same_value_different_object_tenant_succeeds(context: tuple) -> None:
    """tenant_id se compara por VALOR: un UUID reconstruido con el mismo valor no se rechaza."""
    svc, users, *_ = context
    user = _make_user(password_hash=hash_password("correct-password"))
    users.seed(user)
    same_value = uuid.UUID(str(_TENANT))
    assert same_value is not _TENANT
    result = await svc.login(same_value, user.email, "correct-password", **_kwargs())
    assert result.access_token


async def test_login_rejects_positional_secret(context: tuple) -> None:
    """secret/algorithm/ttl son keyword-only en login(): pasarlos por posición es TypeError."""
    svc, users, *_ = context
    user = _make_user(password_hash=hash_password("correct-password"))
    users.seed(user)
    with pytest.raises(TypeError):
        await svc.login(_TENANT, user.email, "correct-password", SECRET, ALGORITHM, TTL)  # type: ignore[misc]


async def test_refresh_rejects_positional_secret(context: tuple) -> None:
    """secret/algorithm/ttl son keyword-only en refresh(): pasarlos por posición es TypeError."""
    svc, *_ = context
    with pytest.raises(TypeError):
        await svc.refresh("any-token", SECRET, ALGORITHM, TTL)  # type: ignore[misc,call-arg]


async def test_refresh_rotates_and_issues_new_access(context: tuple) -> None:
    """Rotación del refresh: el anterior queda rotado, se emite un access nuevo."""

    svc, users, sessions, *_ = context
    user = _make_user(password_hash=hash_password("correct-password"))
    users.seed(user)
    login_result = await svc.login(_TENANT, user.email, "correct-password", **_kwargs())
    refreshed = await svc.refresh(login_result.refresh_token, **_kwargs())
    assert refreshed.access_token
    assert refreshed.refresh_token != login_result.refresh_token
    assert len(sessions.store) == 2  # original (rotated) + nueva


async def test_refresh_reuse_detection_revokes_family(context: tuple) -> None:
    """Reuse-detection: presentar un refresh ya rotado revoca TODA la family_id."""

    svc, users, sessions, *_ = context
    user = _make_user(password_hash=hash_password("correct-password"))
    users.seed(user)
    login_result = await svc.login(_TENANT, user.email, "correct-password", **_kwargs())
    await svc.refresh(login_result.refresh_token, **_kwargs())  # rota el original
    with pytest.raises(Conflict):
        await svc.refresh(login_result.refresh_token, **_kwargs())  # reuso del ya-rotado
    assert len(sessions.revoked_families) == 1


async def test_refresh_with_unknown_token_is_rejected(context: tuple) -> None:
    """Refresh con un token que no corresponde a ninguna sesión se rechaza."""
    svc, *_ = context
    with pytest.raises(Conflict):
        await svc.refresh("no-such-token", **_kwargs())


async def test_refresh_expired_session_rejects_without_reuse_detection(context: tuple) -> None:
    """Refresh caducado (activo pero expires_at pasado) se rechaza SIN revocar la family_id."""

    svc, users, sessions, *_ = context
    user = _make_user(password_hash=hash_password("correct-password"))
    users.seed(user)
    expired_session = RefreshSession(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=_hash_token("expired-token"),
        family_id=uuid.uuid4(),
        status=RefreshSessionStatus.active,
        expires_at=_NOW - timedelta(days=1),
    )
    await sessions.add(expired_session)
    with pytest.raises(Conflict):
        await svc.refresh("expired-token", **_kwargs())
    assert sessions.revoked_families == []  # no reuse-detection, solo expiración


async def test_logout_revokes_session_server_side(context: tuple) -> None:
    """Logout revoca la sesión server-side; un refresh posterior con ese token falla."""

    svc, users, sessions, *_ = context
    user = _make_user(password_hash=hash_password("correct-password"))
    users.seed(user)
    login_result = await svc.login(_TENANT, user.email, "correct-password", **_kwargs())
    await svc.logout(login_result.refresh_token)
    with pytest.raises(Conflict):
        await svc.refresh(login_result.refresh_token, **_kwargs())


async def test_forgot_password_for_existing_user_creates_token_and_sends_email(
    context: tuple,
) -> None:
    """Solicitud de reset: emite un token de un solo uso y notifica por el canal (stub)."""
    svc, users, _, tokens, email = context
    user = _make_user(password_hash="irrelevant")
    users.seed(user)
    await svc.forgot_password(_TENANT, user.email)
    assert len(tokens.store) == 1
    assert len(email.sent) == 1


async def test_forgot_password_for_nonexistent_email_behaves_the_same(context: tuple) -> None:
    """Reset para un email inexistente responde igual (no revela existencia): no lanza, no emite token."""
    svc, _, _, tokens, email = context
    await svc.forgot_password(_TENANT, "nobody@example.com")  # no debe lanzar
    assert len(tokens.store) == 0
    assert len(email.sent) == 0


async def test_reset_password_with_valid_token_sets_new_password(context: tuple) -> None:
    """Canje válido fija la contraseña y marca el token usado."""
    svc, users, _, tokens, email = context
    user = _make_user(password_hash="old-hash")
    users.seed(user)
    await svc.forgot_password(_TENANT, user.email)
    issued_token_entity = next(iter(tokens.store.values()))
    plaintext_token = email.sent[0][2]["token"]
    await svc.reset_password(plaintext_token, "new-password")
    assert tokens.store[issued_token_entity.id].used_at is not None
    assert users.store[user.id].password_hash != "old-hash"


@pytest.mark.parametrize(
    "corrupt",
    ["already-used", "expired", "wrong-kind"],
)
async def test_reset_password_with_unusable_token_is_rejected(context: tuple, corrupt: str) -> None:
    """Canje de un token inutilizable (caducado/usado/de otro kind) se rechaza — con el hash
    correcto, para que la condición ejercitada sea la específica de cada caso, no 'no encontrado'."""
    svc, users, _, tokens, _ = context
    user = _make_user(password_hash="old-hash")
    users.seed(user)
    plaintext = "plain-token"
    if corrupt == "already-used":
        token = AuthToken(
            id=uuid.uuid4(),
            user_id=user.id,
            kind=AuthTokenKind.password_reset,
            token_hash=_hash_token(plaintext),
            expires_at=_NOW + timedelta(hours=1),
            used_at=_NOW,
        )
    elif corrupt == "expired":
        token = AuthToken(
            id=uuid.uuid4(),
            user_id=user.id,
            kind=AuthTokenKind.password_reset,
            token_hash=_hash_token(plaintext),
            expires_at=_NOW - timedelta(hours=1),
        )
    else:
        token = AuthToken(
            id=uuid.uuid4(),
            user_id=user.id,
            kind=AuthTokenKind.invitation,
            token_hash=_hash_token(plaintext),
            expires_at=_NOW + timedelta(hours=1),
        )
    await tokens.add(token)
    with pytest.raises(Validation):
        await svc.reset_password(plaintext, "new-password")


async def test_reset_password_with_unknown_token_is_rejected(context: tuple) -> None:
    """Canje de un token que no corresponde a ningún AuthToken se rechaza igual (no revela nada)."""
    svc, *_ = context
    with pytest.raises(Validation):
        await svc.reset_password("never-issued", "new-password")


async def test_accept_invitation_activates_user(context: tuple) -> None:
    """Aceptar invitación fija contraseña y activa la cuenta (invited -> active)."""
    svc, users, _, tokens, email = context
    user = _make_user(status=UserStatus.invited, password_hash=None)
    users.seed(user)
    await svc.invite(user.id)
    sent_context = email.sent[0][2]
    await svc.accept_invitation(sent_context["token"], "new-password")
    assert users.store[user.id].status is UserStatus.active
    assert users.store[user.id].password_hash is not None


async def test_invite_already_active_user_is_rejected(context: tuple) -> None:
    """Invitar a un usuario ya activo se rechaza (Validation)."""
    svc, users, *_ = context
    user = _make_user(status=UserStatus.active, password_hash="x")
    users.seed(user)
    with pytest.raises(Validation):
        await svc.invite(user.id)


async def test_invite_nonexistent_user_is_rejected(context: tuple) -> None:
    """Invitar a un user_id que no existe se rechaza con NotFound (distinto de 'ya activo')."""
    svc, *_ = context
    with pytest.raises(NotFound):
        await svc.invite(uuid.uuid4())


def test_auth_result_is_immutable() -> None:
    """AuthResult es frozen: reasignar un campo lanza (contrato del dataclass)."""
    result = AuthResult(access_token="a", refresh_token="r")
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.access_token = "other"  # type: ignore[misc]


async def test_login_refresh_session_expires_in_configured_days(context: tuple) -> None:
    """La RefreshSession creada en login expira exactamente 14 días después (valor fijo, no
    derivado de la constante del propio módulo: así un NumberReplacer sobre ella se detecta)."""
    assert _REFRESH_SESSION_TTL_DAYS == 14
    svc, users, sessions, *_ = context
    user = _make_user(password_hash=hash_password("correct-password"))
    users.seed(user)
    await svc.login(_TENANT, user.email, "correct-password", **_kwargs())
    session = next(iter(sessions.store.values()))
    assert session.expires_at == _NOW + timedelta(days=14)


async def test_forgot_password_token_expires_in_configured_hours(context: tuple) -> None:
    """El AuthToken emitido por forgot_password expira exactamente 24h después (valor fijo, no
    derivado de la constante del propio módulo: así un NumberReplacer sobre ella se detecta)."""
    assert _AUTH_TOKEN_TTL_HOURS == 24
    svc, users, _, tokens, _ = context
    user = _make_user(password_hash="irrelevant")
    users.seed(user)
    await svc.forgot_password(_TENANT, user.email)
    issued = next(iter(tokens.store.values()))
    assert issued.expires_at == _NOW + timedelta(hours=24)


async def test_refresh_at_exact_expiry_boundary_is_rejected(context: tuple) -> None:
    """Frontera: expires_at == now se considera caducado (`<=`, no `<`)."""
    svc, users, sessions, *_ = context
    user = _make_user(password_hash=hash_password("correct-password"))
    users.seed(user)
    boundary_session = RefreshSession(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=_hash_token("boundary-token"),
        family_id=uuid.uuid4(),
        status=RefreshSessionStatus.active,
        expires_at=_NOW,
    )
    await sessions.add(boundary_session)
    with pytest.raises(Conflict):
        await svc.refresh("boundary-token", **_kwargs())


async def test_reset_password_at_exact_expiry_boundary_is_rejected(context: tuple) -> None:
    """Frontera en `_redeem_token`: expires_at == now se considera caducado (`<=`, no `<`)."""
    svc, users, _, tokens, _ = context
    user = _make_user(password_hash="old-hash")
    users.seed(user)
    plaintext = "boundary-reset-token"
    boundary_token = AuthToken(
        id=uuid.uuid4(),
        user_id=user.id,
        kind=AuthTokenKind.password_reset,
        token_hash=_hash_token(plaintext),
        expires_at=_NOW,
    )
    await tokens.add(boundary_token)
    with pytest.raises(Validation):
        await svc.reset_password(plaintext, "new-password")


class _CrossTenantLeakUserRepository:
    """Doble que simula un adaptador con bug: `get_by_email` NO filtra por `tenant_id` (el
    filtrado real vive en el adaptador SQL/RLS, no en el dominio). Prueba que `login()` tiene
    su propia defensa en profundidad comparando `user.tenant_id` contra el `tenant_id` recibido."""

    def __init__(self, user: User) -> None:
        self._user = user

    async def get(self, user_id: uuid.UUID) -> User | None:
        return self._user if user_id == self._user.id else None

    async def get_by_email(self, tenant_id: uuid.UUID, email: str) -> User | None:
        return self._user if email == self._user.email else None

    async def add(self, user: User) -> User:
        return user

    async def update(self, user: User) -> User:
        return user


@pytest.mark.parametrize("leaked_tenant", [uuid.UUID(int=0), _OTHER_TENANT])
async def test_login_rejects_when_port_leaks_user_from_another_tenant(
    leaked_tenant: uuid.UUID,
) -> None:
    """Defensa en profundidad: aunque el puerto devolviera (por bug) un user de otro tenant,
    login() lo rechaza igual — no confía ciegamente en que el adaptador ya filtró por tenant."""
    user = _make_user(password_hash=hash_password("correct-password"), tenant_id=leaked_tenant)
    svc = AuthService(
        users=_CrossTenantLeakUserRepository(user),
        refresh_sessions=_FakeRefreshSessionRepository(),
        auth_tokens=_FakeAuthTokenRepository(),
        email=_FakeEmailPort(),
        clock=_FakeClock(),
    )
    with pytest.raises(Validation):
        await svc.login(_TENANT, user.email, "correct-password", **_kwargs())
