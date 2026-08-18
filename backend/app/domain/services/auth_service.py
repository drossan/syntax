"""app.domain.services.auth_service — login, refresh, reset/invitación (FR-001..009, CU-BE-01/02).

`app.core.security` se consume como **primitivas puras adyacentes al dominio**: `secret`/`algorithm`/
`ttl` llegan como parámetros del llamante (futuro `deps`), el servicio nunca lee `get_settings()`
(decisión de design-review). `refresh()` usa `RefreshSessionRepository.rotate_if_active` (CAS) para
evitar el check-then-act; `Reused`/hash-no-encontrado comparten el mismo rechazo genérico, pero una
sesión `active` con `expires_at` pasado es una rama propia (expiración natural, sin reuse-detection).
"""

import uuid
from dataclasses import dataclass
from datetime import timedelta

from app.core.security import (
    create_access_token,
    hash_password,
    hash_token,
    new_opaque_token,
    verify_password,
)
from app.domain.entities.enums import AuthTokenKind, RefreshSessionStatus, UserStatus
from app.domain.entities.identity import AuthToken, RefreshSession, User
from app.domain.errors import Conflict, NotFound, Validation
from app.domain.ports.clock import Clock
from app.domain.ports.email import EmailPort
from app.domain.ports.repositories import (
    AuthTokenRepository,
    Reused,
    RotationOutcome,
    UserRepository,
)
from app.domain.ports.repositories import RefreshSessionRepository as RefreshSessionRepositoryPort

_REFRESH_SESSION_TTL_DAYS = 14
_AUTH_TOKEN_TTL_HOURS = 24


@dataclass(frozen=True)
class AuthResult:
    """Resultado de `login`/`refresh`: access token (Bearer) + refresh token opaco (cookie httpOnly)."""

    access_token: str
    refresh_token: str


def _generic_credentials_error() -> Validation:
    """Error genérico de login: no revela cuál de las condiciones falló (email/password/status/tenant)."""
    return Validation("credenciales inválidas", code="auth.invalid_credentials")


def _generic_refresh_error() -> Conflict:
    """Error genérico de refresh: no distingue 'no existe' de 'ya reusado' en la respuesta."""
    return Conflict("refresh inválido", code="auth.invalid_refresh")


def _expired_refresh_error() -> Conflict:
    """Refresh expirado por el paso del tiempo (no reuso): rama propia, exige re-login."""
    return Conflict("la sesión ha expirado, inicia sesión de nuevo", code="auth.refresh_expired")


def _unusable_token_error() -> Validation:
    """Token de un solo uso (reset/invitación) inválido/caducado/usado/de otro kind."""
    return Validation("token inválido o caducado", code="auth.unusable_token")


