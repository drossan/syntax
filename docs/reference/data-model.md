# Referencia · Modelo de datos

**Fuente canónica:** `.claude/specs/backend/data-model.md`. Aquí un resumen navegable; para claves, índices
y cascadas exactas, ver la spec.

## Grupos de entidades (18 tablas)

| Grupo | Tablas | `tenant_id` + RLS |
|---|---|:--:|
| Identidad / RBAC | `tenant`, `user`, `capability`, `role`, `role_capability`, `user_role`, `refresh_session`, `auth_token` | — (gobernado por RBAC) |
| Negocio | `ticket`, `message`, `attachment`, `approval_task`, `agent_run`, `audit_log`, `notification` | ✅ |
| KB (global) | `kb_document`, `kb_chunk`, `embedding` | ❌ (compartida) |

## Enums (contrato)

- `ticket_status`: `new · open · pending · resolved · closed · reopened`
- `ticket_priority`: `low · normal · high · urgent`
- `message_visibility`: `public · internal` (sin `developer` — Fase 2)
- `approval_status`: `pending · approved · edited · rejected`
- `agent_run_status`: `queued · running · succeeded · failed`
- `kb_estado`: `draft · active` · `kb_domain`: los 17 dominios de la KB

## Puntos clave

- **RLS** en todas las tablas de negocio (política por `tenant_id`); KB e identidad sin RLS de tenant.
- **`embedding.vector(N)`** con `N = EMBEDDING_DIM` (config, default 1536), **no** literal. Cambiarla
  obliga a re-embeber todo + reconstruir el índice pgvector.
- **Borrado/cascada**: `requester_id`/`assignee_id`/`author_id` → SET NULL; agregado ticket y KB →
  CASCADE; `tenant` → RESTRICT (soft-disable por `status`). Retención/GDPR: hueco explícito a definir.
- **`agent_run`**: `langgraph_thread_id = ticket_{id}_run_{n}` + `run_seq` (re-draft por reapertura);
  `confidence`, `escalated`, `sources` (citas), `langsmith_trace_url`.
- **`refresh_session`**: `token_hash` + `family_id` + `parent_id` → rotación + reuse-detection + logout
  server-side.

Ver el ERD completo (mermaid) en la spec canónica.
