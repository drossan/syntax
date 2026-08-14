"""app.infra.db.models — modelos SQLAlchemy 2 (una clase por entidad de 03).

GUIÓN (→ tarea 08) — materializa `.claude/specs/backend/data-model.md` (03)
--------------------------------------------------------------------------
Una clase ``Mapped`` por entidad, agrupadas como en 03. Marca de RLS (§6) y cascadas (§7) tal cual.
Repartir en submódulos (p.ej. ``identity.py``/``business.py``/``kb.py``) o un fichero por grupo; todas
heredan de ``app.infra.db.base.Base``.

IDENTIDAD / RBAC (cross-tenant de sistema — SIN RLS de fila por tenant; el ámbito lo da el RBAC 02):
  - ``Tenant`` (slug único, status active|disabled), ``User`` (email único por tenant, password_hash
    argon2 nullable, status invited|active|disabled, sso_subject nullable Fase 2),
  - ``Capability`` (name único, scope tenant|global), ``Role`` (kind system|tenant, tenant_id nullable,
    único (tenant_id,name)), ``RoleCapability`` (PK role_id+capability_id), ``UserRole`` (PK user_id+role_id),
  - ``RefreshSession`` (token_hash único, family_id, parent_id nullable, status, expires_at) → rotación +
    reuse-detection + logout server-side, ``AuthToken`` (kind password_reset|invitation, token_hash único).

NEGOCIO (todas con ``tenant_id`` + **RLS**):
  - ``Ticket`` (status new|open|pending|resolved|closed|reopened; priority low|normal|high|urgent;
    domain kb_domain(17); category str; requester_id/assignee_id FK→user **SET NULL**; sla_due; csat),
  - ``Message`` (visibility public|internal; is_ai_draft; author_id SET NULL; ticket_id **CASCADE**),
  - ``Attachment`` (message_id CASCADE; storage_key — binario fuera de Postgres),
  - ``ApprovalTask`` (status pending|approved|edited|rejected; draft_body/final_body/human_note;
    agent_run_id CASCADE; ticket_id CASCADE),
  - ``AgentRun`` (langgraph_thread_id=``ticket_{id}_run_{n}``, run_seq; status queued|running|succeeded|
    **failed**; confidence; escalated; sources JSONB; error; langsmith_trace_url; ticket_id CASCADE),
  - ``AuditLog`` (append-only; actor_id SET NULL; payload JSONB), ``Notification`` (type; read_at; user_id CASCADE).

KB (GLOBAL — **sin RLS de tenant**; 03 §4.3):
  - ``KBDocument`` (uc_id único; domain; package; estado draft|active; title; source_url derivado;
    traza JSONB; upsert por uc_id),
  - ``KBChunk`` (document_id **CASCADE**; section_type str libre; token_count; ordinal),
  - ``Embedding`` (chunk_id CASCADE 1:1; model; ``vector(N)`` con **N = settings.EMBEDDING_DIM**, no literal).

ÍNDICES (03 §9): único ``kb_document.uc_id``; pgvector sobre ``embedding.vector`` (ivfflat/hnsw — decidir
en migración); ``ticket (tenant_id,status)``/``(tenant_id,assignee_id)``/``(tenant_id,sla_due)``;
``message (ticket_id,created_at)``; ``agent_run (ticket_id,run_seq)``; único ``user (tenant_id,email)`` y
``refresh_session.token_hash``.

Anti-patrón: hardcodear la dimensión del vector; poner RLS a las tablas KB; exponer estos modelos al dominio.
"""
