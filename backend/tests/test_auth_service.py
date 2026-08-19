"""Tests de app.domain.services.auth_service (backend-routers-core-02, reescritura sobre identidad
multi-tenant global de backend-routers-core-01).

Nivel unit, con fakes en memoria de UserRepository/UserTenantMembershipRepository/TenantRepository/
RefreshSessionRepository/AuthTokenRepository/EmailPort. Traza a CU-BE-01 (login 2 pasos/sesiones) y
CU-BE-02 (reset/invitación/change_password). `app.core.security` se consume como primitivas puras:
`secret`/`ttl` se pasan como parámetros, el servicio no lee `get_settings()`.
"""

import dataclasses
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.core.security import hash_password
from app.core.security import hash_token as _hash_token
from app.domain.entities.enums import AuthTokenKind, RefreshSessionStatus, TenantStatus, UserStatus
from app.domain.entities.identity import (
    AuthToken,
    RefreshSession,
    Tenant,
    User,
    UserTenantMembership,
)
from app.domain.errors import Conflict, NotFound, Validation
from app.domain.ports.repositories import Reused, Rotated
from app.domain.services.auth_service import (
    _AUTH_TOKEN_TTL_HOURS,
    _IDENTITY_TOKEN_TTL_SECONDS,
    _REFRESH_SESSION_TTL_DAYS,
    AuthResult,
    AuthService,
    IdentitySelection,
    TenantChoice,
)

SECRET = "x" * 32
ALGORITHM = "HS256"
TTL = 900
_NOW = datetime(2026, 1, 1, tzinfo=UTC)
_TENANT_A = uuid.UUID(int=1)
_TENANT_B = uuid.UUID(int=2)
_TENANT_C = uuid.UUID(int=3)


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

    async def get_by_email(self, email: str) -> User | None:
        for user in self.store.values():
            if user.email == email:
                return user
        return None

    async def add(self, user: User) -> User:
        self.store[user.id] = user
        return user

    async def update(self, user: User) -> User:
        self.store[user.id] = user
        return user


class _FakeTenantRepository:
    def __init__(self) -> None:
        self.store: dict[uuid.UUID, Tenant] = {}

    def seed(self, tenant: Tenant) -> None:
        self.store[tenant.id] = tenant

    async def get(self, tenant_id: uuid.UUID) -> Tenant | None:
        return self.store.get(tenant_id)

    async def add(self, tenant: Tenant) -> Tenant:
        self.store[tenant.id] = tenant
        return tenant


class _FakeMembershipRepository:
    def __init__(self) -> None:
        self.store: dict[tuple[uuid.UUID, uuid.UUID], UserTenantMembership] = {}

    def seed(self, membership: UserTenantMembership) -> None:
        self.store[(membership.user_id, membership.tenant_id)] = membership

    async def get(self, user_id: uuid.UUID, tenant_id: uuid.UUID) -> UserTenantMembership | None:
        return self.store.get((user_id, tenant_id))

    async def list_for_user(self, user_id: uuid.UUID) -> list[UserTenantMembership]:
        return [m for (uid, _), m in self.store.items() if uid == user_id]

    async def add(self, membership: UserTenantMembership) -> UserTenantMembership:
        self.store[(membership.user_id, membership.tenant_id)] = membership
        return membership

    async def update(self, membership: UserTenantMembership) -> UserTenantMembership:
        self.store[(membership.user_id, membership.tenant_id)] = membership
        return membership


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
                    tenant_id=session.tenant_id,
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


def _make_tenant(
    tenant_id: uuid.UUID,
    *,
    status: TenantStatus = TenantStatus.active,
    slug: str = "t",
    name: str = "T",
) -> Tenant:
    return Tenant(id=tenant_id, slug=f"{slug}-{tenant_id}", name=name, status=status)


def _make_user(*, email: str = "user@example.com", password_hash: str | None) -> User:
    return User(id=uuid.uuid4(), email=email, password_hash=password_hash)


