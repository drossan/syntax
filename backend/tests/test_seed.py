"""Tests de `app.infra.db.seed` (gap real: sin esto no hay forma de loguearse en un despliegue nuevo).

Contra Postgres real (`session`, superuser — las tablas de RBAC no llevan RLS de fila, ver
`app/infra/db/models/identity.py`), igual que el resto de tests de infra.
"""

from collections.abc import AsyncIterator

import pytest_asyncio
from app.core.security import verify_password
from app.infra.db.repositories.role import SqlAlchemyRoleRepository
from app.infra.db.repositories.tenant import SqlAlchemyTenantRepository
from app.infra.db.repositories.user import SqlAlchemyUserRepository
from app.infra.db.seed import (
    CAPABILITIES,
    DEV_PASSWORD,
    ROLE_USERS,
    SYSTEM_ROLES,
    _ensure_system_role,
    _seed,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

_TRUNCATE_TABLES = (
    "TRUNCATE user_role, role_capability, role, capability, user_tenant, "
    '"user", tenant RESTART IDENTITY CASCADE'
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


async def test_seed_creates_the_full_capability_catalog(session: AsyncSession) -> None:
    await _seed(session)

    catalog = await SqlAlchemyRoleRepository(session).list_all_capabilities()
    assert {c.name for c in catalog} == set(CAPABILITIES)
    for capability in catalog:
        assert capability.scope == CAPABILITIES[capability.name]


async def test_seed_creates_the_six_system_roles_with_the_spec_capability_matrix(
    session: AsyncSession,
) -> None:
    await _seed(session)

    role_repo = SqlAlchemyRoleRepository(session)
    for role_name, expected_capabilities in SYSTEM_ROLES.items():
        role = await _ensure_system_role(session, name=role_name)  # idempotente: solo lo re-lee
        assert role.tenant_id is None, f"{role_name} debe ser un rol de sistema global"
        granted = {c.name for c in await role_repo.list_capabilities(role.id)}
        assert granted == set(expected_capabilities)


async def test_seed_creates_one_user_per_role_with_the_dev_password(session: AsyncSession) -> None:
    await _seed(session)

    user_repo = SqlAlchemyUserRepository(session)
    for _role_name, (email, _tenant_slug) in ROLE_USERS.items():
        user = await user_repo.get_by_email(email)
        assert user is not None, f"falta el usuario semilla {email}"
        assert user.password_hash is not None
        assert verify_password(DEV_PASSWORD, user.password_hash)


async def test_seed_grants_support_roles_globally_and_client_roles_per_tenant(
    session: AsyncSession,
) -> None:
    await _seed(session)

    role_repo = SqlAlchemyRoleRepository(session)
    user_repo = SqlAlchemyUserRepository(session)
    tenant_repo = SqlAlchemyTenantRepository(session)
    demo_tenant = next(
        t for t in (await tenant_repo.list(page=1, page_size=10)).items if t.slug == "demo"
    )

    support_admin = await user_repo.get_by_email("support-admin@syntax.local")
    assert support_admin is not None
    effective = await role_repo.effective_capabilities(support_admin.id, demo_tenant.id)
    assert ("tenant.manage", "global") in effective, (
        "support_admin debe llegar global a CUALQUIER tenant"
    )

    client_viewer = await user_repo.get_by_email("client-viewer@demo.local")
    assert client_viewer is not None
    effective_cv = await role_repo.effective_capabilities(client_viewer.id, demo_tenant.id)
    assert ("ticket.read", "tenant") in effective_cv
    assert "analytics.read" not in {name for name, _scope in effective_cv}


async def test_seed_is_idempotent(session: AsyncSession) -> None:
    await _seed(session)
    await _seed(session)

    role_repo = SqlAlchemyRoleRepository(session)
    catalog = await role_repo.list_all_capabilities()
    assert len(catalog) == len(CAPABILITIES), (
        "no debe duplicar el catálogo de capacidades al re-ejecutar"
    )

    user_repo = SqlAlchemyUserRepository(session)
    support_admin = await user_repo.get_by_email("support-admin@syntax.local")
    assert support_admin is not None
    # re-ejecutar no debe reventar por unique constraints (name/email/slug) — si `_seed` no fuera
    # idempotente, la segunda llamada ya habría lanzado antes de llegar aquí.
