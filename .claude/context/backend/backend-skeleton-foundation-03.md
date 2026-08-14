# Session log — backend-skeleton-foundation-03 (Spec modelo de datos: entidades, ERD, RLS)

## 2026-08-13 — Arranque

**Estado:** tarea movida `pending → active` (`status: active`, `updated: 2026-08-13`). Depends_on
`backend-skeleton-foundation-02` verificado `done`. Doc-only (plan escape-hatch: sin TDD ni gate de
mutation; sí gate `fact-checker`).

**Verificaciones previas a redactar (esta sesión):**
- Spec RBAC (02) leída: capacidades (14), roles semilla (6), ámbitos `tenant|global`, visibilidad
  `public|internal`, aislamiento app-level + RLS, KB global sin RLS. Los enums/nombres se reusan literal.
- KB real (`~/Documents/Desarrollo/syntax/docs-site/domains`): **17 dominios**; 286 .md = **268 UC + 18
  index**; frontmatter `title/domain/package/uc` (**0** ficheros con `url:`); bloque `::: info
  Trazabilidad` en **268** UC con `Estado`(draft/active)/`Package`/`Traza`(rutas de código fuente).
  → `KBDocument.source_url` es **derivado** (no hay url en el frontmatter); `estado`/`traza` vienen del
  bloque Trazabilidad; precedencia `package`: frontmatter gana (coord. 04).

## 2026-08-13 — Cierre

**Resumen:** Escrita `.claude/specs/backend/data-model.md`: 3 grupos de entidades (identidad/RBAC,
negocio, KB global), 13 enums de contrato, 18 tablas con claves/relaciones/índices, ERD mermaid, marca
RLS por tabla, política de borrado/cascada/retención, dimensión de vector parametrizable + coste de
re-embed, e índices (incl. pgvector). Cierra los 6 Refuerzos (scenario-coverage) en checklist.

**Decisiones técnicas + porqué:**
- `agent_run.langgraph_thread_id = ticket_{id}_run_{n}` + `run_seq` → re-draft tras reopen sin colisionar
  el checkpoint anterior (A1.2).
- `refresh_session` con `family_id`/`parent_id` + estado → rotación + reuse-detection (revoca familia) +
  logout server-side (A1.5). `auth_token(kind)` para reset/invitación (B.3, email stub).
- FK on-delete: `requester_id`/`assignee_id`/`author_id`/`decided_by`/`actor_id` → SET NULL (preservar
  histórico); agregado ticket y KB → CASCADE; `tenant` → RESTRICT (soft-disable por `status`, no
  hard-delete). Retención/GDPR = hueco explícito (modelo lo habilita, no lo implementa).
- `embedding.vector(N)` con N desde config (`EMBEDDING_DIM`, default 1536); documentado coste de
  re-embed + reconstrucción de índice al cambiar N.
- `kb_document.source_url` **derivado** de la ruta (la KB real no trae `url` en frontmatter, verificado);
  `estado`/`traza` del bloque Trazabilidad; precedencia `package`: frontmatter gana (coord. 04).
- `ticket.domain` = enum de 17 dominios (verificado contra KB); `ticket.category` = string libre (no
  acoplar el modelo a la taxonomía del clasificador). Enums de visibilidad/scope/approval reusados
  literal de 02.

**Verificación (gate `fact-checker`, subagente fresco, sonnet por config):** 9/9 **VERIFICADO**, 0
INCORRECTO, 0 NO VERIFICABLE. Cubrió: 17 dominios KB, 286 md = 268 UC + 18 index, frontmatter sin `url`,
bloque Trazabilidad en 268 (218 draft / 50 active exacto), coherencia enums data-model↔rbac, estados de
tareas 02/03, `models.fact-checker: sonnet`. Doc-only: sin TDD ni gate de mutation (escape hatch del plan).

**Docs actualizadas:** `.claude/specs/backend/data-model.md` (nuevo, deliverable). Plan: `[x]` tarea 03
+ entrada en Registro de cambios.

**Ficheros/commits:** `.claude/specs/backend/data-model.md` (nuevo); task 03 pending→active→completed;
session log; plan actualizado. (Commit pendiente de que el owner lo pida.)

**Tiempo real:** ~0.75 h.

**Follow-ups:** 08 materializa modelos/migraciones/RLS desde aquí (con el aviso footgun `SET app.tenant_id`
en pool async + tests de integración); 06 deriva schemas de API y **debe reusar estos enums**; 10/18
asumen estas entidades; 04 fija el parseo fino frontmatter/Trazabilidad + chunking H2. Hueco explícito:
política de retención/GDPR sin definir antes de producción.
