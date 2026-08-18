"""app.infra.db.models.enums — enums nativos de Postgres (contrato: data-model.md §3).

Los **valores** string son el contrato literal (02/06 los referencian). Se usan como
etiquetas del tipo enum en Postgres vía :func:`pg_enum` (``values_callable``), no los
nombres de los miembros Python — necesario porque ``global`` es palabra reservada.
"""

import enum

from sqlalchemy import Enum


class TenantStatus(enum.Enum):
    """Estado de un tenant (soft-disable; no hard-delete)."""

    active = "active"
    disabled = "disabled"


class UserStatus(enum.Enum):
    """Estado de un usuario (soft-delete = ``disabled``; ``invited`` para el flujo B.3)."""

    invited = "invited"
    active = "active"
    disabled = "disabled"


class CapabilityScope(enum.Enum):
    """Ámbito de una capacidad RBAC (por tenant o global de Soporte)."""

    tenant = "tenant"
    global_ = "global"


class RoleKind(enum.Enum):
    """Tipo de rol: ``system`` (semilla inmutable) o ``tenant`` (custom por cliente)."""

    system = "system"
    tenant = "tenant"


class RefreshSessionStatus(enum.Enum):
    """Estado de una sesión de refresh (rotación + reuse-detection + logout server-side)."""

    active = "active"
    rotated = "rotated"
    revoked = "revoked"


class AuthTokenKind(enum.Enum):
    """Tipo de token de un solo uso (B.3)."""

    password_reset = "password_reset"  # noqa: S105 — etiqueta de enum, no un secreto
    invitation = "invitation"


class TicketStatus(enum.Enum):
    """Estado de un ticket (``reopened`` reabre el ciclo; sin ``on_hold`` en Fase 1)."""

    new = "new"
    open = "open"
    pending = "pending"
    resolved = "resolved"
    closed = "closed"
    reopened = "reopened"


class TicketPriority(enum.Enum):
    """Prioridad del ticket (la fija el clasificador, 05)."""

    low = "low"
    normal = "normal"
    high = "high"
    urgent = "urgent"


class MessageVisibility(enum.Enum):
    """Visibilidad de un mensaje (sin ``developer`` en Fase 1, 02 §6)."""

    public = "public"
    internal = "internal"


class ApprovalStatus(enum.Enum):
    """Estado de una tarea de aprobación HITL."""

    pending = "pending"
    approved = "approved"
    edited = "edited"
    rejected = "rejected"


class AgentRunStatus(enum.Enum):
    """Estado de una ejecución del grafo (``failed`` = fallo del LLM a mitad de run)."""

    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class NotificationType(enum.Enum):
    """Tipo de notificación in-app (data-model §3)."""

    approval_requested = "approval_requested"
    ticket_assigned = "ticket_assigned"
    ticket_reply = "ticket_reply"
    sla_breach = "sla_breach"
    sla_warning = "sla_warning"


class KbEstado(enum.Enum):
    """Señal de retrieval de un documento KB (peso explícito, 04)."""

    draft = "draft"
    active = "active"


class KbDomain(enum.Enum):
    """Los 17 dominios de la KB (data-model §3; contrato verificado contra la KB real)."""

    analytics_logs_and_activity = "analytics-logs-and-activity"
    authoring_and_editor = "authoring-and-editor"
    content_modeling_and_schemas = "content-modeling-and-schemas"
    data_collection_and_store = "data-collection-and-store"
    data_packs_and_distributors = "data-packs-and-distributors"
    forms_and_submissions = "forms-and-submissions"
    i18n_and_translations = "i18n-and-translations"
    identity_and_permissions = "identity-and-permissions"
    integrations_crm_and_feeds = "integrations-crm-and-feeds"
    media_and_dam = "media-and-dam"
    navigation_and_menus = "navigation-and-menus"
    platform_and_devex = "platform-and-devex"
    render_infra_and_config = "render-infra-and-config"
    rendering_and_publishing = "rendering-and-publishing"
    search_ai_and_llms = "search-ai-and-llms"
    seo_sitemaps_and_edge = "seo-sitemaps-and-edge"
    sites_domains_instances = "sites-domains-instances"


def pg_enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    """Enum nativo de Postgres cuyas etiquetas son los VALUES del enum (no los names).

    :param enum_cls: la clase ``enum.Enum`` de origen.
    :param name: nombre del tipo enum en Postgres (contrato literal de data-model §3).
    :returns: un ``sqlalchemy.Enum`` listo para ``mapped_column``.
    """
    return Enum(enum_cls, name=name, values_callable=lambda members: [m.value for m in members])
