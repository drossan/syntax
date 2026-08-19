"""Tests de integración de las extensiones de repositorio de la tarea `backend-routers-core-06`:
`SqlAlchemyAuditLogRepository` (nuevo) y las asignaciones `user_role` de `SqlAlchemyRoleRepository`
(`assign`/`unassign_all`/`list_assigned`/`list_all_capabilities`), que los routers admin necesitan.

Postgres real vía `superuser_engine` (mismo patrón que `test_repositories_identity.py`): estas tablas
de identidad/RBAC no llevan RLS (salvo `audit_log`, tabla de NEGOCIO con RLS — superuser la bypassa,
igual que `test_migration*.py`).
"""

import uuid
from collections.abc import AsyncIterator

import pytest_asyncio
from app.domain.entities.business import AuditLogEntry
from app.domain.entities.enums import CapabilityScope, RoleKind, TenantStatus
from app.domain.entities.identity import Role, Tenant, User
from app.infra.db.repositories import (
    SqlAlchemyAuditLogRepository,
    SqlAlchemyRoleRepository,
    SqlAlchemyTenantRepository,
    SqlAlchemyUserRepository,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

_TRUNCATE_TABLES = (
    "TRUNCATE audit_log, user_tenant, refresh_session, auth_token, user_role, role_capability, "
    'capability, "user", role, tenant RESTART IDENTITY CASCADE'
)


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables(superuser_engine: AsyncEngine) -> AsyncIterator[None]:
    async with superuser_engine.begin() as conn:
        await conn.execute(text(_TRUNCATE_TABLES))
    yield
    async with superuser_engine.begin() as conn:
        await conn.execute(text(_TRUNCATE_TABLES))


@pytest_asyncio.fixture
async def session(superuser_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with async_sessionmaker(superuser_engine, expire_on_commit=False)() as s:
        yield s


def _make_tenant(*, slug: str | None = None) -> Tenant:
    slug = slug or f"t-{uuid.uuid4()}"
    return Tenant(id=uuid.uuid4(), slug=slug, name="Tenant", status=TenantStatus.active)


async def _make_user(session: AsyncSession, *, user_id: uuid.UUID | None = None) -> User:
    return await SqlAlchemyUserRepository(session).add(
        User(
            id=user_id or uuid.uuid4(),
            email=f"u-{uuid.uuid4()}@example.com",
            password_hash="hash",
        )
    )


async def _seed_capability(
    session: AsyncSession, *, name: str, scope: CapabilityScope
) -> uuid.UUID:
    capability_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO capability (id, name, scope) VALUES (:id, :name, :scope)"),
        {"id": capability_id, "name": name, "scope": scope.value},
    )
    return capability_id


# ── AuditLogRepository ──


async def test_audit_log_add_persists_the_entry(session: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(session).add(_make_tenant())
    await session.commit()

    await SqlAlchemyAuditLogRepository(session).add(
        AuditLogEntry(
            tenant_id=tenant.id,
            action="tenant.created",
            entity_type="tenant",
            entity_id=str(tenant.id),
            payload={"slug": tenant.slug},
        )
    )
    await session.commit()

    row = (
        await session.execute(
            text("SELECT tenant_id, action, entity_type, entity_id, payload FROM audit_log")
        )
    ).one()
    assert row.tenant_id == tenant.id
    assert row.action == "tenant.created"
    assert row.entity_type == "tenant"
    assert row.entity_id == str(tenant.id)
    assert row.payload == {"slug": tenant.slug}


async def test_audit_log_add_with_an_actor_persists_it(session: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(session).add(_make_tenant())
    actor = await _make_user(session)
    await session.commit()

    await SqlAlchemyAuditLogRepository(session).add(
        AuditLogEntry(
            tenant_id=tenant.id,
            action="role.created",
            entity_type="role",
            entity_id=str(uuid.uuid4()),
            payload={},
            actor_id=actor.id,
        )
    )
    await session.commit()

    row = (await session.execute(text("SELECT actor_id FROM audit_log"))).one()
    assert row.actor_id == actor.id


# ── RoleRepository.list_all_capabilities ──


async def test_list_all_capabilities_returns_the_full_catalog_regardless_of_role(
    session: AsyncSession,
) -> None:
    tenant_cap = await _seed_capability(session, name="ticket.reply", scope=CapabilityScope.tenant)
    global_cap = await _seed_capability(
        session, name="tenant.manage", scope=CapabilityScope.global_
    )
    await session.commit()

    capabilities = await SqlAlchemyRoleRepository(session).list_all_capabilities()

    assert {c.id for c in capabilities} == {tenant_cap, global_cap}


# ── RoleRepository.set_capabilities ──


async def test_set_capabilities_grants_the_given_capabilities(session: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(session).add(_make_tenant())
    role_repo = SqlAlchemyRoleRepository(session)
    role = await role_repo.add(
        Role(id=uuid.uuid4(), name="custom", kind=RoleKind.tenant, tenant_id=tenant.id)
    )
    cap_a = await _seed_capability(session, name="ticket.reply", scope=CapabilityScope.tenant)
    cap_b = await _seed_capability(session, name="ticket.read", scope=CapabilityScope.tenant)
    await session.commit()

    await role_repo.set_capabilities(role.id, [cap_a, cap_b])
    await session.commit()

    granted = await role_repo.list_capabilities(role.id)
    assert {c.id for c in granted} == {cap_a, cap_b}


async def test_set_capabilities_replaces_the_previous_set(session: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(session).add(_make_tenant())
    role_repo = SqlAlchemyRoleRepository(session)
    role = await role_repo.add(
        Role(id=uuid.uuid4(), name="custom", kind=RoleKind.tenant, tenant_id=tenant.id)
    )
    cap_a = await _seed_capability(session, name="ticket.reply", scope=CapabilityScope.tenant)
    cap_b = await _seed_capability(session, name="ticket.read", scope=CapabilityScope.tenant)
    await session.commit()
    await role_repo.set_capabilities(role.id, [cap_a])
    await session.commit()

    await role_repo.set_capabilities(role.id, [cap_b])
    await session.commit()

    granted = await role_repo.list_capabilities(role.id)
    assert {c.id for c in granted} == {cap_b}


async def test_set_capabilities_with_an_empty_list_revokes_all(session: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(session).add(_make_tenant())
    role_repo = SqlAlchemyRoleRepository(session)
    role = await role_repo.add(
        Role(id=uuid.uuid4(), name="custom", kind=RoleKind.tenant, tenant_id=tenant.id)
    )
    cap_a = await _seed_capability(session, name="ticket.reply", scope=CapabilityScope.tenant)
    await session.commit()
    await role_repo.set_capabilities(role.id, [cap_a])
    await session.commit()

    await role_repo.set_capabilities(role.id, [])
    await session.commit()

    assert await role_repo.list_capabilities(role.id) == []


# ── RoleRepository.assign / unassign_all / list_assigned ──


async def test_assign_grants_a_role_visible_via_list_assigned(session: AsyncSession) -> None:
    tenant = await SqlAlchemyTenantRepository(session).add(_make_tenant())
    role_repo = SqlAlchemyRoleRepository(session)
    role = await role_repo.add(
        Role(id=uuid.uuid4(), name="agent", kind=RoleKind.tenant, tenant_id=tenant.id)
    )
    user = await _make_user(session)
    await session.commit()

    await role_repo.assign(user.id, role.id, tenant.id)
    await session.commit()

    assigned = await role_repo.list_assigned(user.id, tenant.id)
    assert {r.id for r in assigned} == {role.id}


async def test_assign_is_idempotent_and_updates_the_scope_on_conflict(
    session: AsyncSession,
) -> None:
    """El PK real es `(user_id, role_id)` — reasignar el MISMO par con un `tenant_id` distinto no
    debe violar unicidad, y debe dejar la asignación en el ámbito nuevo (upsert, no error)."""
    tenant_a = await SqlAlchemyTenantRepository(session).add(_make_tenant())
    tenant_b = await SqlAlchemyTenantRepository(session).add(_make_tenant())
    role_repo = SqlAlchemyRoleRepository(session)
    role = await role_repo.add(
        Role(id=uuid.uuid4(), name="support_admin", kind=RoleKind.system, tenant_id=None)
    )
    user = await _make_user(session)
    await session.commit()

    await role_repo.assign(user.id, role.id, tenant_a.id)
    await session.commit()
    await role_repo.assign(user.id, role.id, tenant_b.id)
    await session.commit()

    assert [r.id for r in await role_repo.list_assigned(user.id, tenant_a.id)] == []
    assert {r.id for r in await role_repo.list_assigned(user.id, tenant_b.id)} == {role.id}


async def test_unassign_all_removes_only_that_tenants_assignment(session: AsyncSession) -> None:
    """El usuario tiene el MISMO rol `system` asignado dos veces: una vez en ámbito global
    (`tenant_id=None`) y otra en el ámbito del tenant. `unassign_all(tenant.id)` retira solo la del
    tenant — la global sobrevive (son asignaciones/filas independientes, PK distinto)."""
    tenant = await SqlAlchemyTenantRepository(session).add(_make_tenant())
    role_repo = SqlAlchemyRoleRepository(session)
    role = await role_repo.add(
        Role(id=uuid.uuid4(), name="support_admin", kind=RoleKind.system, tenant_id=None)
    )
    other_role = await role_repo.add(
        Role(id=uuid.uuid4(), name="agent", kind=RoleKind.tenant, tenant_id=tenant.id)
    )
    user = await _make_user(session)
    await session.commit()
    await role_repo.assign(user.id, role.id, None)
    await role_repo.assign(user.id, other_role.id, tenant.id)
    await session.commit()

    await role_repo.unassign_all(user.id, tenant.id)
    await session.commit()

    assert [r.id for r in await role_repo.list_assigned(user.id, tenant.id)] == []
    remaining_global = (
        await session.execute(
            text("SELECT count(*) FROM user_role WHERE user_id = :u AND tenant_id IS NULL"),
            {"u": user.id},
        )
    ).scalar_one()
    assert remaining_global == 1


async def test_list_assigned_does_not_leak_another_tenants_assignment(
    session: AsyncSession,
) -> None:
    """El tenant objetivo (50) queda ENTRE otro tenant con una asignación propia (10): descarta que
    el filtro compare mal y mezcle roles asignados en OTRO tenant."""
    tenant_target = await SqlAlchemyTenantRepository(session).add(
        Tenant(id=uuid.UUID(int=50), slug="t-50", name="T", status=TenantStatus.active)
    )
    tenant_other = await SqlAlchemyTenantRepository(session).add(
        Tenant(id=uuid.UUID(int=10), slug="t-10", name="T", status=TenantStatus.active)
    )
    role_repo = SqlAlchemyRoleRepository(session)
    role_target = await role_repo.add(
        Role(id=uuid.uuid4(), name="agent", kind=RoleKind.tenant, tenant_id=tenant_target.id)
    )
    role_other = await role_repo.add(
        Role(id=uuid.uuid4(), name="agent-2", kind=RoleKind.tenant, tenant_id=tenant_other.id)
    )
    user = await _make_user(session)
    await session.commit()
    await role_repo.assign(user.id, role_target.id, tenant_target.id)
    await role_repo.assign(user.id, role_other.id, tenant_other.id)
    await session.commit()

    assigned = await role_repo.list_assigned(user.id, tenant_target.id)

    assert {r.id for r in assigned} == {role_target.id}


async def test_unassign_all_filters_by_tenant_id_with_exact_equality(
    session: AsyncSession,
) -> None:
    """El tenant objetivo (50) queda ENTRE otros dos con su propia asignación (10 y 90, UUIDs
    deterministas): descarta `<=`/`>=` en el filtro de `tenant_id` — cualquiera de los dos borraría
    también la asignación del tenant vecino."""
    role_repo = SqlAlchemyRoleRepository(session)
    tenants = {}
    roles = {}
    for n in (10, 50, 90):
        tenants[n] = await SqlAlchemyTenantRepository(session).add(
            Tenant(id=uuid.UUID(int=n), slug=f"t-{n}", name="T", status=TenantStatus.active)
        )
        roles[n] = await role_repo.add(
            Role(id=uuid.uuid4(), name=f"role-{n}", kind=RoleKind.tenant, tenant_id=tenants[n].id)
        )
    user = await _make_user(session)
    await session.commit()
    for n in (10, 50, 90):
        await role_repo.assign(user.id, roles[n].id, tenants[n].id)
    await session.commit()

    await role_repo.unassign_all(user.id, tenants[50].id)
    await session.commit()

    assert {r.id for r in await role_repo.list_assigned(user.id, tenants[10].id)} == {roles[10].id}
    assert {r.id for r in await role_repo.list_assigned(user.id, tenants[90].id)} == {roles[90].id}
    assert list(await role_repo.list_assigned(user.id, tenants[50].id)) == []


async def test_unassign_all_filters_by_user_id_with_exact_equality(
    session: AsyncSession,
) -> None:
    """El usuario objetivo (50) queda ENTRE otros dos con la MISMA asignación (10 y 90, UUIDs
    deterministas): descarta `<=`/`>=` en el filtro de `user_id` — cualquiera de los dos borraría
    también la asignación del usuario vecino."""
    tenant = await SqlAlchemyTenantRepository(session).add(_make_tenant())
    role_repo = SqlAlchemyRoleRepository(session)
    role = await role_repo.add(
        Role(id=uuid.uuid4(), name="agent", kind=RoleKind.tenant, tenant_id=tenant.id)
    )
    users = {n: await _make_user(session, user_id=uuid.UUID(int=n)) for n in (10, 50, 90)}
    await session.commit()
    for n in (10, 50, 90):
        await role_repo.assign(users[n].id, role.id, tenant.id)
    await session.commit()

    await role_repo.unassign_all(users[50].id, tenant.id)
    await session.commit()

    assert {r.id for r in await role_repo.list_assigned(users[10].id, tenant.id)} == {role.id}
    assert {r.id for r in await role_repo.list_assigned(users[90].id, tenant.id)} == {role.id}
    assert list(await role_repo.list_assigned(users[50].id, tenant.id)) == []


async def test_list_assigned_join_condition_matches_only_the_assigned_role(
    session: AsyncSession,
) -> None:
    """El rol objetivo (50) queda ENTRE otros dos roles EXISTENTES pero NO asignados (10 y 90, UUIDs
    deterministas): descarta `<=`/`>=` en la condición del JOIN — cualquiera de los dos filtraría un
    rol no asignado como si lo estuviera."""
    tenant = await SqlAlchemyTenantRepository(session).add(_make_tenant())
    role_repo = SqlAlchemyRoleRepository(session)
    role_low = await role_repo.add(
        Role(id=uuid.UUID(int=10), name="low", kind=RoleKind.tenant, tenant_id=tenant.id)
    )
    role_target = await role_repo.add(
        Role(id=uuid.UUID(int=50), name="target", kind=RoleKind.tenant, tenant_id=tenant.id)
    )
    role_high = await role_repo.add(
        Role(id=uuid.UUID(int=90), name="high", kind=RoleKind.tenant, tenant_id=tenant.id)
    )
    user = await _make_user(session)
    await session.commit()
    await role_repo.assign(user.id, role_target.id, tenant.id)
    await session.commit()

    assigned = await role_repo.list_assigned(user.id, tenant.id)

    assert {r.id for r in assigned} == {role_target.id}
    assert role_low.id not in {r.id for r in assigned}
    assert role_high.id not in {r.id for r in assigned}


async def test_list_assigned_filters_by_user_id_with_exact_equality(
    session: AsyncSession,
) -> None:
    """El usuario objetivo (50) queda ENTRE otros dos con roles DISTINTOS asignados en el MISMO
    tenant (10 y 90, UUIDs deterministas): descarta `<=`/`>=` en el filtro de `user_id`."""
    tenant = await SqlAlchemyTenantRepository(session).add(_make_tenant())
    role_repo = SqlAlchemyRoleRepository(session)
    roles = {
        n: await role_repo.add(
            Role(id=uuid.uuid4(), name=f"role-{n}", kind=RoleKind.tenant, tenant_id=tenant.id)
        )
        for n in (10, 50, 90)
    }
    users = {n: await _make_user(session, user_id=uuid.UUID(int=n)) for n in (10, 50, 90)}
    await session.commit()
    for n in (10, 50, 90):
        await role_repo.assign(users[n].id, roles[n].id, tenant.id)
    await session.commit()

    assigned = await role_repo.list_assigned(users[50].id, tenant.id)

    assert {r.id for r in assigned} == {roles[50].id}


async def test_set_capabilities_filters_by_role_id_with_exact_equality(
    session: AsyncSession,
) -> None:
    """El rol objetivo (50) queda ENTRE otros dos con sus propias capabilities (10 y 90, UUIDs
    deterministas): descarta `<=`/`>=` en el `DELETE` — cualquiera de los dos borraría también las
    capabilities del rol vecino."""
    tenant = await SqlAlchemyTenantRepository(session).add(_make_tenant())
    role_repo = SqlAlchemyRoleRepository(session)
    roles = {
        n: await role_repo.add(
            Role(id=uuid.UUID(int=n), name=f"role-{n}", kind=RoleKind.tenant, tenant_id=tenant.id)
        )
        for n in (10, 50, 90)
    }
    caps = {
        n: await _seed_capability(session, name=f"cap-{n}", scope=CapabilityScope.tenant)
        for n in (10, 50, 90)
    }
    await session.commit()
    for n in (10, 50, 90):
        await role_repo.set_capabilities(roles[n].id, [caps[n]])
    await session.commit()

    await role_repo.set_capabilities(roles[50].id, [])
    await session.commit()

    assert {c.id for c in await role_repo.list_capabilities(roles[10].id)} == {caps[10]}
    assert {c.id for c in await role_repo.list_capabilities(roles[90].id)} == {caps[90]}
    assert await role_repo.list_capabilities(roles[50].id) == []
