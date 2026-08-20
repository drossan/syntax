"""app.domain.entities.enums — enums propios del dominio (data-model.md §3).

Mismo conjunto de VALORES que `app.infra.db.models.enums` (protegido por el test de drift), pero
definidos aquí de forma independiente: el dominio no importa el ORM.
"""

import enum


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
    """Estado de un ticket (``reopened`` es un estado de reposo real, CU-BE-04)."""

    new = "new"
    open = "open"
    pending = "pending"
    resolved = "resolved"
    closed = "closed"
    reopened = "reopened"


class TicketPriority(enum.Enum):
    """Prioridad del ticket (la fija el clasificador)."""

    low = "low"
    normal = "normal"
    high = "high"
    urgent = "urgent"


class MessageVisibility(enum.Enum):
    """Visibilidad de un mensaje (sin ``developer`` en Fase 1)."""

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
    """Tipo de notificación in-app."""

    approval_requested = "approval_requested"
    ticket_assigned = "ticket_assigned"
    ticket_reply = "ticket_reply"
    sla_breach = "sla_breach"
    sla_warning = "sla_warning"


class KbDomain(enum.Enum):
    """Los 17 dominios de la KB (data-model §3)."""

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


class KbEstado(enum.Enum):
    """Señal de retrieval de un documento KB (peso explícito, `data-model.md` §4.3)."""

    draft = "draft"
    active = "active"


class Package(enum.Enum):
    """Paquete/producto de Syntax al que pertenece un documento de KB (`api-contract.yaml`)."""

    syntax_api = "syntax-api"
    syntax_cx = "syntax-cx"
    syntax_core = "syntax-core"
    syntax_ax = "syntax-ax"
    syntax_render = "syntax-render"