class AuthService:
    """Servicio de dominio de autenticación. Puertos por inyección de constructor."""

    def __init__(
        self,
        users: UserRepository,
        refresh_sessions: RefreshSessionRepositoryPort,
        auth_tokens: AuthTokenRepository,
        email: EmailPort,
        clock: Clock,
    ) -> None:
        self._users = users
        self._refresh_sessions = refresh_sessions
        self._auth_tokens = auth_tokens
        self._email = email
        self._clock = clock

    async def login(
        self,
        tenant_id: uuid.UUID,
        email: str,
        password: str,
        *,
        secret: str,
        algorithm: str,
        ttl: int,
    ) -> AuthResult:
        """Verifica credenciales; emite access + crea una `RefreshSession` (nueva `family_id`)."""
        user = await self._users.get_by_email(tenant_id, email)
        if (
            user is None
            or user.tenant_id != tenant_id
            or user.status is not UserStatus.active
            or user.password_hash is None
            or not verify_password(password, user.password_hash)
        ):
            raise _generic_credentials_error()

        now = self._clock.now()
        plaintext = new_opaque_token()
        session = RefreshSession(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=hash_token(plaintext),
            family_id=uuid.uuid4(),
            status=RefreshSessionStatus.active,
            expires_at=now + timedelta(days=_REFRESH_SESSION_TTL_DAYS),
        )
        await self._refresh_sessions.add(session)
        access = create_access_token(
            str(user.id), str(tenant_id), secret=secret, algorithm=algorithm, ttl=ttl, now=now
        )
        return AuthResult(access_token=access, refresh_token=plaintext)

    async def refresh(self, token: str, *, secret: str, algorithm: str, ttl: int) -> AuthResult:
        """CAS: rota si la sesión seguía activa; reuse-detection revoca la familia; expirado ≠ reusado."""
        now = self._clock.now()
        new_plaintext = new_opaque_token()
        try:
            outcome: RotationOutcome = await self._refresh_sessions.rotate_if_active(
                hash_token(token), hash_token(new_plaintext), now
            )
        except NotFound:
            raise _generic_refresh_error() from None

        if isinstance(outcome, Reused):
            await self._refresh_sessions.revoke_family(outcome.family_id)
            raise _generic_refresh_error()

        session = outcome.session
        if session.expires_at <= now:
            raise _expired_refresh_error()

        user = await self._users.get(session.user_id)
        if user is None:
            raise _generic_refresh_error()
        access = create_access_token(
            str(user.id), str(user.tenant_id), secret=secret, algorithm=algorithm, ttl=ttl, now=now
        )
        return AuthResult(access_token=access, refresh_token=new_plaintext)

    async def logout(self, token: str) -> None:
        """Revoca la sesión server-side (no depende de que el cliente borre la cookie)."""
        await self._refresh_sessions.revoke_by_hash(hash_token(token))

    async def forgot_password(self, tenant_id: uuid.UUID, email: str) -> None:
        """Siempre responde igual; si el usuario existe, emite `AuthToken` y notifica (stub)."""
        user = await self._users.get_by_email(tenant_id, email)
        if user is None:
            return
        await self._issue_auth_token(user, AuthTokenKind.password_reset, "password_reset")

    async def reset_password(self, token: str, new_password: str) -> None:
        """Canjea un `AuthToken(password_reset)` no caducado/no usado; fija la contraseña."""
        auth_token = await self._redeem_token(token, AuthTokenKind.password_reset)
        user = await self._users.get(auth_token.user_id)
        if user is None:
            raise _unusable_token_error()
        user.password_hash = hash_password(new_password)
        await self._users.update(user)
        await self._auth_tokens.mark_used(auth_token.id, self._clock.now())

    async def invite(self, user_id: uuid.UUID) -> None:
        """Emite `AuthToken(invitation)` para un usuario no-activo; reinvitar a uno activo se rechaza."""
        user = await self._users.get(user_id)
        if user is None:
            raise NotFound(f"user {user_id} no existe", code="auth.user_not_found")
        if user.status is UserStatus.active:
            raise Validation("el usuario ya está activo", code="auth.already_active")
        await self._issue_auth_token(user, AuthTokenKind.invitation, "invitation")

    async def accept_invitation(self, token: str, password: str) -> None:
        """Canjea un `AuthToken(invitation)`; fija la contraseña y activa la cuenta."""
        auth_token = await self._redeem_token(token, AuthTokenKind.invitation)
        user = await self._users.get(auth_token.user_id)
        if user is None:
            raise _unusable_token_error()
        user.password_hash = hash_password(password)
        user.status = UserStatus.active
        await self._users.update(user)
        await self._auth_tokens.mark_used(auth_token.id, self._clock.now())

    async def _issue_auth_token(self, user: User, kind: AuthTokenKind, template: str) -> None:
        plaintext = new_opaque_token()
        auth_token = AuthToken(
            id=uuid.uuid4(),
            user_id=user.id,
            kind=kind,
            token_hash=hash_token(plaintext),
            expires_at=self._clock.now() + timedelta(hours=_AUTH_TOKEN_TTL_HOURS),
        )
        await self._auth_tokens.add(auth_token)
        await self._email.send(user.email, template, {"token": plaintext})

    async def _redeem_token(self, token: str, kind: AuthTokenKind) -> AuthToken:
        auth_token = await self._auth_tokens.get_by_token_hash(hash_token(token))
        now = self._clock.now()
        if (
            auth_token is None
            or auth_token.kind is not kind
            or auth_token.used_at is not None
            or auth_token.expires_at <= now
        ):
            raise _unusable_token_error()
        return auth_token
