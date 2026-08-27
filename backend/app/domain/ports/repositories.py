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
from typing import Any, Protocol

from app.domain.entities.business import (
    AgentRun,
    ApprovalTask,
    Attachment,
    AuditLogEntry,
    Message,
    Notification,
    Ticket,
)
from app.domain.entities.enums import (
    AgentRunStatus,
    ApprovalStatus,
    KbDomain,
    MessageVisibility,
    TicketPriority,
    TicketStatus,
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


@dataclass(frozen=True)
class PageResult[T]:
    """Resultado de un `list*` paginado: los `items` de la página pedida + el `total` sin paginar."""

    items: list[T]
    total: int


class TenantRepository(Protocol):
    """Puerto de `tenant`."""

    async def get(self, tenant_id: uuid.UUID) -> Tenant | None: ...
    async def add(self, tenant: Tenant) -> Tenant: ...
    async def update(self, tenant: Tenant) -> Tenant: ...

    async def list(self, *, page: int, page_size: int) -> PageResult[Tenant]:
        """Orden determinista por `slug` (contrato del puerto)."""
        ...


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

    async def list_by_user(self, user_id: uuid.UUID) -> list[UserTenantMembership]:
        """Todas las membresías del usuario (cualquier `status`, cualquier tenant); sin paginar
        (el número de tenants de un usuario es acotado, a diferencia de usuarios de un tenant)."""
        ...

    async def list_by_tenant(
        self, tenant_id: uuid.UUID, *, page: int, page_size: int
    ) -> PageResult[UserTenantMembership]:
        """Membresías de ese tenant, paginadas (lo usa `admin_users`, 06). Orden por `created_at`."""
        ...

    async def add(self, membership: UserTenantMembership) -> UserTenantMembership: ...
    async def update(self, membership: UserTenantMembership) -> UserTenantMembership: ...


class RoleRepository(Protocol):
    """Puerto de `role`/`capability`, incl. resolución de capacidades efectivas del sujeto."""

    async def get(self, role_id: uuid.UUID) -> Role | None: ...
    async def add(self, role: Role) -> Role: ...
    async def update(self, role: Role) -> Role: ...

    async def delete(self, role_id: uuid.UUID) -> bool:
        """Borra un rol `tenant` (custom). True si borró una fila, False si no existía. Los roles
        `system` son inmutables por invariante de `rbac_service`/`validate_role_composition` — este
        puerto no lo comprueba, solo persiste."""
        ...

    async def list_capabilities(self, role_id: uuid.UUID) -> list[Capability]: ...

    async def list_all_capabilities(self) -> list[Capability]:
        """Catálogo COMPLETO de capacidades (`GET /admin/capabilities`, 06) — a diferencia de
        `list_capabilities(role_id)`, que devuelve solo las concedidas a un rol concreto."""
        ...

    async def effective_capabilities(
        self, user_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> set[tuple[str, str]]:
        """Conjunto `(capability_name, scope)` resuelto server-side, **acotado a `tenant_id`**
        (A1.7): sin este acotamiento, un usuario con roles distintos en dos tenants (ya soportado
        por `user_role.tenant_id`) filtraría capacidades de un tenant a la sesión activa en otro —
        fix de seguridad de `scenario-coverage`, no una ampliación discrecional."""
        ...

    async def assign(
        self, user_id: uuid.UUID, role_id: uuid.UUID, tenant_id: uuid.UUID | None
    ) -> None:
        """Concede `role_id` a `user_id` con el ámbito de asignación `tenant_id` (`None` → grant
        `global`, la fila `user_role.tenant_id` la lee `effective_capabilities`). PK real es
        `(user_id, role_id)` — reasignar el mismo par es un no-op idempotente (upsert), no un error:
        `admin_users` (06) reemplaza `roles[]` completo en cada `PATCH`, así que repetir un rol ya
        asignado es el caso normal, no una excepción."""
        ...

    async def unassign_all(self, user_id: uuid.UUID, tenant_id: uuid.UUID | None) -> None:
        """Retira TODAS las asignaciones de `user_id` en ese ámbito de `tenant_id` — usado por
        `admin_users` (06) para reemplazar `roles[]` completo (unassign-all + assign de la lista
        nueva, sin necesidad de diff)."""
        ...

    async def list_assigned(self, user_id: uuid.UUID, tenant_id: uuid.UUID) -> list[Role]:
        """Roles de `user_id` asignados en `tenant_id` (incl. los `system`/globales que apliquen ahí)
        — pinta `roles: [string]` en `/admin/users` (06)."""
        ...

    async def set_capabilities(self, role_id: uuid.UUID, capability_ids: list[uuid.UUID]) -> None:
        """Reemplaza el conjunto de `capability_ids` concedidas a `role_id` (delete-all + insert) —
        `admin_roles` (06) resuelve nombres del catálogo a ids ANTES de llamar (invariantes de
        `rbac_service.validate_role_composition` ya validadas en el router)."""
        ...

    async def list(self, tenant_id: uuid.UUID) -> list[Role]:
        """Roles visibles para `tenant_id`: la semilla `system` (`tenant_id IS NULL`) + los custom
        del propio tenant. Definido AL FINAL de la clase a propósito: nombrar un método `list`
        vincula ese nombre en el namespace del cuerpo de la clase, y sombrea el builtin `list` para
        cualquier anotación `list[...]` que aparezca DESPUÉS en el mismo cuerpo (peculiaridad de
        scoping de las class bodies de Python — `TypeError: 'function' object is not subscriptable`
        si se declara antes)."""
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


TICKET_SORT_FIELDS: frozenset[str] = frozenset({"updated_at", "created_at", "priority", "sla_due"})
"""Whitelist de columnas ordenables de `GET /tickets` (`api-contract.yaml`, `sort`). Única fuente de
verdad: el router valida `sort` contra esta whitelist ANTES de llamar al puerto (422 si no está, sin
tocar la base de datos — nunca se interpola un string arbitrario en SQL); el adaptador vuelve a
comprobarla como defensa en profundidad antes de traducirla a una columna ORM real."""


class TicketRepository(Protocol):
    """Puerto de `ticket`."""

    async def get(self, ticket_id: uuid.UUID) -> Ticket | None: ...
    async def add(self, ticket: Ticket) -> Ticket: ...
    async def update(self, ticket: Ticket) -> Ticket: ...

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        page: int,
        page_size: int,
        status: TicketStatus | None = None,
        priority: TicketPriority | None = None,
        domain: KbDomain | None = None,
        assignee_id: uuid.UUID | None = None,
        sort: str = "-updated_at",
    ) -> PageResult[Ticket]:
        """Orden por defecto `-updated_at` (contrato del puerto, FR-021); `sort` es un nombre de
        `TICKET_SORT_FIELDS` con prefijo `-` opcional (descendente) — YA validado por el llamante.
        `domain` es un filtro funcionalmente inerte hoy (ningún ticket tiene `domain` distinto de
        `None` hasta que exista un clasificador, planes 12/15); se implementa porque el contrato lo
        exige, no es un bug de esta tarea."""
        ...


class MessageRepository(Protocol):
    """Puerto de `message` + `attachment` (adjuntos, tarea 08 — el binario vive fuera de Postgres,
    vía el puerto `Storage`; aquí solo el metadato)."""

    async def add(self, message: Message) -> Message: ...

    async def get(self, message_id: uuid.UUID) -> Message | None: ...

    async def list_by_ticket(
        self,
        ticket_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 20,
        visibilities: list[MessageVisibility] | None = None,
    ) -> PageResult[Message]:
        """Orden `created_at` ascendente (contrato del puerto, `GET /tickets/{id}/messages`).

        `visibilities`: filtro a nivel de QUERY (no post-filtrado en el router) — sin él, `page.total`/
        el número de `items` de una página quedarían inconsistentes si el router descartara mensajes
        `internal` después de paginar. El router lo resuelve a `[public]` para un subject sin
        `note.internal.read`, o lo deja `None` (sin filtrar) si lo tiene."""
        ...

    async def add_attachment(self, attachment: Attachment) -> Attachment: ...

    async def get_attachment(self, attachment_id: uuid.UUID) -> Attachment | None: ...


APPROVAL_SORT_FIELDS: frozenset[str] = frozenset({"sla_due,confidence"})
"""Whitelist de `sort` de `GET /approvals` (`api-contract.yaml`): un ÚNICO valor literal válido (decisión
del owner, `scenario-coverage` — sin flexibilidad no pedida), no una lista de columnas componibles como
`TICKET_SORT_FIELDS`. El router valida `sort` contra esta whitelist ANTES de llamar al puerto (422 si no
coincide)."""


class ApprovalRepository(Protocol):
    """Puerto de `approval_task`, con CAS en `decide_if_pending`."""

    async def add(self, task: ApprovalTask) -> ApprovalTask: ...

    async def list(
        self,
        tenant_id: uuid.UUID | None,
        *,
        status: ApprovalStatus | None = None,
        sort: str = "sla_due,confidence",
        page: int,
        page_size: int,
    ) -> PageResult[ApprovalTask]:
        """Cola de aprobación paginada (reemplaza `list_pending`, tarea 12).

        `tenant_id=None` agrega **cross-tenant** (`scenario-coverage` #4, bug real corregido antes de
        implementar: `approval.decide` es una capacidad EXCLUSIVAMENTE `global` — `rbac.md §3`, solo
        Soporte, tenant `syntax` — pero las `ApprovalTask` pertenecen a los tenants CLIENTE, nunca a
        `syntax`; con `tenant_id` obligatorio, Soporte no vería jamás ninguna aprobación). Sin `status`
        filtra solo `pending` (preserva el comportamiento de `list_pending`); `sort` ya validado por el
        router contra `APPROVAL_SORT_FIELDS` antes de llegar aquí.
        """
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

    async def update_result(
        self,
        agent_run_id: uuid.UUID,
        *,
        status: AgentRunStatus,
        confidence: float | None = None,
        sources: list[dict[str, Any]] | None = None,
        error: str | None = None,
        escalated: bool | None = None,
        finished_at: datetime | None = None,
        langsmith_trace_url: str | None = None,
    ) -> AgentRun:
        """Persiste el resultado completo de un run (tarea `backend-agent-graph-08`): `status` +
        cualquier combinación de los campos de resultado, no solo el status (a diferencia de
        `update_status`). Cada argumento con default `None` SE ESCRIBE tal cual (no es un PATCH
        parcial que ignore lo no-pasado) — el llamante (`runner.py`) siempre sabe exactamente qué
        campos aplican al desenlace que está persistiendo (éxito/escalado/fallo).

        :raises app.domain.errors.PortError: si `agent_run_id` no existe o falla la escritura.
        """
        ...

    async def next_run_seq(self, ticket_id: uuid.UUID) -> int: ...

    async def get_active_for_ticket(self, ticket_id: uuid.UUID) -> AgentRun | None:
        """El `AgentRun` NO terminal (`queued`/`running`) de `ticket_id`, si existe.

        Pre-check **best-effort** (`agent_service.trigger`, tarea 12): da un uso real a este método
        antes de gastar cuota de rate-limit o tocar la constraint de BD en un disparo que va a fallar
        gratis. **No** es la garantía atómica real bajo concurrencia — eso lo da el índice único
        parcial de `agent_run` que `add()` traduce a `Conflict` (check-then-act con ventana de carrera,
        aceptado: dos requests concurrentes pueden ver ambas `None` aquí y solo una gana en `add()`).
        """
        ...


class NotificationRepository(Protocol):
    """Puerto de `notification`."""

    async def add(self, notification: Notification) -> Notification: ...

    async def get(self, notification_id: uuid.UUID) -> Notification | None:
        """Sin filtrar por `user_id` (el servicio decide el 404 comparando `user_id`, tarea 12) —
        distingue "no existe" de "es de otro usuario" para que el router pueda dar 404 en ambos casos
        sin revelar cuál, y a la vez permitir el `mark_read` idempotente (200) cuando SÍ es del
        usuario y ya estaba leída."""
        ...

    async def list_for_user(
        self, user_id: uuid.UUID, *, unread: bool | None = None, page: int, page_size: int
    ) -> PageResult[Notification]:
        """Orden `-created_at` (contrato del puerto, CU-BE-10). `unread=True` solo no leídas,
        `unread=False` solo leídas (filtro simétrico, `scenario-coverage`), `None`/ausente sin filtro."""
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
