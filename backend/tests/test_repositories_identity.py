"""Tests de integración de los adaptadores SQLAlchemy de identidad (tarea backend-routers-core-04).

Postgres real (`superuser_engine`; estas tablas no llevan RLS, así que superuser vs `syntax_app` no
cambia el comportamiento bajo prueba — se usa `superuser_engine` por simplicidad, igual que
`test_migration*.py`). 1:1 con el `## Scenarios` de la tarea: contrato de cada puerto, CAS real de
`rotate_if_active` (incl. concurrencia con conexiones separadas de verdad), `effective_capabilities`
acotado por tenant, y que ninguna excepción de infra cruda escapa (`PortError`).
"""

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from app.core.security import hash_token
from app.domain.entities.enums import (
    AuthTokenKind,
    CapabilityScope,
    RefreshSessionStatus,
    RoleKind,
    TenantStatus,
    UserStatus,
)
from app.domain.entities.identity import (
    AuthToken,
    RefreshSession,
    Role,
    Tenant,
    User,
    UserTenantMembership,
)
from app.domain.errors import NotFound, PortError
from app.domain.ports.repositories import Reused, Rotated
from app.infra.db.repositories import (
    SqlAlchemyAuthTokenRepository,
    SqlAlchemyRefreshSessionRepository,
    SqlAlchemyRoleRepository,
    SqlAlchemyTenantRepository,
    SqlAlchemyUserRepository,
    SqlAlchemyUserTenantMembershipRepository,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


_TRUNCATE_IDENTITY_TABLES = (
    "TRUNCATE user_tenant, refresh_session, auth_token, user_role, role_capability, "
    'capability, "user", role, tenant RESTART IDENTITY CASCADE'
)


@pytest_asyncio.fixture(autouse=True)
async def _clean_identity_tables(superuser_engine: AsyncEngine) -> AsyncIterator[None]:
    """Trunca las tablas de identidad/RBAC antes y DESPUÉS de cada test (no llevan RLS/tenant_id →
    sin aislamiento natural entre tests). Sin seeds cargados todavía (tarea 17): `capability`/`role`
    están vacías salvo lo que siembre cada test, así que también se truncan. El truncate posterior
    evita contaminar OTRAS suites (p.ej. `test_migration.py`, que asume `user` vacía) si esta suite
    fuera la última en tocar estas tablas dentro de una ejecución completa de `pytest`."""
    async with superuser_engine.begin() as conn:
        await conn.execute(text(_TRUNCATE_IDENTITY_TABLES))
    yield
    async with superuser_engine.begin() as conn:
        await conn.execute(text(_TRUNCATE_IDENTITY_TABLES))


@pytest_asyncio.fixture
async def session(superuser_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with async_sessionmaker(superuser_engine, expire_on_commit=False)() as s:
        yield s


def _make_tenant(*, slug: str | None = None, status: TenantStatus = TenantStatus.active) -> Tenant:
    slug = slug or f"t-{uuid.uuid4()}"
    return Tenant(id=uuid.uuid4(), slug=slug, name="Tenant", status=status)


def _make_user(*, email: str | None = None) -> User:
    return User(
        id=uuid.uuid4(), email=email or f"u-{uuid.uuid4()}@example.com", password_hash="hash"
    )


# ── TenantRepository ──


async def test_tenant_add_get_update_roundtrip(session: AsyncSession) -> None:
    repo = SqlAlchemyTenantRepository(session)
    tenant = _make_tenant()

    added = await repo.add(tenant)
    await session.commit()
    fetched = await repo.get(added.id)
    assert fetched is not None
    assert fetched.slug == tenant.slug
    assert fetched.auto_approve is False

    fetched.name = "Renamed"
    fetched.auto_approve = True
    updated = await repo.update(fetched)
    await session.commit()
    reread = await repo.get(added.id)
    assert reread is not None
    assert reread.name == "Renamed"
    assert reread.auto_approve is True
    assert updated.name == "Renamed"


async def test_tenant_list_paginates(session: AsyncSession) -> None:
    """TenantRepository.list pagina los tenants (Gherkin: page/page_size → página + total correcto)."""
    repo = SqlAlchemyTenantRepository(session)
    for i in range(5):
        await repo.add(_make_tenant(slug=f"page-{i}"))
    await session.commit()

    page = await repo.list(page=1, page_size=2)
    assert len(page.items) == 2
    assert page.total == 5

    second_page = await repo.list(page=2, page_size=2)
    assert len(second_page.items) == 2
    assert {t.id for t in page.items}.isdisjoint({t.id for t in second_page.items})


# ── UserRepository ──


async def test_user_get_by_email_does_not_need_a_tenant(session: AsyncSession) -> None:
    """UserRepository.get_by_email busca sin filtrar por tenant."""
    repo = SqlAlchemyUserRepository(session)
    user = _make_user(email="global@example.com")
    await repo.add(user)
    await session.commit()

    found = await repo.get_by_email("global@example.com")
    assert found is not None
    assert found.id == user.id


async def test_user_list_by_ids_returns_only_the_requested_users_in_one_query(
    session: AsyncSession,
) -> None:
    """`list_by_ids` trae varios usuarios de una sola vez (evita N+1 al resolver autores de
    mensajes en `list_messages`) -- ni de más (otro user no pedido) ni de menos."""
    repo = SqlAlchemyUserRepository(session)
    a = await repo.add(_make_user(email="a@example.com"))
    b = await repo.add(_make_user(email="b@example.com"))
    await repo.add(_make_user(email="c@example.com"))
    await session.commit()

    found = await repo.list_by_ids([a.id, b.id])

    assert {u.id for u in found} == {a.id, b.id}


async def test_user_list_by_ids_with_empty_list_returns_empty_without_querying(
    session: AsyncSession,
) -> None:
    """Lista vacía -> resultado vacío, sin lanzar un `IN ()` inválido a la base de datos."""
    repo = SqlAlchemyUserRepository(session)

    found = await repo.list_by_ids([])

    assert found == []


async def test_user_duplicate_email_is_wrapped_in_port_error(session: AsyncSession) -> None:
    """Insertar un email duplicado llega como PortError, no como IntegrityError cruda."""
    repo = SqlAlchemyUserRepository(session)
    await repo.add(_make_user(email="dup@example.com"))
    await session.commit()

    with pytest.raises(PortError):
        await repo.add(_make_user(email="dup@example.com"))


# ── UserTenantMembershipRepository ──


async def test_membership_list_by_user_returns_only_that_users_memberships(
    session: AsyncSession,
) -> None:
    tenant_repo = SqlAlchemyTenantRepository(session)
    user_repo = SqlAlchemyUserRepository(session)
    membership_repo = SqlAlchemyUserTenantMembershipRepository(session)

    tenant_a, tenant_b = _make_tenant(), _make_tenant()
    user_1, user_2 = _make_user(), _make_user()
    for entity in (tenant_a, tenant_b):
        await tenant_repo.add(entity)
    for entity in (user_1, user_2):
        await user_repo.add(entity)
    await membership_repo.add(
        UserTenantMembership(user_id=user_1.id, tenant_id=tenant_a.id, status=UserStatus.active)
    )
    await membership_repo.add(
        UserTenantMembership(user_id=user_2.id, tenant_id=tenant_b.id, status=UserStatus.active)
    )
    await session.commit()

    memberships = await membership_repo.list_by_user(user_1.id)

    assert [m.tenant_id for m in memberships] == [tenant_a.id]


async def test_membership_list_by_tenant_paginates(session: AsyncSession) -> None:
    tenant_repo = SqlAlchemyTenantRepository(session)
    user_repo = SqlAlchemyUserRepository(session)
    membership_repo = SqlAlchemyUserTenantMembershipRepository(session)
    tenant = await tenant_repo.add(_make_tenant())
    for _ in range(3):
        user = await user_repo.add(_make_user())
        await membership_repo.add(
            UserTenantMembership(user_id=user.id, tenant_id=tenant.id, status=UserStatus.active)
        )
    await session.commit()

    page = await membership_repo.list_by_tenant(tenant.id, page=1, page_size=2)

    assert len(page.items) == 2
    assert page.total == 3


async def test_membership_update_persists_status_change(session: AsyncSession) -> None:
    tenant_repo = SqlAlchemyTenantRepository(session)
    user_repo = SqlAlchemyUserRepository(session)
    membership_repo = SqlAlchemyUserTenantMembershipRepository(session)
    tenant = await tenant_repo.add(_make_tenant())
    user = await user_repo.add(_make_user())
    membership = await membership_repo.add(
        UserTenantMembership(user_id=user.id, tenant_id=tenant.id, status=UserStatus.invited)
    )
    await session.commit()

    membership.status = UserStatus.active
    await membership_repo.update(membership)
    await session.commit()

    reread = await membership_repo.get(user.id, tenant.id)
    assert reread is not None
    assert reread.status is UserStatus.active


# ── RoleRepository ──


async def test_role_list_returns_system_seed_and_tenant_custom_but_not_other_tenants(
    session: AsyncSession,
) -> None:
    """El tenant objetivo (50) queda ENTRE otros dos tenants con su propio rol custom (10 y 90,
    UUIDs deterministas): descarta que el filtro compare mal (`==` vs `<=`/`>=`/…) y que se cuele
    el rol custom de OTRO tenant."""
    tenant_repo = SqlAlchemyTenantRepository(session)
    role_repo = SqlAlchemyRoleRepository(session)
    tenant = await tenant_repo.add(
        Tenant(id=uuid.UUID(int=50), slug="t-50", name="T", status=TenantStatus.active)
    )
    await tenant_repo.add(
        Tenant(id=uuid.UUID(int=10), slug="t-10", name="T", status=TenantStatus.active)
    )
    await tenant_repo.add(
        Tenant(id=uuid.UUID(int=90), slug="t-90", name="T", status=TenantStatus.active)
    )
    system_role = await role_repo.add(
        Role(id=uuid.uuid4(), name="support_admin", kind=RoleKind.system, tenant_id=None)
    )
    custom_role = await role_repo.add(
        Role(id=uuid.uuid4(), name="custom", kind=RoleKind.tenant, tenant_id=tenant.id)
    )
    await role_repo.add(
        Role(id=uuid.uuid4(), name="other-1", kind=RoleKind.tenant, tenant_id=uuid.UUID(int=10))
    )
    await role_repo.add(
        Role(id=uuid.uuid4(), name="other-2", kind=RoleKind.tenant, tenant_id=uuid.UUID(int=90))
    )
    await session.commit()

    roles = await role_repo.list(tenant.id)

    assert {r.id for r in roles} == {system_role.id, custom_role.id}


async def test_role_update_persists_description_change(session: AsyncSession) -> None:
    tenant_repo = SqlAlchemyTenantRepository(session)
    role_repo = SqlAlchemyRoleRepository(session)
    tenant = await tenant_repo.add(_make_tenant())
    role = await role_repo.add(
        Role(id=uuid.uuid4(), name="custom", kind=RoleKind.tenant, tenant_id=tenant.id)
    )
    await session.commit()

    role.description = "nueva descripción"
    await role_repo.update(role)
    await session.commit()

    reread = await role_repo.get(role.id)
    assert reread is not None
    assert reread.description == "nueva descripción"


async def test_role_delete_removes_it_from_list(session: AsyncSession) -> None:
    tenant_repo = SqlAlchemyTenantRepository(session)
    role_repo = SqlAlchemyRoleRepository(session)
    tenant = await tenant_repo.add(_make_tenant())
    role = await role_repo.add(
        Role(id=uuid.uuid4(), name="custom", kind=RoleKind.tenant, tenant_id=tenant.id)
    )
    await session.commit()

    deleted = await role_repo.delete(role.id)
    await session.commit()

    assert deleted is True
    assert role.id not in {r.id for r in await role_repo.list(tenant.id)}


async def test_role_delete_on_nonexistent_role_returns_false(session: AsyncSession) -> None:
    role_repo = SqlAlchemyRoleRepository(session)
    deleted = await role_repo.delete(uuid.uuid4())
    assert deleted is False


async def _seed_capability(
    session: AsyncSession,
    *,
    name: str,
    scope: CapabilityScope,
    capability_id: uuid.UUID | None = None,
) -> uuid.UUID:
    capability_id = capability_id or uuid.uuid4()
    await session.execute(
        text("INSERT INTO capability (id, name, scope) VALUES (:id, :name, :scope)"),
        {"id": capability_id, "name": name, "scope": scope.value},
    )
    return capability_id


async def test_role_list_capabilities_returns_only_that_roles_capabilities(
    session: AsyncSession,
) -> None:
    """El `role_id` objetivo (50) queda ENTRE otros dos roles con sus propias capabilities (10 y
    90, UUIDs deterministas): descarta que el join/filtro compare mal y mezcle capabilities de
    OTRO rol."""
    role_repo = SqlAlchemyRoleRepository(session)
    target_role = await role_repo.add(
        Role(id=uuid.UUID(int=50), name="target", kind=RoleKind.system, tenant_id=None)
    )
    await role_repo.add(
        Role(id=uuid.UUID(int=10), name="other-1", kind=RoleKind.system, tenant_id=None)
    )
    await role_repo.add(
        Role(id=uuid.UUID(int=90), name="other-2", kind=RoleKind.system, tenant_id=None)
    )
    target_cap = await _seed_capability(
        session, name="ticket.reply", scope=CapabilityScope.tenant, capability_id=uuid.UUID(int=500)
    )
    other_cap_1 = await _seed_capability(
        session,
        name="ticket.assign",
        scope=CapabilityScope.tenant,
        capability_id=uuid.UUID(int=100),
    )
    other_cap_2 = await _seed_capability(
        session, name="kb.read", scope=CapabilityScope.tenant, capability_id=uuid.UUID(int=900)
    )
    await session.execute(
        text("INSERT INTO role_capability (role_id, capability_id) VALUES (:r, :c)"),
        {"r": target_role.id, "c": target_cap},
    )
    await session.execute(
        text("INSERT INTO role_capability (role_id, capability_id) VALUES (:r, :c)"),
        {"r": uuid.UUID(int=10), "c": other_cap_1},
    )
    await session.execute(
        text("INSERT INTO role_capability (role_id, capability_id) VALUES (:r, :c)"),
        {"r": uuid.UUID(int=90), "c": other_cap_2},
    )
    await session.commit()

    capabilities = await role_repo.list_capabilities(target_role.id)

    assert {c.id for c in capabilities} == {target_cap}


async def test_effective_capabilities_is_scoped_to_the_session_tenant(
    session: AsyncSession,
) -> None:
    """effective_capabilities(user_id, tenant_id) solo devuelve las del rol asignado en ESE tenant
    Y a ESE usuario — `user_id` objetivo (50) queda ENTRE el de otro usuario con rol/capability
    propios en el MISMO tenant (10, UUID determinista): descarta que el filtro `user_id` compare
    mal y mezcle las capabilities de otro usuario."""
    tenant_repo = SqlAlchemyTenantRepository(session)
    user_repo = SqlAlchemyUserRepository(session)
    role_repo = SqlAlchemyRoleRepository(session)
    tenant_a = await tenant_repo.add(_make_tenant())
    tenant_b = await tenant_repo.add(_make_tenant())
    user = await user_repo.add(User(id=uuid.UUID(int=50), email="target@example.com"))
    other_user = await user_repo.add(User(id=uuid.UUID(int=10), email="other@example.com"))

    role_a = await role_repo.add(
        Role(id=uuid.uuid4(), name="role-a", kind=RoleKind.tenant, tenant_id=tenant_a.id)
    )
    role_b = await role_repo.add(
        Role(id=uuid.uuid4(), name="role-b", kind=RoleKind.tenant, tenant_id=tenant_b.id)
    )
    role_other = await role_repo.add(
        Role(id=uuid.uuid4(), name="role-other", kind=RoleKind.tenant, tenant_id=tenant_a.id)
    )
    cap_a = await _seed_capability(session, name="ticket.reply", scope=CapabilityScope.tenant)
    cap_b = await _seed_capability(session, name="ticket.assign", scope=CapabilityScope.tenant)
    cap_other = await _seed_capability(session, name="kb.read", scope=CapabilityScope.tenant)
    await session.execute(
        text("INSERT INTO role_capability (role_id, capability_id) VALUES (:r, :c)"),
        {"r": role_a.id, "c": cap_a},
    )
    await session.execute(
        text("INSERT INTO role_capability (role_id, capability_id) VALUES (:r, :c)"),
        {"r": role_b.id, "c": cap_b},
    )
    await session.execute(
        text("INSERT INTO role_capability (role_id, capability_id) VALUES (:r, :c)"),
        {"r": role_other.id, "c": cap_other},
    )
    await session.execute(
        text("INSERT INTO user_role (user_id, role_id, tenant_id) VALUES (:u, :r, :t)"),
        {"u": user.id, "r": role_a.id, "t": tenant_a.id},
    )
    await session.execute(
        text("INSERT INTO user_role (user_id, role_id, tenant_id) VALUES (:u, :r, :t)"),
        {"u": user.id, "r": role_b.id, "t": tenant_b.id},
    )
    await session.execute(
        text("INSERT INTO user_role (user_id, role_id, tenant_id) VALUES (:u, :r, :t)"),
        {"u": other_user.id, "r": role_other.id, "t": tenant_a.id},
    )
    await session.commit()

    capabilities_in_a = await role_repo.effective_capabilities(user.id, tenant_a.id)

    assert capabilities_in_a == {("ticket.reply", "tenant")}


async def test_effective_capabilities_scope_comes_from_the_assignment_not_the_catalog(
    session: AsyncSession,
) -> None:
    """La MISMA capacidad concedida vía un rol `system` (global) Y un rol `tenant` produce AMBAS
    tuplas `(cap, "global")` y `(cap, "tenant")` — el `scope` de la tupla se deriva de
    `user_role.tenant_id` (NULL=global), no del `capability.scope` fijo del catálogo (bug real:
    leer el catálogo colapsaba ambas vías a un único valor, rompiendo la precedencia
    global>tenant de `get_tenant_context`, backend-routers-core-05)."""
    tenant_repo = SqlAlchemyTenantRepository(session)
    role_repo = SqlAlchemyRoleRepository(session)
    user_repo = SqlAlchemyUserRepository(session)
    tenant = await tenant_repo.add(_make_tenant())
    user = await user_repo.add(_make_user())

    tenant_role = await role_repo.add(
        Role(id=uuid.uuid4(), name="tenant-role", kind=RoleKind.tenant, tenant_id=tenant.id)
    )
    global_role = await role_repo.add(
        Role(id=uuid.uuid4(), name="global-role", kind=RoleKind.system, tenant_id=None)
    )
    cap = await _seed_capability(session, name="ticket.reply", scope=CapabilityScope.tenant)
    for role in (tenant_role, global_role):
        await session.execute(
            text("INSERT INTO role_capability (role_id, capability_id) VALUES (:r, :c)"),
            {"r": role.id, "c": cap},
        )
    await session.execute(
        text("INSERT INTO user_role (user_id, role_id, tenant_id) VALUES (:u, :r, :t)"),
        {"u": user.id, "r": tenant_role.id, "t": tenant.id},
    )
    await session.execute(
        text("INSERT INTO user_role (user_id, role_id, tenant_id) VALUES (:u, :r, :t)"),
        {"u": user.id, "r": global_role.id, "t": None},
    )
    await session.commit()

    capabilities = await role_repo.effective_capabilities(user.id, tenant.id)

    assert capabilities == {("ticket.reply", "tenant"), ("ticket.reply", "global")}


# ── RefreshSessionRepository ──


async def _seed_active_session(
    session: AsyncSession, *, plaintext: str = "plain-token", family_id: uuid.UUID | None = None
) -> tuple[SqlAlchemyRefreshSessionRepository, RefreshSession]:
    tenant_repo = SqlAlchemyTenantRepository(session)
    user_repo = SqlAlchemyUserRepository(session)
    tenant = await tenant_repo.add(_make_tenant())
    user = await user_repo.add(_make_user())
    repo = SqlAlchemyRefreshSessionRepository(session)
    created = await repo.add(
        RefreshSession(
            id=uuid.uuid4(),
            user_id=user.id,
            tenant_id=tenant.id,
            token_hash=hash_token(plaintext),
            family_id=family_id or uuid.uuid4(),
            status=RefreshSessionStatus.active,
            expires_at=_NOW + timedelta(days=14),
        )
    )
    await session.commit()
    return repo, created


async def test_rotate_if_active_rotates_an_active_session(session: AsyncSession) -> None:
    repo, original = await _seed_active_session(session)

    outcome = await repo.rotate_if_active(hash_token("plain-token"), hash_token("new-token"), _NOW)
    await session.commit()

    assert isinstance(outcome, Rotated)
    assert outcome.session.parent_id == original.id
    assert outcome.session.status is RefreshSessionStatus.active


async def test_rotate_if_active_detects_reuse(session: AsyncSession) -> None:
    repo, _original = await _seed_active_session(session)
    await repo.rotate_if_active(hash_token("plain-token"), hash_token("new-token"), _NOW)
    await session.commit()

    outcome = await repo.rotate_if_active(hash_token("plain-token"), hash_token("another"), _NOW)

    assert isinstance(outcome, Reused)


async def test_rotate_if_active_with_unknown_hash_raises_not_found(session: AsyncSession) -> None:
    """Con OTRA sesión ya existente (hash distinto) en la tabla, un hash nunca emitido sigue dando
    NotFound — descarta que el SELECT de diagnóstico compare mal (`==` vs `!=`) y confunda una fila
    ajena con un `match`."""
    repo, _existing = await _seed_active_session(session, plaintext="existing-token")
    with pytest.raises(NotFound):
        await repo.rotate_if_active(hash_token("never-issued"), hash_token("x"), _NOW)


async def test_add_duplicate_token_hash_is_wrapped_in_port_error(session: AsyncSession) -> None:
    """token_hash es único: una segunda refresh_session con el mismo hash llega como PortError."""
    repo, _original = await _seed_active_session(session, plaintext="clash-token")
    tenant_repo = SqlAlchemyTenantRepository(session)
    user_repo = SqlAlchemyUserRepository(session)
    tenant = await tenant_repo.add(_make_tenant())
    user = await user_repo.add(_make_user())
    await session.commit()

    with pytest.raises(PortError):
        await repo.add(
            RefreshSession(
                id=uuid.uuid4(),
                user_id=user.id,
                tenant_id=tenant.id,
                token_hash=hash_token("clash-token"),
                family_id=uuid.uuid4(),
                status=RefreshSessionStatus.active,
                expires_at=_NOW + timedelta(days=14),
            )
        )


async def test_revoke_revokes_only_that_session(session: AsyncSession) -> None:
    """El `id` objetivo (5) queda ENTRE los otros dos (1 y 9, UUIDs deterministas): descarta que el
    filtro compare mal (`==` vs `<=`/`>=`/…) en cualquiera de las dos direcciones."""
    tenant_repo = SqlAlchemyTenantRepository(session)
    user_repo = SqlAlchemyUserRepository(session)
    tenant = await tenant_repo.add(_make_tenant())
    user = await user_repo.add(_make_user())
    repo = SqlAlchemyRefreshSessionRepository(session)

    async def _add(id_int: int, plaintext: str) -> RefreshSession:
        return await repo.add(
            RefreshSession(
                id=uuid.UUID(int=id_int),
                user_id=user.id,
                tenant_id=tenant.id,
                token_hash=hash_token(plaintext),
                family_id=uuid.uuid4(),
                status=RefreshSessionStatus.active,
                expires_at=_NOW + timedelta(days=14),
            )
        )

    await _add(1, "token-lower")
    session_target = await _add(5, "token-target")
    await _add(9, "token-higher")
    await session.commit()

    await repo.revoke(session_target.id)
    await session.commit()

    reused_target = await repo.rotate_if_active(hash_token("token-target"), hash_token("x"), _NOW)
    still_lower = await repo.rotate_if_active(hash_token("token-lower"), hash_token("y"), _NOW)
    still_higher = await repo.rotate_if_active(hash_token("token-higher"), hash_token("z"), _NOW)
    assert isinstance(reused_target, Reused)
    assert isinstance(still_lower, Rotated)
    assert isinstance(still_higher, Rotated)


async def test_revoke_family_revokes_every_session_in_the_family_not_others(
    session: AsyncSession,
) -> None:
    """`family_id` objetivo (5) queda ENTRE las otras dos familias (1 y 9, UUIDs deterministas):
    descarta que el filtro compare mal (`==` vs `<=`/`>=`/…) en cualquiera de las dos direcciones."""
    repo, seeded = await _seed_active_session(
        session, plaintext="family-token", family_id=uuid.UUID(int=5)
    )
    tenant_repo = SqlAlchemyTenantRepository(session)
    user_repo = SqlAlchemyUserRepository(session)
    tenant = await tenant_repo.add(_make_tenant())
    user = await user_repo.add(_make_user())

    async def _add_family(family_int: int, plaintext: str) -> None:
        await repo.add(
            RefreshSession(
                id=uuid.uuid4(),
                user_id=user.id,
                tenant_id=tenant.id,
                token_hash=hash_token(plaintext),
                family_id=uuid.UUID(int=family_int),
                status=RefreshSessionStatus.active,
                expires_at=_NOW + timedelta(days=14),
            )
        )

    await _add_family(1, "lower-family-token")
    await _add_family(9, "higher-family-token")
    await session.commit()

    await repo.revoke_family(seeded.family_id)
    await session.commit()

    revoked = await repo.rotate_if_active(hash_token("family-token"), hash_token("x"), _NOW)
    lower = await repo.rotate_if_active(hash_token("lower-family-token"), hash_token("y"), _NOW)
    higher = await repo.rotate_if_active(hash_token("higher-family-token"), hash_token("z"), _NOW)
    assert isinstance(revoked, Reused)
    assert isinstance(lower, Rotated)
    assert isinstance(higher, Rotated)


async def test_revoke_by_hash_revokes_only_that_hash(session: AsyncSession) -> None:
    repo, _seeded = await _seed_active_session(session, plaintext="hash-a")
    tenant_repo = SqlAlchemyTenantRepository(session)
    user_repo = SqlAlchemyUserRepository(session)
    tenant = await tenant_repo.add(_make_tenant())
    user = await user_repo.add(_make_user())
    await repo.add(
        RefreshSession(
            id=uuid.uuid4(),
            user_id=user.id,
            tenant_id=tenant.id,
            token_hash=hash_token("hash-b"),
            family_id=uuid.uuid4(),
            status=RefreshSessionStatus.active,
            expires_at=_NOW + timedelta(days=14),
        )
    )
    await session.commit()

    await repo.revoke_by_hash(hash_token("hash-a"))
    await session.commit()

    revoked = await repo.rotate_if_active(hash_token("hash-a"), hash_token("x"), _NOW)
    still_active = await repo.rotate_if_active(hash_token("hash-b"), hash_token("y"), _NOW)
    assert isinstance(revoked, Reused)
    assert isinstance(still_active, Rotated)


async def test_revoke_by_hash_on_unknown_hash_is_idempotent_noop(session: AsyncSession) -> None:
    """revoke_by_hash sobre un hash que no corresponde a ninguna sesión no lanza (idempotente)."""
    repo = SqlAlchemyRefreshSessionRepository(session)
    await repo.revoke_by_hash(hash_token("never-issued"))
    await session.commit()


async def test_rotate_if_active_is_atomic_under_real_concurrency(
    superuser_engine: AsyncEngine,
) -> None:
    """2 llamadas concurrentes (conexiones DE VERDAD separadas) con el mismo token_hash: solo una
    obtiene Rotated; la serialización la da el lock de fila del UPDATE, no el código Python."""
    async with async_sessionmaker(superuser_engine, expire_on_commit=False)() as setup_session:
        await _seed_active_session(setup_session, plaintext="race-token")

    async def _attempt() -> object:
        async with async_sessionmaker(superuser_engine, expire_on_commit=False)() as s:
            repo = SqlAlchemyRefreshSessionRepository(s)
            outcome = await repo.rotate_if_active(
                hash_token("race-token"), hash_token(str(uuid.uuid4())), _NOW
            )
            await s.commit()
            return outcome

    results = await asyncio.gather(_attempt(), _attempt(), return_exceptions=True)

    rotated_count = sum(1 for r in results if isinstance(r, Rotated))
    other_count = sum(1 for r in results if isinstance(r, Reused | NotFound))
    assert rotated_count == 1
    assert rotated_count + other_count == 2


# ── AuthTokenRepository ──


async def test_auth_token_add_get_mark_used_roundtrip(session: AsyncSession) -> None:
    user_repo = SqlAlchemyUserRepository(session)
    user = await user_repo.add(_make_user())
    repo = SqlAlchemyAuthTokenRepository(session)
    token = await repo.add(
        AuthToken(
            id=uuid.uuid4(),
            user_id=user.id,
            kind=AuthTokenKind.invitation,
            token_hash=hash_token("invite-token"),
            expires_at=_NOW + timedelta(hours=24),
        )
    )
    await session.commit()

    found = await repo.get_by_token_hash(hash_token("invite-token"))
    assert found is not None
    assert found.kind is AuthTokenKind.invitation

    used = await repo.mark_used(token.id, _NOW)
    await session.commit()
    assert used.used_at == _NOW


# ── PortError envuelve fallos de infra arbitrarios ──


async def test_infra_failure_is_wrapped_in_port_error() -> None:
    """Un fallo de infra real (conexión a un host inalcanzable) llega como PortError, no como la
    excepción cruda de SQLAlchemy/asyncpg (p.ej. `OperationalError`)."""
    broken_engine = create_async_engine(
        "postgresql+asyncpg://syntax:syntax@localhost:59999/syntax_test"
    )
    try:
        async with async_sessionmaker(broken_engine, expire_on_commit=False)() as broken_session:
            repo = SqlAlchemyTenantRepository(broken_session)
            with pytest.raises(PortError):
                await repo.get(uuid.uuid4())
    finally:
        await broken_engine.dispose()
