---
id: backend-skeleton-foundation-03
package: backend
plan: skeleton-foundation
status: done
priority: 1
depends_on: [backend-skeleton-foundation-02]
estimate: 3h
actual: 0.75h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# Spec modelo de datos (entidades, ERD, RLS)

## Description

Escribir `.claude/specs/backend/data-model.md`: entidades, relaciones y ERD del helpdesk multi-tenant,
incluyendo el modelo RBAC (02), las tablas de KB (globales) y las de negocio (con RLS). Fuente para el
skeleton de DB (08), los servicios (10) y el contrato (06).

## Spec

- **Tenancy/identidad**: `Tenant` (incl. tenant-sistema `syntax`), `User` (email, password_hash argon2,
  `tenant_id`, status; `sso_subject` nullable para Fase 2), `Capability`, `Role` (system|tenant-scoped),
  `RoleCapability`, `UserRole`.
- **Negocio (con `tenant_id` + RLS)**: `Ticket` (status new/open/pending/resolved/closed/reopened;
  `priority`; `sla_due`; `domain`+`category` fijados por el clasificador → 17 dominios; `requester_id`;
  `assignee_id`; `csat`), `Message` (`visibility public|internal`, `is_ai_draft`, `author_id`),
  `Attachment` (puerto storage), `ApprovalTask` (pending/approved/edited/rejected; `human_note`),
  `AgentRun` (`langgraph_thread_id`=ticket, `confidence`, `sources`, `langsmith_trace_url`),
  `AuditLog`, `Notification`.
- **KB (global, sin RLS de tenant)**: `KBDocument` (`uc_id` único, `domain`, `package`, `estado`,
  `title`, `source_url`, `traza`, `updated`), `KBChunk` (`section_type`, `content`, `token_count`),
  `Embedding` (`vector(N)` — **N desde config**, no hardcodeado; documentar coste de re-embed al cambiar).
- **RLS**: qué tablas la llevan (todas las de negocio) y el patrón `SET app.tenant_id` (detalle en 08).
- **ERD** (mermaid o tabla de relaciones), claves, índices (incl. índice pgvector ivfflat/hnsw), enums.

## Refuerzos (scenario-coverage)

- `AgentRun.status` incluye **`failed`** (fallo del LLM a mitad de run).
- **Borrado/retención/cascada**: FK `on-delete` por relación (`assignee_id`/`requester_id` set-null,
  `KBDocument→KBChunk/Embedding` cascade, `Tenant`), **soft-delete** (`User.status`) vs hard, política de
  retención/GDPR — hoy sin definir.
- **`RefreshSession`** (token store): habilita **rotación + reuse-detection + logout server-side** (A1.5).
- **Tokens de password-reset/invitación** (B.3, promovido).
- `thread_id` del agente con **secuencia de run** (`ticket_{id}_run_{n}`) para re-draft tras reopen (A1.2).
- Precedencia si difieren `package` del frontmatter vs Trazabilidad (frontmatter gana) — coord. con 04.

## Fuera de alcance

- Crear las tablas/migraciones (eso es 08); aquí solo la spec/ERD.
- Campo/visibilidad `developer_note` (Fase 2, diferido).
- Política/horario de SLA (solo se modelan `priority`+`sla_due`).

## Scenarios (Gherkin)

<!-- Doc-only. -->
**Verificación (doc-only):**
- Toda tabla de negocio tiene `tenant_id` y está marcada como sujeta a RLS; las tablas de KB no lo tienen.
- La dimensión del vector se declara parametrizable (config), no un literal.
- Los enums (status ticket, visibility, priority, approval status) coinciden con rbac (02) y api-contract (06).
- El ERD es completo (todas las FKs) y no hay entidades huérfanas.

## Provides

- `.claude/specs/backend/data-model.md`: entidades + ERD + enums + marca RLS + tablas KB globales. 08 crea
  modelos/migraciones desde aquí; 06 deriva los schemas de la API; 10/17 asumen estas entidades.

## Definition of Done

- [x] Spec + ERD creados; todas las entidades del alcance presentes con claves/relaciones/índices.
- [x] RLS marcada en tablas de negocio; KB global sin RLS; dimensión vector parametrizable.
- [x] Enums coherentes con 02 y 06. <!-- 06 aún no existe; enums fijados como contrato para que 06 los reuse. -->
- [x] `Provides` disponible para las dependientes.
- [x] Gate de `fact-checker` superado (sonnet): 9/9 VERIFICADO, 0 INCORRECTO, 0 NO VERIFICABLE.
- [x] Histórico en `.claude/context/backend/backend-skeleton-foundation-03.md`.
