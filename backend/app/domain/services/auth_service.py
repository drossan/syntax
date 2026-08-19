"""app.domain.services.auth_service — login multi-tenant en 2 pasos, sesiones, reset/invitación
(FR-001..009 ampliadas, CU-BE-01/02).

Identidad global desde el rediseño multi-tenant (backend-routers-core-01/02): `User` no lleva
`tenant_id`/`status` propios — el `email` es único global y una sola contraseña vale para todas las
membresías (`UserTenantMembership`) del usuario. `login()` ya no recibe `tenant_id`: cuenta las
membresías `active` en tenants no-`disabled`; si hay 2+, emite un `identity_token` corto
(`purpose=tenant_selection`, sin refresh-cookie) en vez de tokens reales — `select_tenant()` lo
canjea. `switch_tenant()` hace lo mismo mismo pero partiendo de un access token ya válido (cambiar de
tenant sin re-login). `app.core.security` se consume como **primitivas puras adyacentes al dominio**:
`secret`/`algorithm`/`ttl` llegan como parámetros del llamante, el servicio nunca lee
`get_settings()`. `refresh()` usa `RefreshSessionRepository.rotate_if_active` (CAS) para evitar el
check-then-act; `Reused`/hash-no-encontrado comparten el mismo rechazo genérico, pero una sesión
`active` con `expires_at` pasado es una rama propia (expiración natural, sin reuse-detection).
"""

import uuid
from dataclasses import dataclass
from datetime import timedelta

import jwt

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    hash_token,
    new_opaque_token,
    verify_password,
)
from app.domain.entities.enums import AuthTokenKind, RefreshSessionStatus, TenantStatus, UserStatus
from app.domain.entities.identity import (
    AuthToken,
    RefreshSession,
    Tenant,
    User,
    UserTenantMembership,
)
from app.domain.errors import Conflict, NotFound, Validation
from app.domain.ports.clock import Clock
from app.domain.ports.email import EmailPort
from app.domain.ports.repositories import (
    AuthTokenRepository,
    Reused,
    RotationOutcome,
    TenantRepository,
    UserRepository,
    UserTenantMembershipRepository,
)
from app.domain.ports.repositories import RefreshSessionRepository as RefreshSessionRepositoryPort

_REFRESH_SESSION_TTL_DAYS = 14
_AUTH_TOKEN_TTL_HOURS = 24
_IDENTITY_TOKEN_TTL_SECONDS = 300
_IDENTITY_TOKEN_PURPOSE = "tenant_selection"  # noqa: S105 — claim `purpose`, no un secreto
_ACCESS_TOKEN_PURPOSE = "access"  # noqa: S105 — claim `purpose`, no un secreto


@dataclass(frozen=True)
class AuthResult:
    """Resultado con tokens reales: access token (Bearer) + refresh token opaco (cookie httpOnly)."""

    access_token: str
    refresh_token: str


@dataclass(frozen=True)
class TenantChoice:
    """Un tenant elegible para seleccionar en el paso 2 del login (identity_token)."""

    tenant_id: uuid.UUID
    slug: str
    name: str


@dataclass(frozen=True)
class IdentitySelection:
    """Login con 2+ membresías activas: hay que elegir tenant antes de tokens reales (sin
    refresh-cookie todavía)."""

    identity_token: str
    tenants: list[TenantChoice]


LoginOutcome = AuthResult | IdentitySelection
"""`login()` devuelve tokens reales (1 tenant elegible) o una selección pendiente (2+)."""


