"""app.infra.db.seed — seeds/fixtures idempotentes (entry-point ``python -m app.infra.db.seed``).

Datos semilla para poder **loguearse y disparar `agent.trigger`/`approval.decide` desde el front** sin
insertar datos a mano (gap real: con RLS+roles+tenants no hay forma de arrancar sin seeds). Siembra el
**catálogo de capacidades** y los **6 roles de sistema** (`.claude/specs/backend/rbac.md` §2-3, fuente
de verdad — no se reinventa aquí), el tenant-sistema ``syntax`` (personal de Soporte) + el tenant
cliente ``demo``, y **un usuario por rol** con password de dev.

Fuera de esta pasada (no bloquea login, se deja para cuando haga falta): tickets/mensajes de ejemplo y
KB de muestra — la KB real se siembra vía ``make ingest`` (pipeline dedicado, no duplicar aquí); tickets
de ejemplo se generan más realistamente disparando el flujo real (`make run` + `POST /ai-draft`) que
con datos sintéticos fijos.

Idempotente por claves naturales: `capability.name`, `role.name` (con `tenant_id IS NULL`, únicas por
`(tenant_id, name)`), `tenant.slug`, `user.email` — re-ejecutar no duplica ni falla.

Anti-patrón: datos de producción; seeds no idempotentes; saltarse RLS insertando sin contexto de
tenant (aquí no aplica: `role`/`user_role`/`capability` son tablas de sistema sin RLS de fila, ver
`app/infra/db/models/identity.py`).
"""

import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.security import hash_password
from app.domain.entities.enums import CapabilityScope, RoleKind, TenantStatus, UserStatus
from app.domain.entities.identity import Role, Tenant, User, UserTenantMembership
from app.infra.db.models.identity import Capability as CapabilityModel
from app.infra.db.models.identity import Role as RoleModel
from app.infra.db.models.identity import Tenant as TenantModel
from app.infra.db.repositories.role import SqlAlchemyRoleRepository
from app.infra.db.repositories.tenant import SqlAlchemyTenantRepository
from app.infra.db.repositories.user import SqlAlchemyUserRepository
from app.infra.db.repositories.user_tenant import SqlAlchemyUserTenantMembershipRepository

DEV_PASSWORD = "DevPassword123!"  # noqa: S105 — password de dev fija a propósito, nunca producción
"""Password compartida de TODOS los usuarios semilla — solo para dev/demo, nunca producción."""

_SYNTAX_TENANT_SLUG = "syntax"
_DEMO_TENANT_SLUG = "demo"

# Catálogo de capacidades — rbac.md §2 (fuente de verdad; NO editar sin sincronizar el spec).
CAPABILITIES: dict[str, CapabilityScope] = {
    "ticket.read": CapabilityScope.tenant,
    "ticket.create": CapabilityScope.tenant,
    "ticket.reply": CapabilityScope.tenant,
    "ticket.transition": CapabilityScope.tenant,
    "ticket.reopen": CapabilityScope.tenant,
    "ticket.assign": CapabilityScope.tenant,
    "ticket.update": CapabilityScope.tenant,
    "note.internal.read": CapabilityScope.global_,
    "note.internal.write": CapabilityScope.global_,
    "approval.decide": CapabilityScope.global_,
    "agent.trigger": CapabilityScope.tenant,
    "kb.read": CapabilityScope.tenant,
    "tenant.manage": CapabilityScope.global_,
    "tenant.settings.manage": CapabilityScope.tenant,
    "user.manage": CapabilityScope.tenant,
    "role.manage": CapabilityScope.tenant,
    "analytics.read": CapabilityScope.tenant,
}

_TICKET_CRUD = [
    "ticket.read",
    "ticket.create",
    "ticket.reply",
    "ticket.transition",
    "ticket.assign",
    "ticket.update",
]

# Roles de sistema × capacidades — rbac.md §3 (prosa, fuente de verdad sobre la matriz resumen: la
# matriz colapsa `kb.read`/`analytics.read` en una sola celda por rol y no refleja que `client_viewer`
# solo tiene `kb.read`, no `analytics.read` — la prosa lo desambigua).
SYSTEM_ROLES: dict[str, list[str]] = {
    "support_admin": list(CAPABILITIES),  # TODAS, ámbito global
    "support_agent": [
        *_TICKET_CRUD,
        "note.internal.read",
        "note.internal.write",
        "approval.decide",
        "agent.trigger",
        "kb.read",
        "analytics.read",
    ],
    "support_viewer": ["ticket.read", "note.internal.read", "kb.read", "analytics.read"],
    "client_admin": [
        *_TICKET_CRUD,
        "user.manage",
        "role.manage",
        "kb.read",
        "analytics.read",
        "agent.trigger",
    ],
    "client_agent": [
        "ticket.create",
        "ticket.reply",
        "ticket.read",
        "ticket.reopen",
        "kb.read",
        "agent.trigger",
    ],
    "client_viewer": ["ticket.read", "kb.read"],
}