def _make_membership(
    user_id: uuid.UUID, tenant_id: uuid.UUID, *, status: UserStatus = UserStatus.active
) -> UserTenantMembership:
    return UserTenantMembership(user_id=user_id, tenant_id=tenant_id, status=status)


@pytest.fixture
def context() -> tuple:
    users = _FakeUserRepository()
    memberships = _FakeMembershipRepository()
    tenants = _FakeTenantRepository()
    sessions = _FakeRefreshSessionRepository()
    tokens = _FakeAuthTokenRepository()
    email = _FakeEmailPort()
    svc = AuthService(
        users=users,
        memberships=memberships,
        tenants=tenants,
        refresh_sessions=sessions,
        auth_tokens=tokens,
        email=email,
        clock=_FakeClock(),
    )
    return svc, users, memberships, tenants, sessions, tokens, email


def _kwargs() -> dict[str, object]:
    return {"secret": SECRET, "algorithm": ALGORITHM, "ttl": TTL}


def _seed_single_active_membership(
    context: tuple,
    *,
    password: str = "correct-password",  # noqa: S107 — fixture de test, no un secreto
) -> User:
    svc, users, memberships, tenants, *_ = context
    user = _make_user(password_hash=hash_password(password))
    users.seed(user)
    tenants.seed(_make_tenant(_TENANT_A))
    memberships.seed(_make_membership(user.id, _TENANT_A))
    return user


async def test_login_with_one_active_membership_issues_tokens_directly(context: tuple) -> None:
    """Login con UNA membership active emite un TokenResponse (access + refresh-cookie), CU-BE-01."""
    svc, *_ = context
    user = _seed_single_active_membership(context)
    result = await svc.login(user.email, "correct-password", **_kwargs())
    assert isinstance(result, AuthResult)
    assert result.access_token
    assert result.refresh_token


async def test_login_with_invalid_password_is_rejected(context: tuple) -> None:
    """Login con contraseña incorrecta se rechaza con error genérico."""
    svc, *_ = context
    user = _seed_single_active_membership(context)
    with pytest.raises(Validation):
        await svc.login(user.email, "wrong-password", **_kwargs())


async def test_login_with_unknown_email_is_rejected_like_invalid_credentials(
    context: tuple,
) -> None:
    """Login con un email que no existe se rechaza igual (no revela existencia)."""
    svc, *_ = context
    with pytest.raises(Validation):
        await svc.login("nobody@example.com", "whatever", **_kwargs())


async def test_login_with_two_active_memberships_issues_identity_token_not_real_tokens(
    context: tuple,
) -> None:
    """Login con DOS membresías active en tenants distintos emite identity_token + lista de
    tenants, SIN refresh-cookie (sin RefreshSession creada)."""
    svc, users, memberships, tenants, sessions, *_ = context
    user = _make_user(password_hash=hash_password("correct-password"))
    users.seed(user)
    tenants.seed(_make_tenant(_TENANT_A, slug="a"))
    tenants.seed(_make_tenant(_TENANT_B, slug="b"))
    memberships.seed(_make_membership(user.id, _TENANT_A))
    memberships.seed(_make_membership(user.id, _TENANT_B))

    result = await svc.login(user.email, "correct-password", **_kwargs())

    assert isinstance(result, IdentitySelection)
    assert result.identity_token
    assert {t.tenant_id for t in result.tenants} == {_TENANT_A, _TENANT_B}
    assert len(sessions.store) == 0


async def test_login_with_no_active_membership_is_rejected_like_invalid_credentials(
    context: tuple,
) -> None:
    """Login sin ninguna membership active se rechaza con el mismo error genérico."""
    svc, users, memberships, tenants, *_ = context
    user = _make_user(password_hash=hash_password("correct-password"))
    users.seed(user)
    tenants.seed(_make_tenant(_TENANT_A))
    memberships.seed(_make_membership(user.id, _TENANT_A, status=UserStatus.invited))
    with pytest.raises(Validation):
        await svc.login(user.email, "correct-password", **_kwargs())


