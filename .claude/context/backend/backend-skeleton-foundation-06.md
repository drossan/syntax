# Session log — backend-skeleton-foundation-06 (Spec contrato de API, OpenAPI-first)

## 2026-08-13 — Arranque

**Estado:** tarea movida `pending → active` (`status: active`, `updated: 2026-08-13`). Deps 02/03/04/05
verificadas `done`. Doc-only. Es la **dependencia dura cross-plan** (frontend-02 deriva tipos + mocks).

**Decisión de formato (owner, AskUserQuestion):** materializar como **`.yaml` (OpenAPI 3.1 real, fuente
única) + `.md` fino** (companion con convenciones + puntero al `.yaml`). Motivo: "machine-readable, no
prosa" (design-review C1) + el frontend genera tipos/valida mocks con tooling → necesita un fichero
machine-readable; el `.md` preserva la ruta que citan `CLAUDE.md` y las otras specs.
→ `.claude/specs/general/api-contract.yaml` + `.claude/specs/general/api-contract.md`.

**Fuentes de coherencia (specs leídas esta sesión):** 02 (capacidades/roles/scope/visibilidad), 03
(entidades+enums: ticket_status/priority, message_visibility, approval_status, agent_run_status,
kb_domain(17), kb_estado, notification_type, auth_token_kind), 04 (kb search filtros domain/package/
estado, orden por score), 05 (ai-draft/approvals/agent-runs; 409 en doble decisión).

## 2026-08-13 — Cierre

**Resumen:** Creado el contrato compartido como **`.claude/specs/general/api-contract.yaml`** (OpenAPI
3.1, fuente única) + **`api-contract.md`** (companion fino: convenciones + puntero al `.yaml`). Cubre:
auth (login/refresh/logout/me + password forgot/reset/change), tickets (CRUD + transition + assign),
messages (con visibilidad public/internal server-side) + attachments, flujo-IA (ai-draft, cola
`/approvals`, approve/edit/reject con **409** en doble decisión, `/agent-runs/{id}`), KB (search + docs
con filtros domain/package/estado), admin (tenants/users+invite/roles+capabilities role builder/settings
`auto_approve`), analytics/summary, notifications (+read). Envelope de error problem+json (`Problem`),
paginación, orden determinista por listado, i18n del error por `Accept-Language`.

**Decisión de formato (owner):** `.yaml` (OpenAPI real) + `.md` companion — para que el frontend genere
tipos/valide mocks con tooling y se preserve la ruta `.md` que citan CLAUDE.md/specs. La fuente única es
el `.yaml`; el `.md` no duplica el schema.

**Verificación en sesión (bucle principal):** YAML parsea como `3.1.0`; **32 paths, 38 schemas, 7
responses**; **los 48 `$ref` distintos resuelven** (script python). Enums/capacidades/flujo-IA/KB
alineados con 02/03/04/05.

**Verificación (gate `fact-checker`, subagente fresco, sonnet por config):** **9/9 VERIFICADO**, 0
INCORRECTO, 0 NO VERIFICABLE. Cubrió: parseo+conteos (D1), $refs resuelven (D2), enums == 03 (D3),
capacidades ∈ 02 (D4), flujo-IA+409 == 05 (D5), kb/search filtros == 04 (D6), envelope problem+json (D7),
companion no duplica el schema (D8), y **D9 (honestidad)**: no se afirma validación formal contra el
meta-schema OpenAPI (tool ausente).

**Aviso reconocido (NO VERIFICABLE por falta de tooling):** `openapi-spec-validator` **no está
instalado** → NO se validó formalmente contra el meta-schema OpenAPI 3.1; solo parseo YAML + resolución
de `$ref`. No bloquea (doc-only); el gate real de conformidad lo aportan 11/12 (OpenAPI generado ⊇
contrato, tarea 19) y el frontend-02 (validación de mocks).

**Docs:** `api-contract.yaml` (nuevo) + `api-contract.md` (nuevo). Plan: `[x]` tarea 06 + Registro.

**Ficheros/commits:** dos ficheros nuevos en `.claude/specs/general/`; task 06 pending→active→completed;
session log; plan. (Commit pendiente de que el owner lo pida.)

**Tiempo real:** ~1.25 h.

**Follow-ups:** 07 (skeleton core) ya arrancable (dep 01). 11/12 implementan routers/schemas contra este
contrato; 19 añade el gate "OpenAPI generado ⊇ contrato"; frontend-02 genera cliente tipado + mocks MSW.
Al compilar el lockfile del backend, considerar añadir `openapi-spec-validator` para un gate formal.