def _generic_credentials_error() -> Validation:
    """Error genérico: no revela cuál de las condiciones falló (email/password/membership/tenant)."""
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
        memberships: UserTenantMembershipRepository,
        tenants: TenantRepository,
        refresh_sessions: RefreshSessionRepositoryPort,
        auth_tokens: AuthTokenRepository,
        email: EmailPort,
        clock: Clock,
    ) -> None:
        self._users = users
        self._memberships = memberships
        self._tenants = tenants
        self._refresh_sessions = refresh_sessions
        self._auth_tokens = auth_tokens
        self._email = email
        self._clock = clock

    async def login(
        self, email: str, password: str, *, secret: str, algorithm: str, ttl: int
    ) -> LoginOutcome:
        """Verifica credenciales (email normalizado, global); cuenta membresías `active` en tenants
        no-`disabled`: 0 → error genérico; 1 → tokens reales; 2+ → `identity_token` corto."""
        user = await self._users.get_by_email(email.strip().lower())
        if (
            user is None
            or user.password_hash is None
            or not verify_password(password, user.password_hash)
        ):
            raise _generic_credentials_error()

        eligible = await self._eligible_memberships(user.id)
        if not eligible:
            raise _generic_credentials_error()
        if len(eligible) == 1:
            (_, tenant) = eligible[0]
            return await self._issue_tokens(
                user, tenant.id, secret=secret, algorithm=algorithm, ttl=ttl
            )

        now = self._clock.now()
        identity_token = create_access_token(
            str(user.id),
            None,
            secret=secret,
            algorithm=algorithm,
            ttl=_IDENTITY_TOKEN_TTL_SECONDS,
            now=now,
            purpose=_IDENTITY_TOKEN_PURPOSE,
        )
        choices = [
            TenantChoice(tenant_id=tenant.id, slug=tenant.slug, name=tenant.name)
            for _, tenant in eligible
        ]
        return IdentitySelection(identity_token=identity_token, tenants=choices)

    async def select_tenant(
        self, identity_token: str, tenant_id: uuid.UUID, *, secret: str, algorithm: str, ttl: int
    ) -> AuthResult:
        """Canjea un `identity_token` (`purpose=tenant_selection`, reutilizable dentro de su TTL) por
        el `TokenResponse` real, si la membership de ese tenant sigue `active` y el tenant no `disabled`."""
        user_id = self._decode_subject(
            identity_token,
            secret=secret,
            algorithm=algorithm,
            expected_purpose=_IDENTITY_TOKEN_PURPOSE,
        )
        return await self._issue_tokens_for_selected_tenant(
            user_id, tenant_id, secret=secret, algorithm=algorithm, ttl=ttl
        )

    async def switch_tenant(
        self, access_token: str, tenant_id: uuid.UUID, *, secret: str, algorithm: str, ttl: int
    ) -> AuthResult:
        """Cambia de tenant con una sesión ya autenticada (access token válido), sin repetir
        credenciales — mismas validaciones de membership `active` + tenant no-`disabled`."""
        user_id = self._decode_subject(
            access_token, secret=secret, algorithm=algorithm, expected_purpose=_ACCESS_TOKEN_PURPOSE
        )
        return await self._issue_tokens_for_selected_tenant(
            user_id, tenant_id, secret=secret, algorithm=algorithm, ttl=ttl
        )

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
            str(user.id),
            str(session.tenant_id),
            secret=secret,
            algorithm=algorithm,
            ttl=ttl,
            now=now,
        )
        return AuthResult(access_token=access, refresh_token=new_plaintext)

    async def logout(self, token: str) -> None:
        """Revoca la sesión server-side (no depende de que el cliente borre la cookie)."""
        await self._refresh_sessions.revoke_by_hash(hash_token(token))

    async def forgot_password(self, email: str) -> None:
        """Siempre responde igual; si el usuario existe, emite `AuthToken` y notifica (stub)."""
        user = await self._users.get_by_email(email.strip().lower())
        if user is None:
            return
        await self._issue_auth_token(user, AuthTokenKind.password_reset, "password_reset")

    async def reset_password(self, token: str, new_password: str) -> None:
        """Canjea un `AuthToken(password_reset)` no caducado/no usado; fija la contraseña global."""
        auth_token = await self._redeem_token(token, AuthTokenKind.password_reset)
        user = await self._users.get(auth_token.user_id)
        if user is None:
            raise _unusable_token_error()
        user.password_hash = hash_password(new_password)
        await self._users.update(user)
        await self._auth_tokens.mark_used(auth_token.id, self._clock.now())

    async def change_password(
        self, user_id: uuid.UUID, current_password: str, new_password: str
    ) -> None:
        """Cambia la contraseña global verificando la actual; no la toca si no coincide."""
        user = await self._users.get(user_id)
        if (
            user is None
            or user.password_hash is None
            or not verify_password(current_password, user.password_hash)
        ):
            raise Validation("contraseña actual incorrecta", code="auth.invalid_current_password")
        user.password_hash = hash_password(new_password)
        await self._users.update(user)

    async def invite(self, tenant_id: uuid.UUID, email: str) -> None:
        """Invita un email a un tenant: si ya existe como `User` global, crea solo la membership
        `invited` (sin tocar su password); si no existe, crea el `User` (sin password) + membership.
        Reinvitar un email ya `active` en ESE MISMO tenant se rechaza (`Conflict`)."""
        normalized_email = email.strip().lower()
        user = await self._users.get_by_email(normalized_email)
        if user is None:
            user = await self._users.add(
                User(id=uuid.uuid4(), email=normalized_email, password_hash=None)
            )
        else:
            existing = await self._memberships.get(user.id, tenant_id)
            if existing is not None and existing.status is UserStatus.active:
                raise Conflict(
                    "el usuario ya está activo en este tenant", code="auth.already_active"
                )
        membership = UserTenantMembership(
            user_id=user.id, tenant_id=tenant_id, status=UserStatus.invited
        )
        await self._memberships.add(membership)
        await self._issue_auth_token(user, AuthTokenKind.invitation, "invitation")

    async def accept_invitation(self, token: str, password: str) -> None:
        """Canjea un `AuthToken(invitation)`: fija la contraseña GLOBAL (afecta a todas las
        membresías) y activa la(s) membership(s) `invited` del usuario — el `auth_token` no referencia
        un tenant concreto (limitación conocida: con invitaciones simultáneas a varios tenants, activa
        todas las que sigan `invited`, no solo la del token)."""
        auth_token = await self._redeem_token(token, AuthTokenKind.invitation)
        user = await self._users.get(auth_token.user_id)
        if user is None:
            raise _unusable_token_error()
        user.password_hash = hash_password(password)
        await self._users.update(user)
        for membership in await self._memberships.list_by_user(user.id):
            if membership.status is UserStatus.invited:
                membership.status = UserStatus.active
                await self._memberships.update(membership)
        await self._auth_tokens.mark_used(auth_token.id, self._clock.now())

    async def _eligible_memberships(
        self, user_id: uuid.UUID
    ) -> list[tuple[UserTenantMembership, Tenant]]:
        """Membresías `active` cuyo tenant NO está `disabled` (una membership `active` de un tenant
        deshabilitado no cuenta, scenario-coverage)."""
        eligible: list[tuple[UserTenantMembership, Tenant]] = []
        for membership in await self._memberships.list_by_user(user_id):
            if membership.status is not UserStatus.active:
                continue
            tenant = await self._tenants.get(membership.tenant_id)
            if tenant is None or tenant.status is TenantStatus.disabled:
                continue
            eligible.append((membership, tenant))
        return eligible

    def _decode_subject(
        self, token: str, *, secret: str, algorithm: str, expected_purpose: str
    ) -> uuid.UUID:
        """Decodifica un token exigiendo su `purpose`; cualquier fallo → el mismo error genérico."""
        try:
            claims = decode_access_token(
                token, secret=secret, algorithm=algorithm, now=self._clock.now()
            )
        except jwt.InvalidTokenError as exc:
            raise _generic_credentials_error() from exc
        if claims.get("purpose") != expected_purpose:
            raise _generic_credentials_error()
        return uuid.UUID(claims["sub"])

    async def _issue_tokens_for_selected_tenant(
        self, user_id: uuid.UUID, tenant_id: uuid.UUID, *, secret: str, algorithm: str, ttl: int
    ) -> AuthResult:
        membership = await self._memberships.get(user_id, tenant_id)
        tenant = await self._tenants.get(tenant_id)
        if (
            membership is None
            or membership.status is not UserStatus.active
            or tenant is None
            or tenant.status is TenantStatus.disabled
        ):
            raise _generic_credentials_error()
        user = await self._users.get(user_id)
        if user is None:
            raise _generic_credentials_error()
        return await self._issue_tokens(
            user, tenant_id, secret=secret, algorithm=algorithm, ttl=ttl
        )

    async def _issue_tokens(
        self, user: User, tenant_id: uuid.UUID, *, secret: str, algorithm: str, ttl: int
    ) -> AuthResult:
        now = self._clock.now()
        plaintext = new_opaque_token()
        session = RefreshSession(
            id=uuid.uuid4(),
            user_id=user.id,
            tenant_id=tenant_id,
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
