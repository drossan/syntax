"""app.infra.db.repositories — repositorios de persistencia (adaptadores del puerto de dominio).

`BaseRepository` es la base tenant-aware (filtro app-level por `tenant_id`, 1ª línea sobre RLS) — solo
aplica a las 7 tablas de negocio con `TenantMixin`. Las de identidad/RBAC (`Tenant`/`User`/
`UserTenant`/`Role`/`RefreshSession`/`AuthToken`) son cross-tenant por diseño (RBAC gobierna su
aislamiento, no RLS) y tienen adaptadores propios (`tenant.py`/`user.py`/`user_tenant.py`/`role.py`/
`refresh_session.py`/`auth_token.py`). Anti-patrón: confiar solo en RLS para el aislamiento; exponer
entidades ORM crudas al dominio; dejar pasar una excepción de infra cruda (envolver en `PortError`).
"""

from app.infra.db.repositories.agent_run import SqlAlchemyAgentRunRepository
from app.infra.db.repositories.approval import SqlAlchemyApprovalRepository
from app.infra.db.repositories.audit_log import SqlAlchemyAuditLogRepository
from app.infra.db.repositories.auth_token import SqlAlchemyAuthTokenRepository
from app.infra.db.repositories.base import BaseRepository, TenantScoped
from app.infra.db.repositories.message import SqlAlchemyMessageRepository
from app.infra.db.repositories.notification import SqlAlchemyNotificationRepository
from app.infra.db.repositories.refresh_session import SqlAlchemyRefreshSessionRepository
from app.infra.db.repositories.role import SqlAlchemyRoleRepository
from app.infra.db.repositories.tenant import SqlAlchemyTenantRepository
from app.infra.db.repositories.ticket import SqlAlchemyTicketRepository
from app.infra.db.repositories.user import SqlAlchemyUserRepository
from app.infra.db.repositories.user_tenant import SqlAlchemyUserTenantMembershipRepository

__all__ = [
    "BaseRepository",
    "SqlAlchemyAgentRunRepository",
    "SqlAlchemyApprovalRepository",
    "SqlAlchemyAuditLogRepository",
    "SqlAlchemyAuthTokenRepository",
    "SqlAlchemyMessageRepository",
    "SqlAlchemyNotificationRepository",
    "SqlAlchemyRefreshSessionRepository",
    "SqlAlchemyRoleRepository",
    "SqlAlchemyTenantRepository",
    "SqlAlchemyTicketRepository",
    "SqlAlchemyUserRepository",
    "SqlAlchemyUserTenantMembershipRepository",
    "TenantScoped",
]