async def test_login_with_mixed_membership_states_only_counts_active(context: tuple) -> None:
    """Membership active en A, invited en B, disabled en C: se comporta como 'una sola active'."""
    svc, users, memberships, tenants, *_ = context
    user = _make_user(password_hash=hash_password("correct-password"))
    users.seed(user)
    tenants.seed(_make_tenant(_TENANT_A))
    tenants.seed(_make_tenant(_TENANT_B))
    tenants.seed(_make_tenant(_TENANT_C))
    memberships.seed(_make_membership(user.id, _TENANT_A, status=UserStatus.active))
    memberships.seed(_make_membership(user.id, _TENANT_B, status=UserStatus.invited))
    memberships.seed(_make_membership(user.id, _TENANT_C, status=UserStatus.disabled))

    result = await svc.login(user.email, "correct-password", **_kwargs())

    assert isinstance(result, AuthResult)


async def test_login_ignores_active_membership_in_a_disabled_tenant(context: tuple) -> None:
    """Una membership active en un tenant disabled no cuenta; si era la única, se rechaza."""
    svc, users, memberships, tenants, *_ = context
    user = _make_user(password_hash=hash_password("correct-password"))
    users.seed(user)
    tenants.seed(_make_tenant(_TENANT_A, status=TenantStatus.disabled))
    memberships.seed(_make_membership(user.id, _TENANT_A))

    with pytest.raises(Validation):
        await svc.login(user.email, "correct-password", **_kwargs())


async def test_login_skips_a_non_active_membership_seen_before_the_eligible_one(
    context: tuple,
) -> None:
    """Una membership NO active vista ANTES de la elegible se SALTA, no corta la búsqueda: el
    filtrado sigue examinando el resto (mutation-kill: `continue` vs `break`)."""
    svc, users, memberships, tenants, *_ = context
    user = _make_user(password_hash=hash_password("correct-password"))
    users.seed(user)
    tenants.seed(_make_tenant(_TENANT_B))
    tenants.seed(_make_tenant(_TENANT_A))
    memberships.seed(_make_membership(user.id, _TENANT_B, status=UserStatus.invited))
    memberships.seed(_make_membership(user.id, _TENANT_A, status=UserStatus.active))

    result = await svc.login(user.email, "correct-password", **_kwargs())

    assert isinstance(result, AuthResult)


async def test_login_skips_a_disabled_tenant_membership_seen_before_the_eligible_one(
    context: tuple,
) -> None:
    """Una membership active de un tenant disabled vista ANTES de la elegible se SALTA, no corta
    la búsqueda (mutation-kill: `continue` vs `break`)."""
    svc, users, memberships, tenants, *_ = context
    user = _make_user(password_hash=hash_password("correct-password"))
    users.seed(user)
    tenants.seed(_make_tenant(_TENANT_B, status=TenantStatus.disabled))
    tenants.seed(_make_tenant(_TENANT_A))
    memberships.seed(_make_membership(user.id, _TENANT_B, status=UserStatus.active))
    memberships.seed(_make_membership(user.id, _TENANT_A, status=UserStatus.active))

    result = await svc.login(user.email, "correct-password", **_kwargs())

    assert isinstance(result, AuthResult)


async def test_login_rejects_positional_secret(context: tuple) -> None:
    """secret/algorithm/ttl son keyword-only en login(): pasarlos por posición es TypeError."""
    svc, *_ = context
    user = _seed_single_active_membership(context)
    with pytest.raises(TypeError):
        await svc.login(user.email, "correct-password", SECRET, ALGORITHM, TTL)  # type: ignore[misc]


async def test_select_tenant_with_active_membership_issues_real_tokens(context: tuple) -> None:
    """select_tenant con una membership active del identity_token emite el TokenResponse real."""
    svc, users, memberships, tenants, *_ = context
    user = _make_user(password_hash=hash_password("correct-password"))
    users.seed(user)
    tenants.seed(_make_tenant(_TENANT_A, slug="a"))
    tenants.seed(_make_tenant(_TENANT_B, slug="b"))
    memberships.seed(_make_membership(user.id, _TENANT_A))
    memberships.seed(_make_membership(user.id, _TENANT_B))
    selection = await svc.login(user.email, "correct-password", **_kwargs())
    assert isinstance(selection, IdentitySelection)

    result = await svc.select_tenant(selection.identity_token, _TENANT_A, **_kwargs())

    assert isinstance(result, AuthResult)
    assert result.access_token


