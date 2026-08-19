"""app.domain.ports.repositories — puertos de repositorio por agregado.

Un `Protocol` async por agregado; firmas en tipos de dominio (`app.domain.entities`), nunca SQLAlchemy.
El aislamiento multi-tenant es responsabilidad del adaptador (filtra por el `tenant_id` del contexto);
estos puertos reciben `tenant_id` como parámetro explícito donde aplica.

Dos puertos llevan **compare-and-set** (una sola llamada atómica, no `get`+`if`+`update` en pasos
separados — el check-then-act no es demostrable con fakes y es el footgun real de la concurrencia,
design-review B3 + scenario-coverage): `ApprovalRepository.decide_if_pending` y
`RefreshSessionRepository.rotate_if_active`.

Anti-patrón: filtrar tenant en la capa de servicio en vez del repo; tipos de infra en las firmas; que un
adaptador deje pasar una excepción de infra cruda (debe envolverla en `app.domain.errors.PortError`).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.domain.entities.business import (
    AgentRun,
    ApprovalTask,
    AuditLogEntry,
    Message,
    Notification,
    Ticket,
)
from app.domain.entities.identity import (
    AuthToken,
    Capability,
    RefreshSession,
    Role,
    Tenant,
    User,
    UserTenantMembership,
)


class TenantRepository(Protocol):
    """Puerto de `tenant`."""

    async def get(self, tenant_id: uuid.UUID) -> Tenant | None: ...
    async def add(self, tenant: Tenant) -> Tenant: ...


class UserRepository(Protocol):
    """Puerto de `user` (identidad GLOBAL desde el rediseño multi-tenant: `email` es único global,
    sin `tenant_id` — la pertenencia a un tenant vive en `UserTenantMembershipRepository`)."""

    async def get(self, user_id: uuid.UUID) -> User | None: ...
    async def get_by_email(self, email: str) -> User | None: ...
    async def add(self, user: User) -> User: ...
    async def update(self, user: User) -> User: ...


class UserTenantMembershipRepository(Protocol):
    """Puerto de `user_tenant` (membership `user`×`tenant`, con su propio `status`)."""

    async def get(
        self, user_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> UserTenantMembership | None: ...

    async def list_for_user(self, user_id: uuid.UUID) -> list[UserTenantMembership]:
        """Todas las membresías del usuario (cualquier `status`, cualquier tenant)."""
        ...

    async def add(self, membership: UserTenantMembership) -> UserTenantMembership: ...
    async def update(self, membership: UserTenantMembership) -> UserTenantMembership: ...


class RoleRepository(Protocol):
    """Puerto de `role`/`capability`, incl. resolución de capacidades efectivas del sujeto."""

    async def get(self, role_id: uuid.UUID) -> Role | None: ...
    async def add(self, role: Role) -> Role: ...
    async def list_capabilities(self, role_id: uuid.UUID) -> list[Capability]: ...
    async def effective_capabilities(self, user_id: uuid.UUID) -> set[tuple[str, str]]:
        """Conjunto `(capability_name, scope)` resuelto server-side para el usuario (A1.7)."""
        ...


@dataclass(frozen=True)
class Rotated:
    """`rotate_if_active`: la sesión estaba activa y se rotó con éxito."""

    session: RefreshSession


@dataclass(frozen=True)
class Reused:
    """`rotate_if_active`: la sesión encontrada ya NO estaba activa (reuse-detection)."""

    family_id: uuid.UUID


RotationOutcome = Rotated | Reused
"""Resultado de `rotate_if_active` cuando el hash SÍ corresponde a una sesión (rotada o reusada).

