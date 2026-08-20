"""app.core.deps — dependencias FastAPI comunes (punto de composición de la capa API).

`get_current_subject` resuelve el JWT (access) a un `Subject` con sus capacidades acotadas al tenant
de la sesión (`RoleRepository.effective_capabilities(user_id, tenant_id)`) — nunca desde el propio
JWT. `get_tenant_context` decide `global_scope`/`tenant_scope` por el **ámbito concedido de la
capacidad requerida** (no por un flag fijo del subject, decisión de `grilling`): si el subject tiene
`(cap, "global")` → abre `global_scope` (precedencia sobre `tenant`, aunque tenga ambos); si no y
tiene `(cap, "tenant")` → `tenant_scope(subject.tenant_id)`; si ninguno → `Deny(no_capability)`.
`require_capability` es la factory que los routers 06-09 reutilizan sin repetir esta lógica.
`require_any_capability` (tarea 12) es su variante OR: concede acceso si el subject tiene CUALQUIERA
de las capacidades dadas — primer caso de capacidad compuesta del backend (`GET /agent-runs/{id}`,
`agent.trigger` OR `ticket.read`).

Anti-patrón: resolver permisos desde el JWT (las capacidades se resuelven server-side, por request);
capturar el tenant en estado global compartido entre requests.
"""

import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AuthorizationDenied
from app.core.config import Settings, get_settings
from app.core.security import JWT_ALGORITHM, decode_access_token
from app.domain.entities.enums import TenantStatus
from app.domain.entities.identity import Subject
from app.domain.ports.rate_limiter import RateLimiter
from app.domain.ports.storage import Storage
from app.domain.ports.vectorstore import VectorStore
from app.domain.services.agent_service import AgentService
from app.domain.services.approval_service import ApprovalService
from app.domain.services.auth_service import AuthService
from app.domain.services.rbac_service import Deny, DenyReason
from app.domain.services.ticket_service import TicketService
from app.infra.agent_runner.stub import StubAgentRunner
from app.infra.clock import SystemClock
from app.infra.db.repositories import (
    SqlAlchemyAgentRunRepository,
    SqlAlchemyApprovalRepository,
    SqlAlchemyAuditLogRepository,
    SqlAlchemyAuthTokenRepository,
    SqlAlchemyMessageRepository,
    SqlAlchemyRefreshSessionRepository,
    SqlAlchemyRoleRepository,
    SqlAlchemyTenantRepository,
    SqlAlchemyTicketRepository,
    SqlAlchemyUserRepository,
    SqlAlchemyUserTenantMembershipRepository,
)
from app.infra.db.session import get_session, global_scope, tenant_scope
from app.infra.email import StubEmailPort
from app.infra.rate_limit.in_memory import InMemoryRateLimiter
from app.infra.sla import StubSlaPolicy
from app.infra.storage.local import LocalFilesystemStorage
from app.infra.vectorstore.stub import StubVectorStore

_ACCESS_TOKEN_PURPOSE = "access"  # noqa: S105 — claim `purpose`, no un secreto

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login", auto_error=False)