async def test_select_tenant_rejects_positional_secret(context: tuple) -> None:
    """secret/algorithm/ttl son keyword-only en select_tenant(): pasarlos por posición es TypeError."""
    svc, *_ = context
    with pytest.raises(TypeError):
        await svc.select_tenant("any-token", _TENANT_A, SECRET, ALGORITHM, TTL)  # type: ignore[misc]


async def test_select_tenant_with_tenant_outside_memberships_is_rejected(context: tuple) -> None:
    """select_tenant con un tenant fuera de las membresías del usuario se rechaza."""
    svc, users, memberships, tenants, *_ = context
    user = _make_user(password_hash=hash_password("correct-password"))
    users.seed(user)
    tenants.seed(_make_tenant(_TENANT_A, slug="a"))
    tenants.seed(_make_tenant(_TENANT_B, slug="b"))
    memberships.seed(_make_membership(user.id, _TENANT_A))
    memberships.seed(_make_membership(user.id, _TENANT_B))
    selection = await svc.login(user.email, "correct-password", **_kwargs())
    assert isinstance(selection, IdentitySelection)

    with pytest.raises(Validation):
        await svc.select_tenant(selection.identity_token, _TENANT_C, **_kwargs())


async def test_select_tenant_with_non_active_membership_is_rejected(context: tuple) -> None:
    """select_tenant con una membership invited (no active) se rechaza."""
    svc, users, memberships, tenants, *_ = context
    user = _make_user(password_hash=hash_password("correct-password"))
    users.seed(user)
    tenants.seed(_make_tenant(_TENANT_A, slug="a"))
    tenants.seed(_make_tenant(_TENANT_B, slug="b"))
    tenants.seed(_make_tenant(_TENANT_C, slug="c"))
    memberships.seed(_make_membership(user.id, _TENANT_A))
    memberships.seed(_make_membership(user.id, _TENANT_C))
    memberships.seed(_make_membership(user.id, _TENANT_B, status=UserStatus.invited))
    selection = await svc.login(user.email, "correct-password", **_kwargs())
    assert isinstance(selection, IdentitySelection)

    with pytest.raises(Validation):
        await svc.select_tenant(selection.identity_token, _TENANT_B, **_kwargs())


async def test_select_tenant_with_expired_identity_token_is_rejected(context: tuple) -> None:
    """select_tenant con un identity_token cuyo TTL ya pasó se rechaza con el error genérico."""
    svc, users, memberships, tenants, sessions, tokens, email = context
    user = _make_user(password_hash=hash_password("correct-password"))
    users.seed(user)
    tenants.seed(_make_tenant(_TENANT_A, slug="a"))
    tenants.seed(_make_tenant(_TENANT_B, slug="b"))
    memberships.seed(_make_membership(user.id, _TENANT_A))
    memberships.seed(_make_membership(user.id, _TENANT_B))

    class _LateClock:
        def now(self) -> datetime:
            return _NOW + timedelta(seconds=_IDENTITY_TOKEN_TTL_SECONDS + 1)

    selection = await svc.login(user.email, "correct-password", **_kwargs())
    assert isinstance(selection, IdentitySelection)
    late_svc = AuthService(
        users=users,
        memberships=memberships,
        tenants=tenants,
        refresh_sessions=sessions,
        auth_tokens=tokens,
        email=email,
        clock=_LateClock(),
    )
    with pytest.raises(Validation):
        await late_svc.select_tenant(selection.identity_token, _TENANT_A, **_kwargs())


async def test_select_tenant_rejects_a_token_whose_purpose_is_not_tenant_selection(
    context: tuple,
) -> None:
    """select_tenant rechaza un access token normal (purpose=access) usado como identity_token."""
    svc, *_ = context
    user = _seed_single_active_membership(context)
    login_result = await svc.login(user.email, "correct-password", **_kwargs())
    assert isinstance(login_result, AuthResult)

    with pytest.raises(Validation):
        await svc.select_tenant(login_result.access_token, _TENANT_A, **_kwargs())