Si ningún hash coincide, el puerto lanza `app.domain.errors.NotFound` (no hay tercer valor de retorno).
"""


class RefreshSessionRepository(Protocol):
    """Puerto de `refresh_session` (rotación + reuse-detection)."""

    async def add(self, session: RefreshSession) -> RefreshSession: ...

    async def rotate_if_active(
        self, token_hash: str, new_token_hash: str, now: datetime
    ) -> RotationOutcome:
        """CAS: busca por `token_hash` y rota **solo si** la sesión seguía `active`.

        :raises app.domain.errors.NotFound: si ningún hash coincide con ninguna sesión.
        """
        ...

    async def revoke_family(self, family_id: uuid.UUID) -> None:
        """Revoca todas las sesiones de `family_id` (reuse-detection: logout de toda la cadena)."""
        ...

    async def revoke(self, session_id: uuid.UUID) -> None:
        """Revoca una sesión concreta (logout server-side)."""
        ...

    async def revoke_by_hash(self, token_hash: str) -> None:
        """Revoca la sesión con ese `token_hash`, sin rotarla (logout). Idempotente: si el hash no
        corresponde a ninguna sesión (ya revocada, o nunca existió), no-op — no revela cuál de las
        dos ocurrió, ni lanza."""
        ...


class AuthTokenRepository(Protocol):
    """Puerto de `auth_token` (password-reset / invitación, un solo uso)."""

    async def add(self, token: AuthToken) -> AuthToken: ...
    async def get_by_token_hash(self, token_hash: str) -> AuthToken | None: ...
    async def mark_used(self, token_id: uuid.UUID, used_at: datetime) -> AuthToken: ...


class TicketRepository(Protocol):
    """Puerto de `ticket`."""

    async def get(self, ticket_id: uuid.UUID) -> Ticket | None: ...
    async def add(self, ticket: Ticket) -> Ticket: ...
    async def update(self, ticket: Ticket) -> Ticket: ...
    async def list(self, tenant_id: uuid.UUID) -> list[Ticket]:
        """Orden por defecto `-updated_at` (contrato del puerto, FR-021)."""
        ...


class MessageRepository(Protocol):
    """Puerto de `message`."""

    async def add(self, message: Message) -> Message: ...
    async def list_by_ticket(self, ticket_id: uuid.UUID) -> list[Message]:
        """Orden `created_at` (contrato del puerto)."""
        ...


class ApprovalRepository(Protocol):
    """Puerto de `approval_task`, con CAS en `decide_if_pending`."""

    async def add(self, task: ApprovalTask) -> ApprovalTask: ...

    async def list_pending(self, tenant_id: uuid.UUID) -> list[ApprovalTask]:
        """Orden `sla_due,confidence` (contrato del puerto, `api-contract.yaml`)."""
        ...

    async def decide_if_pending(
        self,
        task_id: uuid.UUID,
        decision: str,
        final_body: str | None,
        human_note: str | None,
    ) -> ApprovalTask | None:
        """CAS: aplica la decisión **solo si** la tarea seguía `pending`.

        :returns: la tarea actualizada, o `None` si existía pero ya no estaba `pending`.
        :raises app.domain.errors.NotFound: si `task_id` no corresponde a ninguna tarea.
        """
        ...


class AgentRunRepository(Protocol):
    """Puerto de `agent_run`."""

    async def get(self, agent_run_id: uuid.UUID) -> AgentRun | None: ...
    async def add(self, run: AgentRun) -> AgentRun: ...
    async def update_status(self, agent_run_id: uuid.UUID, status: str) -> AgentRun: ...
    async def next_run_seq(self, ticket_id: uuid.UUID) -> int: ...


class NotificationRepository(Protocol):
    """Puerto de `notification`."""

    async def add(self, notification: Notification) -> Notification: ...

    async def list_for_user(self, user_id: uuid.UUID) -> list[Notification]:
        """Orden `-created_at` (contrato del puerto, CU-BE-10)."""
        ...

    async def mark_read(
        self, notification_id: uuid.UUID, user_id: uuid.UUID, read_at: datetime
    ) -> None:
        """Idempotente; solo afecta si la notificación pertenece a `user_id`."""
        ...

    async def count_unread(self, user_id: uuid.UUID) -> int:
        """Deriva de `read_at IS NULL` (data-model.md RN-2)."""
        ...


class AuditLogRepository(Protocol):
    """Puerto de `audit_log` (append-only)."""

    async def add(self, entry: AuditLogEntry) -> None: ...