# email del usuario semilla por rol · tenant de la MEMBERSHIP (los roles support_* son globales —
# `user_role.tenant_id=None`, ver `role.py::effective_capabilities` — pero el usuario necesita
# pertenecer a ALGÚN tenant activo para tener una sesión con la que loguearse: el tenant-sistema).
ROLE_USERS: dict[str, tuple[str, str]] = {
    "support_admin": ("support-admin@syntax.local", _SYNTAX_TENANT_SLUG),
    "support_agent": ("support-agent@syntax.local", _SYNTAX_TENANT_SLUG),
    "support_viewer": ("support-viewer@syntax.local", _SYNTAX_TENANT_SLUG),
    "client_admin": ("client-admin@demo.local", _DEMO_TENANT_SLUG),
    "client_agent": ("client-agent@demo.local", _DEMO_TENANT_SLUG),
    "client_viewer": ("client-viewer@demo.local", _DEMO_TENANT_SLUG),
}

_SUPPORT_ROLE_PREFIXES = ("support_",)


async def _ensure_tenant(session: AsyncSession, *, slug: str, name: str) -> Tenant:
    tenant_repo = SqlAlchemyTenantRepository(session)
    existing_id = (
        await session.execute(select(TenantModel.id).where(TenantModel.slug == slug))
    ).scalar_one_or_none()
    if existing_id is not None:
        found = await tenant_repo.get(existing_id)
        if found is None:
            raise RuntimeError(f"tenant {existing_id} desapareció entre el SELECT y el get()")
        return found
    return await tenant_repo.add(
        Tenant(id=uuid.uuid4(), slug=slug, name=name, status=TenantStatus.active)
    )


async def _ensure_capability(
    session: AsyncSession, *, name: str, scope: CapabilityScope
) -> uuid.UUID:
    row = (
        await session.execute(select(CapabilityModel).where(CapabilityModel.name == name))
    ).scalar_one_or_none()
    if row is not None:
        return row.id
    row = CapabilityModel(id=uuid.uuid4(), name=name, scope=scope.value)
    session.add(row)
    await session.flush()
    return row.id


async def _ensure_system_role(session: AsyncSession, *, name: str) -> Role:
    role_repo = SqlAlchemyRoleRepository(session)
    row = (
        await session.execute(
            select(RoleModel).where(RoleModel.name == name, RoleModel.tenant_id.is_(None))
        )
    ).scalar_one_or_none()
    if row is not None:
        return Role(id=row.id, name=row.name, kind=RoleKind.system, tenant_id=None)
    return await role_repo.add(
        Role(id=uuid.uuid4(), name=name, kind=RoleKind.system, tenant_id=None)
    )


async def _ensure_user(session: AsyncSession, *, email: str) -> User:
    user_repo = SqlAlchemyUserRepository(session)
    existing = await user_repo.get_by_email(email)
    if existing is not None:
        return existing
    return await user_repo.add(
        User(id=uuid.uuid4(), email=email, password_hash=hash_password(DEV_PASSWORD))
    )


async def _ensure_membership(
    session: AsyncSession, *, user_id: uuid.UUID, tenant_id: uuid.UUID
) -> None:
    membership_repo = SqlAlchemyUserTenantMembershipRepository(session)
    if await membership_repo.get(user_id, tenant_id) is not None:
        return
    await membership_repo.add(
        UserTenantMembership(user_id=user_id, tenant_id=tenant_id, status=UserStatus.active)
    )


async def _seed(session: AsyncSession) -> None:
    syntax_tenant = await _ensure_tenant(session, slug=_SYNTAX_TENANT_SLUG, name="Syntax (Soporte)")
    demo_tenant = await _ensure_tenant(session, slug=_DEMO_TENANT_SLUG, name="Demo Tenant")
    tenants_by_slug = {_SYNTAX_TENANT_SLUG: syntax_tenant, _DEMO_TENANT_SLUG: demo_tenant}

    capability_ids = {
        name: await _ensure_capability(session, name=name, scope=scope)
        for name, scope in CAPABILITIES.items()
    }

    role_repo = SqlAlchemyRoleRepository(session)
    for role_name, capability_names in SYSTEM_ROLES.items():
        role = await _ensure_system_role(session, name=role_name)
        await role_repo.set_capabilities(
            role.id, [capability_ids[name] for name in capability_names]
        )

        email, tenant_slug = ROLE_USERS[role_name]
        user = await _ensure_user(session, email=email)
        home_tenant = tenants_by_slug[tenant_slug]
        await _ensure_membership(session, user_id=user.id, tenant_id=home_tenant.id)

        # `support_*` es rol GLOBAL (tenant_id=None en la asignación, ver rbac.md §7/role.py) — aplica
        # en cualquier sesión, no solo en el tenant `syntax`. `client_*` se asigna ACOTADO al tenant.
        assignment_tenant_id = (
            None if role_name.startswith(_SUPPORT_ROLE_PREFIXES) else home_tenant.id
        )
        await role_repo.assign(user.id, role.id, assignment_tenant_id)

    await session.commit()


async def main() -> int:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        await _seed(session)
    await engine.dispose()
    print(f"Seed OK. Password de dev para los 6 usuarios de rol: {DEV_PASSWORD}")
    for role_name, (email, _slug) in ROLE_USERS.items():
        print(f"  {role_name:16s} {email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