async def test_switch_tenant_with_active_session_changes_to_another_membership(
    context: tuple,
) -> None:
    """switch_tenant cambia a otra membership del usuario sin repetir credenciales."""
    svc, users, memberships, tenants, *_ = context
    user = _make_user(password_hash=hash_password("correct-password"))
    users.seed(user)
    tenants.seed(_make_tenant(_TENANT_A, slug="a"))
    tenants.seed(_make_tenant(_TENANT_B, slug="b"))
    memberships.seed(_make_membership(user.id, _TENANT_A))
    memberships.seed(_make_membership(user.id, _TENANT_B))
    login_result = await svc.login(user.email, "correct-password", **_kwargs())
    assert isinstance(login_result, IdentitySelection)
    current = await svc.select_tenant(login_result.identity_token, _TENANT_A, **_kwargs())

    switched = await svc.switch_tenant(current.access_token, _TENANT_B, **_kwargs())

    assert isinstance(switched, AuthResult)
    assert switched.access_token != current.access_token


async def test_switch_tenant_to_a_membership_the_user_does_not_have_is_rejected(
    context: tuple,
) -> None:
    """switch_tenant a un tenant del que el usuario no es miembro se rechaza."""
    svc, *_ = context
    user = _seed_single_active_membership(context)
    login_result = await svc.login(user.email, "correct-password", **_kwargs())
    assert isinstance(login_result, AuthResult)

    with pytest.raises(Validation):
        await svc.switch_tenant(login_result.access_token, _TENANT_C, **_kwargs())


async def test_switch_tenant_rejects_positional_secret(context: tuple) -> None:
    """secret/algorithm/ttl son keyword-only en switch_tenant(): pasarlos por posición es TypeError."""
    svc, *_ = context
    with pytest.raises(TypeError):
        await svc.switch_tenant("any-token", _TENANT_A, SECRET, ALGORITHM, TTL)  # type: ignore[misc]


async def test_switch_tenant_rejects_a_token_whose_purpose_is_not_access(context: tuple) -> None:
    """switch_tenant rechaza un identity_token (purpose=tenant_selection) usado como access token
    (dirección opuesta al mismo chequeo de select_tenant)."""
    svc, users, memberships, tenants, *_ = context
    user = _make_user(password_hash=hash_password("correct-password"))
    users.seed(user)
    tenants.seed(_make_tenant(_TENANT_A, slug="a"))
    tenants.seed(_make_tenant(_TENANT_B, slug="b"))
    memberships.seed(_make_membership(user.id, _TENANT_A))
    memberships.seed(_make_membership(user.id, _TENANT_B))
    login_result = await svc.login(user.email, "correct-password", **_kwargs())
    assert isinstance(login_result, IdentitySelection)

    with pytest.raises(Validation):
        await svc.switch_tenant(login_result.identity_token, _TENANT_A, **_kwargs())


async def test_select_tenant_rejects_a_membership_whose_tenant_became_disabled_after_login(
    context: tuple,
) -> None:
    """select_tenant re-comprueba el tenant en el momento del canje: si se deshabilitó DESPUÉS de
    emitir el identity_token (login vio 2 tenants no-disabled), el canje de ESE tenant se rechaza
    igual (defensa en profundidad, no solo confía en lo válido en el momento del login)."""
    svc, users, memberships, tenants, *_ = context
    user = _make_user(password_hash=hash_password("correct-password"))
    users.seed(user)
    tenants.seed(_make_tenant(_TENANT_A, slug="a"))
    tenants.seed(_make_tenant(_TENANT_B, slug="b"))
    memberships.seed(_make_membership(user.id, _TENANT_A))
    memberships.seed(_make_membership(user.id, _TENANT_B))
    login_result = await svc.login(user.email, "correct-password", **_kwargs())
    assert isinstance(login_result, IdentitySelection)

    tenants.seed(_make_tenant(_TENANT_A, status=TenantStatus.disabled, slug="a"))

    with pytest.raises(Validation):
        await svc.select_tenant(login_result.identity_token, _TENANT_A, **_kwargs())