def _unauthorized() -> HTTPException:
    """401 genérico: no distingue token ausente/expirado/con purpose incorrecto/tenant disabled."""
    return HTTPException(status_code=401)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Dependency que cede una `AsyncSession` por request y la cierra (delega en `session.py`)."""
    async for session in get_session():
        yield session


def get_auth_service(session: AsyncSession = Depends(get_db_session)) -> AuthService:
    """Ensambla `AuthService` con los adaptadores reales (una instancia por request)."""
    return AuthService(
        users=SqlAlchemyUserRepository(session),
        memberships=SqlAlchemyUserTenantMembershipRepository(session),
        tenants=SqlAlchemyTenantRepository(session),
        refresh_sessions=SqlAlchemyRefreshSessionRepository(session),
        auth_tokens=SqlAlchemyAuthTokenRepository(session),
        email=StubEmailPort(),
        clock=SystemClock(),
    )


def get_ticket_service(session: AsyncSession = Depends(get_db_session)) -> TicketService:
    """Ensambla `TicketService` con los adaptadores reales. `SlaPolicy` es el stub de la tarea 07
    (`data-model.md` §11: la política real de SLA es la tarea 18, aquí `sla_due` siempre queda
    `None`)."""
    return TicketService(
        tickets=SqlAlchemyTicketRepository(session),
        messages=SqlAlchemyMessageRepository(session),
        audit_log=SqlAlchemyAuditLogRepository(session),
        sla_policy=StubSlaPolicy(),
        clock=SystemClock(),
    )


def get_storage(settings: Settings = Depends(get_settings)) -> Storage:
    """Ensambla el adaptador de `Storage` (tarea 08) — filesystem local (`settings.storage_root`);
    nube diferida, el puerto ya lo permite sin cambiar la firma."""
    return LocalFilesystemStorage(settings.storage_root)


def get_vector_store() -> VectorStore:
    """Ensambla el adaptador de `VectorStore` (tarea 09) — stub sin estado hasta el retriever real
    (tarea 14); sin parámetros de construcción, no necesita ninguna dependencia."""
    return StubVectorStore()


@lru_cache
def _rate_limiter_singleton(limit: int) -> RateLimiter:
    """Instancia ÚNICA de `InMemoryRateLimiter` por valor de `limit` (proceso) — `lru_cache` evita
    crear un contador nuevo en cada request, que nunca acumularía cuota (mismo criterio que
    `get_settings`, cacheada por argumento en vez de sin argumentos)."""
    return InMemoryRateLimiter(limit=limit)


def get_agent_service(
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> AgentService:
    """Ensambla `AgentService` (tarea 12) con `StubAgentRunner` (sin grafo real hasta 15/16 — persiste
    el `AgentRun` vía el MISMO `AgentRunRepository`, sin duplicar instancias sobre la misma sesión) y el
    `RateLimiter` singleton de proceso (`ai_draft_rate_limit_per_minute`)."""
    agent_runs = SqlAlchemyAgentRunRepository(session)
    return AgentService(
        tickets=SqlAlchemyTicketRepository(session),
        agent_runs=agent_runs,
        agent_runner=StubAgentRunner(agent_runs),
        rate_limiter=_rate_limiter_singleton(settings.ai_draft_rate_limit_per_minute),
    )


def get_approval_service(session: AsyncSession = Depends(get_db_session)) -> ApprovalService:
    """Ensambla `ApprovalService` (tarea 12) con `TicketService`/`StubAgentRunner` reales — `decide()`
    ya estaba cerrado en `domain-services`, esta tarea solo le da adaptadores de verdad."""
    return ApprovalService(
        approvals=SqlAlchemyApprovalRepository(session),
        ticket_service=get_ticket_service(session),
        agent_runner=StubAgentRunner(SqlAlchemyAgentRunRepository(session)),
    )


async def get_current_subject(
    token: str | None = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> Subject:
    """JWT (`purpose=access`) → `Subject` con capacidades acotadas al tenant de la sesión.

    401 si: sin token, firma inválida, expirado, `purpose` distinto de `access` (p.ej. un
    `identity_token` usado como Bearer), o el tenant de la sesión está `disabled`.
    """
    if token is None:
        raise _unauthorized()
    try:
        claims = decode_access_token(token, secret=settings.jwt_secret, algorithm=JWT_ALGORITHM)
    except jwt.InvalidTokenError as exc:
        raise _unauthorized() from exc
    if claims.get("purpose") != _ACCESS_TOKEN_PURPOSE:
        raise _unauthorized()

    user_id = uuid.UUID(claims["sub"])
    tenant_id = uuid.UUID(claims["tenant_id"])

    tenant = await SqlAlchemyTenantRepository(session).get(tenant_id)
    if tenant is None or tenant.status is TenantStatus.disabled:
        raise _unauthorized()

    capabilities = await SqlAlchemyRoleRepository(session).effective_capabilities(
        user_id, tenant_id
    )
    return Subject(id=user_id, tenant_id=tenant_id, capabilities=capabilities)


@asynccontextmanager
async def _scope_for_any_capability(
    session: AsyncSession, subject: Subject, capabilities: tuple[str, ...]
) -> AsyncIterator[AsyncSession]:
    """Abre `global_scope`/`tenant_scope` según el ámbito CONCEDIDO de CUALQUIERA de `capabilities`
    (OR) para `subject` (nunca por un flag fijo del subject). Con una sola capacidad, este es el
    comportamiento de `get_tenant_context`; con varias, basta con que UNA la conceda — precedencia de
    ámbito (`scenario-coverage` #7): si CUALQUIERA de las capacidades la concede en `global`, gana
    `global` (el orden de `capabilities` no importa); si no, y CUALQUIERA la concede en `tenant`, abre
    `tenant_scope`; si ninguna concede ninguna, `Deny(no_capability)`."""
    if any((cap, "global") in subject.capabilities for cap in capabilities):
        async with global_scope(session) as scoped:
            yield scoped
        return
    if any((cap, "tenant") in subject.capabilities for cap in capabilities):
        async with tenant_scope(session, subject.tenant_id) as scoped:
            yield scoped
        return
    raise AuthorizationDenied(Deny(DenyReason.no_capability))


@asynccontextmanager
async def get_tenant_context(
    session: AsyncSession, subject: Subject, capability: str
) -> AsyncIterator[AsyncSession]:
    """Abre `global_scope`/`tenant_scope` según el ámbito CONCEDIDO de `capability` para `subject`
    (nunca por un flag fijo del subject). Si el subject tiene la capacidad en ambos ámbitos, gana
    `global`. `Deny(no_capability)` si no la tiene en ninguno."""
    async with _scope_for_any_capability(session, subject, (capability,)) as scoped:
        yield scoped


def require_capability(
    capability: str,
) -> Callable[..., AsyncIterator[tuple[Subject, AsyncSession]]]:
    """Factory de dependencia: exige `capability`, cede `(subject, session-ya-en-scope)` al router."""

    async def _dependency(
        subject: Subject = Depends(get_current_subject),
        session: AsyncSession = Depends(get_db_session),
    ) -> AsyncIterator[tuple[Subject, AsyncSession]]:
        async with get_tenant_context(session, subject, capability) as scoped:
            yield subject, scoped

    return _dependency


def require_any_capability(
    *capabilities: str,
) -> Callable[..., AsyncIterator[tuple[Subject, AsyncSession]]]:
    """Factory de dependencia: exige CUALQUIERA de `capabilities` (OR, tarea 12) — primer caso de
    capacidad compuesta del backend (`GET /agent-runs/{id}`, `agent.trigger` OR `ticket.read`)."""

    async def _dependency(
        subject: Subject = Depends(get_current_subject),
        session: AsyncSession = Depends(get_db_session),
    ) -> AsyncIterator[tuple[Subject, AsyncSession]]:
        async with _scope_for_any_capability(session, subject, capabilities) as scoped:
            yield subject, scoped

    return _dependency