async def test_refresh_rotates_and_issues_new_access(context: tuple) -> None:
    """Rotación del refresh: el anterior queda rotado, se emite un access nuevo."""
    svc, users, memberships, tenants, sessions, *_ = context
    user = _seed_single_active_membership(context)
    login_result = await svc.login(user.email, "correct-password", **_kwargs())
    assert isinstance(login_result, AuthResult)
    refreshed = await svc.refresh(login_result.refresh_token, **_kwargs())
    assert refreshed.access_token
    assert refreshed.refresh_token != login_result.refresh_token
    assert len(sessions.store) == 2  # original (rotated) + nueva


async def test_refresh_rejects_positional_secret(context: tuple) -> None:
    """secret/algorithm/ttl son keyword-only en refresh(): pasarlos por posición es TypeError."""
    svc, *_ = context
    with pytest.raises(TypeError):
        await svc.refresh("any-token", SECRET, ALGORITHM, TTL)  # type: ignore[misc,call-arg]


async def test_refresh_reuse_detection_revokes_family(context: tuple) -> None:
    """Reuse-detection: presentar un refresh ya rotado revoca TODA la family_id."""
    svc, *_ = context
    user = _seed_single_active_membership(context)
    login_result = await svc.login(user.email, "correct-password", **_kwargs())
    assert isinstance(login_result, AuthResult)
    await svc.refresh(login_result.refresh_token, **_kwargs())  # rota el original
    with pytest.raises(Conflict):
        await svc.refresh(login_result.refresh_token, **_kwargs())  # reuso del ya-rotado


async def test_refresh_with_unknown_token_is_rejected(context: tuple) -> None:
    """Refresh con un token que no corresponde a ninguna sesión se rechaza."""
    svc, *_ = context
    with pytest.raises(Conflict):
        await svc.refresh("no-such-token", **_kwargs())


async def test_refresh_expired_session_rejects_without_reuse_detection(context: tuple) -> None:
    """Refresh caducado (activo pero expires_at pasado) se rechaza SIN revocar la family_id."""
    svc, users, memberships, tenants, sessions, *_ = context
    user = _seed_single_active_membership(context)
    expired_session = RefreshSession(
        id=uuid.uuid4(),
        user_id=user.id,
        tenant_id=_TENANT_A,
        token_hash=_hash_token("expired-token"),
        family_id=uuid.uuid4(),
        status=RefreshSessionStatus.active,
        expires_at=_NOW - timedelta(days=1),
    )
    await sessions.add(expired_session)
    with pytest.raises(Conflict):
        await svc.refresh("expired-token", **_kwargs())
    assert sessions.revoked_families == []


async def test_logout_revokes_session_server_side(context: tuple) -> None:
    """Logout revoca la sesión server-side; un refresh posterior con ese token falla."""
    svc, *_ = context
    user = _seed_single_active_membership(context)
    login_result = await svc.login(user.email, "correct-password", **_kwargs())
    assert isinstance(login_result, AuthResult)
    await svc.logout(login_result.refresh_token)
    with pytest.raises(Conflict):
        await svc.refresh(login_result.refresh_token, **_kwargs())


async def test_forgot_password_for_existing_user_creates_token_and_sends_email(
    context: tuple,
) -> None:
    """Solicitud de reset (sin tenant_id): emite un token de un solo uso y notifica (stub)."""
    svc, users, *_ = context
    user = _make_user(password_hash="irrelevant")
    users.seed(user)
    await svc.forgot_password(user.email)
    _, _, _, _, _, tokens, email = context
    assert len(tokens.store) == 1
    assert len(email.sent) == 1


async def test_forgot_password_for_nonexistent_email_behaves_the_same(context: tuple) -> None:
    """Reset para un email inexistente responde igual (no revela existencia): no lanza, no emite token."""
    svc, _, _, _, _, tokens, email = context
    await svc.forgot_password("nobody@example.com")
    assert len(tokens.store) == 0
    assert len(email.sent) == 0


async def test_reset_password_with_valid_token_sets_new_password(context: tuple) -> None:
    """Canje válido fija la contraseña y marca el token usado."""
    svc, users, _, _, _, tokens, email = context
    user = _make_user(password_hash="old-hash")
    users.seed(user)
    await svc.forgot_password(user.email)
    issued_token_entity = next(iter(tokens.store.values()))
    plaintext_token = email.sent[0][2]["token"]
    await svc.reset_password(plaintext_token, "new-password")
    assert tokens.store[issued_token_entity.id].used_at is not None
    assert users.store[user.id].password_hash != "old-hash"


@pytest.mark.parametrize("corrupt", ["already-used", "expired", "wrong-kind"])
async def test_reset_password_with_unusable_token_is_rejected(context: tuple, corrupt: str) -> None:
    """Canje de un token inutilizable (caducado/usado/de otro kind) se rechaza."""
    svc, users, _, _, _, tokens, _ = context
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


async def test_invite_existing_user_only_creates_membership_without_touching_password(
    context: tuple,
) -> None:
    """Invitar un email que ya existe como User global solo crea la membership (invited); no toca
    su password existente."""
    svc, users, memberships, tenants, _, _, email = context
    user = _make_user(password_hash="existing-hash")
    users.seed(user)
    tenants.seed(_make_tenant(_TENANT_B, slug="b"))

    await svc.invite(_TENANT_B, user.email)

    membership = await memberships.get(user.id, _TENANT_B)
    assert membership is not None
    assert membership.status is UserStatus.invited
    assert users.store[user.id].password_hash == "existing-hash"
    assert len(email.sent) == 1


async def test_invite_creates_a_new_global_user_when_email_does_not_exist(context: tuple) -> None:
    """Invitar un email que no existe crea el User (sin password) + membership invited."""
    svc, users, memberships, tenants, *_ = context
    tenants.seed(_make_tenant(_TENANT_B, slug="b"))

    await svc.invite(_TENANT_B, "new-person@example.com")

    created = await users.get_by_email("new-person@example.com")
    assert created is not None
    assert created.password_hash is None
    membership = await memberships.get(created.id, _TENANT_B)
    assert membership is not None
    assert membership.status is UserStatus.invited


async def test_invite_already_active_in_the_same_tenant_is_rejected(context: tuple) -> None:
    """Invitar un email ya active en el MISMO tenant se rechaza (Conflict)."""
    svc, users, memberships, tenants, *_ = context
    user = _make_user(password_hash="existing-hash")
    users.seed(user)
    tenants.seed(_make_tenant(_TENANT_B, slug="b"))
    memberships.seed(_make_membership(user.id, _TENANT_B, status=UserStatus.active))
    with pytest.raises(Conflict):
        await svc.invite(_TENANT_B, user.email)


async def test_accept_invitation_sets_global_password_and_activates_only_invited_memberships(
    context: tuple,
) -> None:
    """Aceptar invitación fija el password GLOBAL y activa la membership invited; una membership YA
    active en otro tenant no se toca."""
    svc, users, memberships, tenants, *_ = context
    user = _make_user(password_hash=None)
    users.seed(user)
    tenants.seed(_make_tenant(_TENANT_A, slug="a"))
    tenants.seed(_make_tenant(_TENANT_B, slug="b"))
    memberships.seed(_make_membership(user.id, _TENANT_A, status=UserStatus.active))
    await svc.invite(_TENANT_B, user.email)
    _, _, _, _, _, tokens, email = context
    plaintext = email.sent[-1][2]["token"]

    await svc.accept_invitation(plaintext, "new-password")

    assert users.store[user.id].password_hash is not None
    assert (await memberships.get(user.id, _TENANT_B)).status is UserStatus.active  # type: ignore[union-attr]
    assert (await memberships.get(user.id, _TENANT_A)).status is UserStatus.active  # type: ignore[union-attr]


async def test_change_password_with_correct_current_password_updates_it(context: tuple) -> None:
    """change_password con la actual correcta la actualiza."""
    svc, users, *_ = context
    user = _make_user(password_hash=hash_password("old-password"))
    users.seed(user)
    await svc.change_password(user.id, "old-password", "new-password")
    updated = users.store[user.id]
    assert updated.password_hash != hash_password("old-password")


async def test_change_password_with_wrong_current_password_is_rejected(context: tuple) -> None:
    """change_password con la actual incorrecta se rechaza, sin tocar el password."""
    svc, users, *_ = context
    user = _make_user(password_hash=hash_password("old-password"))
    users.seed(user)
    original_hash = user.password_hash
    with pytest.raises(Validation):
        await svc.change_password(user.id, "wrong-password", "new-password")
    assert users.store[user.id].password_hash == original_hash


async def test_change_password_when_no_password_is_set_yet_is_rejected(context: tuple) -> None:
    """change_password sobre un usuario sin password fijado (invited, aún sin aceptar) se
    rechaza — cualquier `current_password` es 'incorrecta' contra un hash inexistente."""
    svc, users, *_ = context
    user = _make_user(password_hash=None)
    users.seed(user)
    with pytest.raises(Validation):
        await svc.change_password(user.id, "anything", "new-password")


def test_auth_result_is_immutable() -> None:
    """AuthResult es frozen: reasignar un campo lanza (contrato del dataclass)."""
    result = AuthResult(access_token="a", refresh_token="r")
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.access_token = "other"  # type: ignore[misc]


def test_tenant_choice_is_immutable() -> None:
    """TenantChoice es frozen: reasignar un campo lanza."""
    choice = TenantChoice(tenant_id=_TENANT_A, slug="a", name="A")
    with pytest.raises(dataclasses.FrozenInstanceError):
        choice.slug = "other"  # type: ignore[misc]


def test_identity_selection_is_immutable() -> None:
    """IdentitySelection es frozen: reasignar un campo lanza."""
    selection = IdentitySelection(identity_token="t", tenants=[])
    with pytest.raises(dataclasses.FrozenInstanceError):
        selection.identity_token = "other"  # type: ignore[misc]


async def test_login_refresh_session_expires_in_configured_days(context: tuple) -> None:
    """La RefreshSession creada en login expira exactamente 14 días después (valor fijo)."""
    assert _REFRESH_SESSION_TTL_DAYS == 14
    svc, users, memberships, tenants, sessions, *_ = context
    user = _seed_single_active_membership(context)
    await svc.login(user.email, "correct-password", **_kwargs())
    session = next(iter(sessions.store.values()))
    assert session.expires_at == _NOW + timedelta(days=14)


async def test_forgot_password_token_expires_in_configured_hours(context: tuple) -> None:
    """El AuthToken emitido por forgot_password expira exactamente 24h después (valor fijo)."""
    assert _AUTH_TOKEN_TTL_HOURS == 24
    svc, users, *_ = context
    user = _make_user(password_hash="irrelevant")
    users.seed(user)
    await svc.forgot_password(user.email)
    _, _, _, _, _, tokens, _ = context
    issued = next(iter(tokens.store.values()))
    assert issued.expires_at == _NOW + timedelta(hours=24)


async def test_identity_token_ttl_is_configured_short(context: tuple) -> None:
    """El identity_token expira exactamente 300s después de emitido (valor fijo, mutation-safe)."""
    assert _IDENTITY_TOKEN_TTL_SECONDS == 300


async def test_refresh_at_exact_expiry_boundary_is_rejected(context: tuple) -> None:
    """Frontera: expires_at == now se considera caducado (`<=`, no `<`)."""
    svc, users, memberships, tenants, sessions, *_ = context
    user = _seed_single_active_membership(context)
    boundary_session = RefreshSession(
        id=uuid.uuid4(),
        user_id=user.id,
        tenant_id=_TENANT_A,
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
    svc, users, *_ = context
    user = _make_user(password_hash="old-hash")
    users.seed(user)
    _, _, _, _, _, tokens, _ = context
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
