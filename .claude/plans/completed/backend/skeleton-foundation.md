---
id: backend-skeleton-foundation
package: backend
status: completed       # pending | active | completed | cancelled
branch: plan/backend/skeleton-foundation
created: 2026-08-11
updated: 2026-08-13
---

# Backend — Esqueleto de fundación (FastAPI + LangGraph + Postgres/pgvector)

## Contexto y problema

Syntax necesita un backend Python para un helpdesk con IA generativa. Existen **dos demos
desechables** (Streamlit): `~/Downloads/helpdesk_system` (aporta la **idea del grafo con aprobación
humana** — `interrupt_before` + checkpointer) y `~/Downloads/multiuser_chat_system` (aporta un
**grafo multi-nodo con estado `add_messages`, `trim_messages`, checkpointer por thread y extracción
Pydantic**). Ninguna trae FastAPI, auth real, Postgres/pgvector, LangSmith, streaming, HITL sobre
API ni async: eso es **trabajo nuevo**.

Este plan **no implementa el backend**: produce su **esqueleto completo** (estructura de ficheros),
las **specs** (Spec-Driven Design) y un **guión por fichero** de qué implementar. Lo construirá a
mano el owner como práctica de LangChain/LangGraph/LangSmith. Se **conserva la idea del grafo** de
ambas demos y se **reemplaza todo lo demás**: FastAPI async, Postgres+pgvector (negocio + embeddings
en el mismo Postgres), SQLAlchemy 2/Alembic, RBAC multi-tenant (capacidades + roles custom por
tenant), aislamiento app-level **+ RLS**, abstracción de proveedor LLM y tracing LangSmith.

## Objetivos

1. **Estructura del proyecto completa, navegable y "seguible" a mano**.
   - *Criterio de éxito*: el layout hexagonal existe; cada fichero de esqueleto tiene su guión;
     `docker-compose config` y `pyproject`/`requirements` validan; hay **seeds** que permiten ejercer
     login→ticket→draft→aprobación sin escribir datos a mano; `/health` comprueba DB + pgvector.
2. **Specs que fijan los contratos** (rbac, data-model, api-contract, rag-ingestion, agent-graph),
   coherentes entre sí y con la KB real.
   - *Criterio de éxito*: verificables por bullets, sin contradicciones; el `api-contract` incluye
     **envelope de error** y es **única fuente de verdad** (la guía añade un gate "OpenAPI generado ⊇ contrato").
3. **Contrato de API compartido** derivable por el frontend (tipos + mocks, incl. mocks de error).
4. **El núcleo de riesgo (HITL/checkpointer) especificado a fondo**, no despachado.
   - *Criterio de éxito*: la spec del agente describe el modelo `interrupt → endpoint de aprobación →
     resume desde checkpoint Postgres`, incluyendo reinicio a mitad de run y ediciones concurrentes.
5. **Guión maestro** que ordene la construcción real.

## Alcance y fuera de alcance

### Dentro del alcance
- Estructura + guión de todo el backend; specs (rbac, data-model, api-contract, rag-ingestion,
  agent-graph); scaffolding (requirements pip-tools, ruff/mypy/pytest, Dockerfile, docker-compose
  Postgres+pgvector, Alembic, `.env.example`, README, Makefile).
- **RBAC**: capacidades + ámbito **con roles custom por tenant** (`Capability`/`Role` sistema+tenant/
  `RoleCapability`) + endpoints de gestión + (en el otro plan) role builder. Visibilidad de mensajes
  Fase 1: **`public | internal`**.
- **Aislamiento**: app-level en repos **+ RLS** (políticas Alembic + `SET app.tenant_id` por conexión).
  KB **compartida, sin RLS de tenant**.
- **Ingestión** contra la fuente real `domains/*/uc/*.md`: frontmatter **`title/domain/package/uc`**
  (no `url`) + bloque `::: info Trazabilidad` (`Estado`/`Traza`) + **glosario** de los `index.md`.
  Chunking **por sección H2 tolerante** (H2 casi-uniformes: `Comportamiento`/`Conceptos`/`Reglas`/
  `Detalles QA`/`Fidelidad`, con variantes y H2 sueltos → no asumir estructura rígida). Categorización
  dominio(17)/UC-id/package(5)/estado/tipo-de-sección; `estado` draft(218)/active(50) como señal con
  **peso explícito** (no penalizar draft a ciegas: es el 81% del corpus). Upsert idempotente por `uc-id`.
- **Agente** (patrón de las demos): grafo multi-nodo `retrieve(RAG) → grade → generate → classify`;
  estado `add_messages` + campos de dominio; `trim_messages`; **clasificador de ticket** (Pydantic →
  dominio/prioridad); checkpointer **Postgres** por `thread_id`=ticket; nodo **HITL**; confianza
  híbrida (similitud + grade) → auto vs escalado; insuficiente → nota al humano; auto-asunto opcional.

### Fuera de alcance
- Implementar el **código de negocio** (solo esqueleto + guión + specs).
- **SSO/OIDC Fase 2** (hueco en auth, no implementado).
- **Nota al desarrollador / KB de código (Fase 2)**: **diferida por completo** — sin campo/nodo/
  visibilidad `developer` en Fase 1 (se asume migración en Fase 2).
- **Streaming SSE del draft IA**: *seam* diseñado (el grafo permitirá `astream`), pero en Fase 1 el
  draft se entrega por request/polling, no token-a-token.
- CI/CD, despliegue, tiempo real/streaming SSE, BM25 híbrido, storage S3, colas/workers **generales**
  (excepto el scheduler de SLA), SSO/OIDC (Fase 2) — seams diferidos.
- **Promovidos a Fase 1 desde scenario-coverage**: throttling básico de login + límite de `ai-draft`
  (B.1), scheduler de vencimiento/escalado de SLA (B.2, tarea 18), endpoints de reset/invitación de
  contraseña con **email en stub** (B.3). Siguen diferidos: rate-limiting/email **generales**, webhooks/
  push, antivirus de adjuntos, BM25, SSO/OIDC, nota al desarrollador (B.4–B.8).
- **Recrear** los `domains/*/uc/*.md` (lo hace el owner; ya restaurados, 286 .md = 268 UC + 18 index).

## Recursos externos

- Demos de referencia (patrones, NO copiar la persistencia/UI): `~/Downloads/helpdesk_system`
  (grafo HITL `interrupt_before`) y `~/Downloads/multiuser_chat_system` (grafo multi-nodo, estado
  `add_messages`, `trim_messages`, checkpointer por thread, extracción `PydanticOutputParser`,
  auto-título LLM, envelope de respuesta uniforme). **Anti-patrones a evitar**: Streamlit, filesystem
  por usuario, singleton global de chatbot, `SqliteSaver`, ChromaDB, "auth" por carpeta.
- KB: `~/Documents/Desarrollo/syntax/docs-site/domains` (restaurada; formato verificado en
  `identity-and-permissions/uc/UC-API-001.md` e `index.md`).
- Arquitectura consolidada: `CLAUDE.md` raíz + plan de programa aprobado + Plan change log (abajo).

## Estimación global

- **Tareas totales**: 19 (ver lista al final).
- **Esfuerzo estimado** (esqueleto+specs): ~4–6 sesiones.
- **Recursos**: 1 dev con acceso al repo y a la KB.

## Criterios de calidad y verificación

- Doc-only: **sin TDD ni gate de mutation** (escape hatch). Verificación = estructura + guión por
  fichero + specs coherentes + scaffolding que valida.
- Hexagonal: dominio no importa infra; puertos/adaptadores; Pydantic v2; async.
- Guiones de riesgo con **avisos explícitos**: el de RLS (`SET app.tenant_id` en pool asyncpg es un
  footgun → exige tests de integración al implementar) y el de HITL/checkpointer (resume tras reinicio).
- Gate `fact-checker` al cierre de cada tarea (no-negociable).

## Tasks

- [x] `backend-skeleton-foundation-01` (P1) — Scaffold + tooling (requirements pip-tools, ruff/mypy/pytest, Dockerfile, docker-compose postgres+pgvector, Makefile, .env.example, README)  · depends_on: —
- [x] `backend-skeleton-foundation-02` (P1) — Spec RBAC (capacidades + ámbito, **roles custom por tenant** + role builder, aislamiento tenant, visibilidad msg `public|internal`)  · depends_on: —
- [x] `backend-skeleton-foundation-03` (P1) — Spec data-model (entidades, ERD; `Capability`/`Role`/`RoleCapability`; **RLS** en tablas de negocio + nota `SET app.tenant_id`; KB global sin RLS; dimensión vector desde config + coste re-embed; ticket domain/prioridad por clasificador)  · depends_on: backend-skeleton-foundation-02
- [x] `backend-skeleton-foundation-04` (P1) — Spec RAG + ingestión (fuente `domains/uc`, frontmatter `title/domain/package/uc` + Trazabilidad, glosario, **chunk H2 tolerante**, categorización, pgvector, confianza híbrida, citas, peso `estado` explícito, upsert idempotente por `uc-id`)  · depends_on: —
- [x] `backend-skeleton-foundation-05` (P1) — Spec agente LangGraph + HITL + fases + LangSmith (**detalle alto**: **grafo plano con edges condicionales tipados, NO supervisor por prompt**; `classify→retrieve→grade→generate→HITL`; **clasificación `with_structured_output`** `{categoría, dominio 1-de-17, prioridad, resoluble}` que **filtra el retrieval**; estado `add_messages`+dominio; `trim_messages`; tools tipadas con toolset acotado por tenant; checkpointer Postgres; **modelo interrupt→API→resume** con reinicio/concurrencia; seam `astream`)  · depends_on: backend-skeleton-foundation-04
- [x] `backend-skeleton-foundation-06` (P1) — Spec **contrato de API** (única fuente de verdad, OpenAPI-first; core + flujo-IA; incl. endpoints roles/capacidades por tenant; **envelope de error** problem+json)  · depends_on: backend-skeleton-foundation-02, backend-skeleton-foundation-03, backend-skeleton-foundation-04, backend-skeleton-foundation-05
- [x] `backend-skeleton-foundation-07` (P2) — Skeleton core (config/security/logging+**request-id**/deps) + app factory `main.py` + **healthcheck** (DB + pgvector)  · depends_on: backend-skeleton-foundation-01
- [x] `backend-skeleton-foundation-08` (P2) — Skeleton capa DB (modelos SQLAlchemy, session, repos ports+stubs) + Alembic + **políticas RLS** + `SET app.tenant_id` por conexión  · **guión: aviso footgun pool async + exige tests de integración**  · depends_on: backend-skeleton-foundation-03, backend-skeleton-foundation-07
- [x] `backend-skeleton-foundation-09` (P2) — Skeleton puerto LLM (1 adaptador OpenAI) + embeddings + tracing LangSmith  · depends_on: backend-skeleton-foundation-07
- [x] `backend-skeleton-foundation-10` (P2) — Skeleton servicios de dominio + ports (ticket, approval, rbac, notification, classification)  · **dep data-model + puertos, NO routers**  · depends_on: backend-skeleton-foundation-03, backend-skeleton-foundation-07
- [x] `backend-skeleton-foundation-11` (P2) — Skeleton routers API **core** + schemas (auth, tickets, messages, admin tenants/usuarios/roles, kb)  · depends_on: backend-skeleton-foundation-06, backend-skeleton-foundation-07, backend-skeleton-foundation-10
- [x] `backend-skeleton-foundation-12` (P2) — Skeleton routers API **flujo-IA** + schemas (approvals, disparar draft, fuentes/confianza, escalado, notificaciones, dashboard)  · depends_on: backend-skeleton-foundation-06, backend-skeleton-foundation-07, backend-skeleton-foundation-10
- [x] `backend-skeleton-foundation-13` (P3) — Skeleton pipeline de ingestión (loader/parser Trazabilidad/**chunker H2 tolerante**/embedder/cli idempotente)  · depends_on: backend-skeleton-foundation-04, backend-skeleton-foundation-08, backend-skeleton-foundation-09
- [x] `backend-skeleton-foundation-14` (P3) — Skeleton RAG retriever (pgvector + filtros + rerank + confianza híbrida + citas + peso `estado`)  · depends_on: backend-skeleton-foundation-04, backend-skeleton-foundation-08, backend-skeleton-foundation-09
- [x] `backend-skeleton-foundation-15` (P3) — Skeleton grafo **definición** (state `add_messages`+dominio, nodos retrieve/grade/generate/classify, `trim_messages`, inyección de contexto RAG)  · depends_on: backend-skeleton-foundation-05, backend-skeleton-foundation-09, backend-skeleton-foundation-14
- [x] `backend-skeleton-foundation-16` (P3) — Skeleton grafo **checkpointer + HITL** (PostgresSaver, `interrupt`→endpoint aprobación→`resume`, integración con approval service)  · **el núcleo de riesgo**  · depends_on: backend-skeleton-foundation-15, backend-skeleton-foundation-08
- [x] `backend-skeleton-foundation-17` (P3) — Skeleton **seeds/fixtures** idempotentes (tenant demo `syntax` + cliente demo, usuario por rol, capacidades/roles, chunks KB de muestra)  · depends_on: backend-skeleton-foundation-08, backend-skeleton-foundation-09
- [x] `backend-skeleton-foundation-18` (P3) — Skeleton **scheduler de SLA** (vencimiento → notificar/escalar; idempotente; worker acotado solo a SLA)  · *(B.2 promovido)*  · depends_on: backend-skeleton-foundation-03, backend-skeleton-foundation-10
- [x] `backend-skeleton-foundation-19` (P3) — **Guión maestro** `IMPLEMENTATION-GUIDE.md` (orden de build, cómo levantar, cómo encaja cada pieza, gate "OpenAPI generado ⊇ contrato")  · depends_on: todas

## Registro de cambios del plan

- 2026-08-11: creado (materializado desde el plan de programa aprobado).
- 2026-08-11: **refinado con `grilling`** (9 ramas + puntos por defecto). Decisiones: 1) monorepo pnpm + git `dev`; 2) pip-tools+venv, ruff/mypy strict, FastAPI async, SQLAlchemy async/asyncpg, checkpointer Postgres; 3) RBAC capacidades + **roles custom por tenant** + role builder *(scope+)*; 4) aislamiento **app-level + RLS día 1** (KB compartida sin RLS) *(scope+)*; 5) JWT access(memoria)+refresh(cookie httpOnly); 6) embeddings OpenAI `3-small` `vector(1536)`, chunk H2, frontmatter-first + glosario; 7) confianza híbrida similitud+`grade`; 8) chat OpenAI default (puerto conmutable), LangSmith; 9) **Fase 2 diferida** (visibilidad `public|internal`). Confirmados: `auto_approve=false` por tenant; notif in-app+polling. Puntos por defecto: storage port adjuntos; auditoría de mutaciones; 1 AgentRun/ticket; `priority`+`sla_due`; ingestión CLI idempotente; búsqueda semántica (BM25 diferido); `estado` señal de retrieval.
- 2026-08-11: fuente KB **restaurada** por el owner (286 .md = 268 UC + 18 index; frontmatter rico `title/domain/package/uc`; glosario en `index.md`).
- 2026-08-11: **`design-review`** (subagente adversario). Decisiones del owner: **#1 mantener** RBAC roles-custom + builder; **#2 mantener** RLS + app-level activos (con **guión de footgun** `SET app.tenant_id` en pool async + tests de integración obligatorios); **#3 aplicar todo el resto**, aplicado en esta reescritura:
  - Factual: `url`→`title/domain/package/uc`; "H2 fijos"→**H2 tolerante**; conteo 268 UC + 18 index; peso de `estado` explícito (draft 81%).
  - **Quitado "workers"** (contradecía Fuera de alcance).
  - **Partida** la tarea "routers de toda la API" en **core (11)** + **flujo-IA (12)**.
  - **Partido** el grafo en **definición (15)** + **checkpointer/HITL (16)**; subido el detalle de spec del HITL (tarea 05) por ser el núcleo de riesgo.
  - **Reorden**: `contrato (06)` depende de rbac+data-model+**rag(04)**+**agent(05)** (única fuente de verdad, en vez de derivar antes que sus conceptos); **servicios de dominio (10)** dependen de data-model+puertos, **no** de routers (respeta hexagonal).
  - **Añadidas**: seeds (17), healthcheck (07), envelope de error en el contrato (06), logging+request-id (07), gate de conformidad OpenAPI en la guía (18); dimensión vector configurable (03/04); puerto LLM reencuadrado como "1 adaptador" (09); `developer_note` alineado (fuera del contrato y del frontend en Fase 1).
- 2026-08-11: **2ª demo** (`multiuser_chat_system`) analizada → patrones adoptados en agent-graph (05/15): grafo multi-nodo, estado `add_messages`+dominio, `trim_messages`, checkpointer por thread→`PostgresSaver`, **clasificador de ticket** (Pydantic → dominio/prioridad), auto-asunto por LLM (opcional). Ignorados sus anti-patrones (Streamlit, filesystem, singleton global, SqliteSaver, Chroma). Streaming SSE del draft = seam diferido.
- 2026-08-11: **3ª demo** (`soc_multiagent`) analizada → directrices para agent-graph (05): **grafo plano + edges condicionales tipados** (no supervisor por prompt); **clasificación con structured output** `{categoría, dominio 1-de-17, prioridad, resoluble}` que **filtra el retrieval RAG** (no parseo de strings); tools tipadas con toolset acotado por tenant; settings inyectables (Pydantic `BaseSettings`, sin efectos en import) → guión de core (07). Descartados sus anti-patrones (routing por prompt, clasificación en prosa, sin checkpointer/HITL/tracing/auth, blocking en async).
- 2026-08-11: **`scenario-coverage`** (subagente QA fresco sobre las 18 tareas + plan). **(A)** incorporados
  todos los huecos dentro de alcance como sección `## Refuerzos (scenario-coverage)` en las tareas
  02/03/04/05/06/07/09/10/11/12/13/15/16 (respond→`Message(public)`+transición; prompt-injection; `AgentRun.failed`
  + retry LLM; `RefreshSession`+rotación/logout; orden determinista; borrado/retención/cascada; frontmatter
  malformado/`uc_id` dup/docs huérfanos; no-clasificable→fallback; idioma de respuesta; deny-all sin rol;
  caps server-side; idempotencia doble decisión; run-por-reapertura; obs. de errores). **(B)** decididos por
  el owner: **promovidos** B.1 (throttling login + límite `ai-draft`), B.2 (scheduler SLA → **tarea 18 nueva**),
  B.3 (reset/invitación de contraseña, email stub); **diferidos** B.4–B.8. Guión maestro renumerado a **19**.
  Drift factual corregido: `estado` ≈ 218 draft / 51 active.
- 2026-08-11: backend **listo para handoff** (grilling + design-review + scenario-coverage superados). Siguiente
  en el pipeline: el plan **frontend** hace su propio `grilling` (checkpoint) antes de descomponerse.
- 2026-08-13: **tarea 01 (scaffold + tooling) cerrada**. Creada la raíz `backend/` (tooling pip-tools,
  pyproject ruff/mypy-strict/pytest, Dockerfile non-root, docker-compose db pgvector+healthcheck, Makefile,
  .env.example, README) + árbol `app/` (13 `__init__.py` con guión-puntero por subpaquete). Verificado en
  sesión: `docker compose config` exit 0, `pyproject` parsea, `compileall` OK. Gate `fact-checker` (sonnet):
  10/10 VERIFICADO. Doc-only (sin TDD/mutation).
- 2026-08-13: **tarea 03 (spec data-model) cerrada**. Creada `.claude/specs/backend/data-model.md`: 18
  tablas en 3 grupos (identidad/RBAC, negocio con `tenant_id`+RLS, KB global sin RLS), 13 enums de contrato
  (reusan `public|internal`, `tenant|global` de 02), ERD mermaid completo, política borrado/cascada/
  retención (SET NULL requester/assignee, CASCADE agregado/KB, RESTRICT tenant, GDPR = hueco explícito),
  `vector(N)` desde config (default 1536) + coste re-embed, índices (incl. pgvector). Refuerzos cerrados:
  `agent_run.failed`, `refresh_session` (rotación/reuse-detection/logout), `auth_token` (reset/invitación),
  `thread_id=ticket_{id}_run_{n}`+`run_seq`, precedencia `package` frontmatter-gana. KB verificada en sesión
  (17 dominios, 268 UC + 18 index, frontmatter sin `url`, Trazabilidad en 268 → `source_url` derivado).
  Gate `fact-checker` (sonnet): 9/9 VERIFICADO. Doc-only.
- 2026-08-13: **tarea 04 (spec RAG + ingestión) cerrada**. Creada `.claude/specs/backend/rag-ingestion.md`:
  fuente (268 UC/17 dominios/18 index + fallback `llms-full.txt`), parsing (frontmatter
  `title/domain/package/uc` sin `url`; Trazabilidad `Estado`/`Traza`; `Relacionado:`), **chunking H2
  tolerante** (H2 ausentes/renombrados/sueltos verificados; no partir tablas; glosario del index),
  categorización 5 facetas con **peso `estado` explícito**, embeddings (`vector(N)` config default 1536,
  upsert idempotente por `uc_id`), contrato de retrieval/confianza (pgvector coseno + filtros + híbrida +
  citas) para 05. Refuerzos: `uc_id` dup→fail, doc retirado→reconciliación/tombstone, precedencia
  `package` frontmatter-gana. **Correcciones factuales**: conteo `estado` **51→50 active** (real
  218/50); método de conteo H2 aclarado (agrupando variantes /268: Comportamiento 268, Fidelidad 268,
  Reglas e invariantes 268, Detalles observados en QA 266, Conceptos 257; exactas 262/265). Gate
  `fact-checker` (sonnet): 9/10 VERIFICADO + 1 INCORRECTO (conteos H2) corregido y re-cuadrado. Doc-only.
- 2026-08-13: **tarea 05 (spec agente LangGraph + HITL) cerrada** — núcleo de riesgo, detalle alto. Creada
  `.claude/specs/backend/agent-graph.md`: grafo **plano + edges condicionales tipados** (no supervisor por
  prompt); `classify` `with_structured_output` `{categoria, dominio 1-de-17, prioridad, resoluble}` que
  filtra el retrieval; estado `add_messages`+dominio mapeado 1:1 a 03; `trim_messages`; confianza híbrida
  (similitud de 04 + grade → umbral → auto/escalado/human_note); **HITL asíncrono a fondo**
  (`interrupt()`→checkpoint PostgresSaver `thread_id=ticket_{id}_run_{n}`→endpoint `approval.decide`→
  `Command(resume=)`; reinicio a mitad de run reanuda desde checkpoint; doble decisión→409 idempotente;
  mapeo interrupt↔ApprovalTask); tools tipadas acotadas por tenant; settings inyectables; LangSmith +
  seam `astream`. Refuerzos: prompt-injection, no-clasificable→fallback, idioma, `agent_run.failed`,
  re-draft tras reopen. **Nota de conformidad de API**: deps LLM sin instalar/compilar; demos usan
  variantes antiguas (`interrupt_before`/`PydanticOutputParser`) vs modernas objetivo → surface exacto a
  pinar/verificar en 15/16. Gate `fact-checker` (sonnet): 8/8 VERIFICADO (incl. C8 honestidad). Doc-only.
- 2026-08-13: **tarea 06 (spec contrato de API) cerrada** — dependencia dura cross-plan. Materializada
  (decisión del owner) como **`.claude/specs/general/api-contract.yaml`** (OpenAPI 3.1, fuente única:
  32 paths, 38 schemas, todos los `$ref` resuelven) + **`api-contract.md`** (companion fino, puntero +
  convenciones). Cubre core (auth incl. password reset/invitación, tickets CRUD+transition+assign,
  messages public/internal, attachments) + flujo-IA (ai-draft, `/approvals` approve/edit/reject con
  **409** en doble decisión, `/agent-runs/{id}`) + KB (search/docs con filtros domain/package/estado) +
  admin (tenants/users+invite/roles+capabilities role builder/settings auto_approve) + analytics +
  notifications. Envelope de error **problem+json** (`Problem`), paginación, orden determinista por
  listado, i18n por `Accept-Language`. Enums/capacidades alineados literal con 02/03/04/05. Gate
  `fact-checker` (sonnet): 9/9 VERIFICADO. **Aviso**: sin validación formal contra meta-schema OpenAPI
  (`openapi-spec-validator` no instalado) → solo parseo+`$ref`; el gate de conformidad real lo dan 11/12
  (OpenAPI generado ⊇ contrato, tarea 19) y frontend-02. Doc-only.
- 2026-08-13: **tarea 07 (skeleton core + app factory + healthcheck) cerrada** — primeros ficheros de
  código (esqueleto guión-only, patrón del 01). Creados `backend/app/core/{config,security,logging,
  deps}.py` + `backend/app/main.py`: `config` (Settings BaseSettings + `get_settings()` cacheada, sin
  efectos en import), `security` (Argon2id, JWT access **sin** capacidades, refresh contra
  `refresh_session` con rotación+reuse-detection+logout server-side, tokens reset/invitación), `logging`
  (estructurado + request-id por contextvar + hook errores), `deps` (sesión DB con `SET app.tenant_id`,
  `get_tenant_context`, `get_current_subject` con **capacidades server-side por request** A1.7,
  `require_capability`→403), `main` (`create_app()`, middleware request-id/CORS/throttling B.1, routers
  11/12 placeholder, `/health` split liveness/readiness DB+pgvector, `/metrics`). `compileall` OK. Gate
  `fact-checker` (sonnet): 8/8 VERIFICADO. Doc-only.
- 2026-08-13: **tarea 08 (skeleton capa DB + Alembic + RLS) cerrada**. Creados 8 ficheros guión en
  `backend/`: `app/infra/db/{base,session}.py`, `app/infra/db/models/__init__.py` (18 entidades de 03,
  marca RLS, `vector(N)` desde config), `app/infra/db/repositories/__init__.py` (stubs filtran por
  `tenant_id`; KB sin filtro), `app/domain/ports/{__init__,repositories}.py` (interfaces), `alembic/env.py`
  + `alembic/versions/0001_initial_schema.py` (guión migración: `CREATE EXTENSION vector`, tablas+cascadas,
  índices incl. pgvector, **RLS `ENABLE`+`CREATE POLICY tenant_isolation`** en negocio; KB/identidad sin
  RLS). `session.py` lleva el **aviso de footgun** (`SET app.tenant_id` en pool asyncpg) + exige tests de
  integración. Drift resuelto: `models/` (spec de la tarea) vs `models.py` (`db/__init__.py`). `compileall`
  OK. Gate `fact-checker` (sonnet): 7/8 VERIFICADO + F2 INCORRECTO (afirmación literal de grep sobre línea
  pseudo-código dentro del docstring) corregido y re-verificado. Doc-only.
- 2026-08-13: **tarea 09 (skeleton puerto LLM + embeddings + LangSmith) cerrada**. Creados 4 ficheros
  guión: `app/domain/ports/llm.py` (ChatModel generate/grade/classify + EmbeddingModel), `app/infra/llm/
  openai_adapter.py` (adaptador OpenAI único, lazy/sin creds en import, conmutable `LLM_PROVIDER`,
  `settings.CHAT_MODEL` no hardcodeado, timeout/retry/backoff+429→`AgentRun.failed`), `app/infra/llm/
  structured.py` (helper `with_structured_output` para el clasificador 05 + nota de conformidad de API),
  `app/infra/langsmith/tracing.py` (activación por env + `langsmith_trace_url`→AgentRun + degradación
  limpia). Añadido `LLM_PROVIDER=openai` a `.env.example`. `compileall` OK. Gate `fact-checker` (sonnet):
  8/8 VERIFICADO. Doc-only.
- 2026-08-13: **tarea 10 (skeleton servicios de dominio + ports) cerrada** — centro hexagonal. Creados 11
  ficheros guión en `backend/app/domain/`: servicios `ticket_service` (máquina de 6 estados+SLA+auditoría),
  `approval_service` (HITL, `auto_approve` default false, aprobar/editar→`Message(public)`+transición A1.1,
  idempotencia→409), `rbac_service` (`authorize` capacidad+ámbito, deny-all fail-closed, roles custom, caps
  server-side), `notification_service` (in-app+polling), `classification` (structured output 1-de-17 +
  fallback), `auth_service` (login/refresh rotación+reuse-detection+logout, reset/invitación B.3 email
  stub) + `__init__`; puertos `vector`/`storage`/`email`/`clock` (repos/llm ya de 08/09). Hexagonal
  estricto (0 imports de infra/FastAPI/SQLAlchemy/openai/langchain, verificado). `compileall` OK. Gate
  `fact-checker` (sonnet): 8/8 VERIFICADO. Doc-only.
- 2026-08-13: **tarea 11 (skeleton routers API core) cerrada**. 9 ficheros guión en `app/api/v1/`:
  routers `auth`/`tickets`/`messages`/`admin_tenants`/`admin_users`/`admin_roles`/`kb` + `routers/__init__`
  + `schemas/__init__` (DTOs 1:1 con 06, `Problem`+`Page`). Endpoints == contrato 06; delegan en servicios
  (10) —kb en retriever 14—; deps auth+tenant+`require_capability` (salvo recursos globales). `compileall`
  OK. Gate `fact-checker` (sonnet): 6/7 VERIFICADO + I5 (regla "siempre app.domain" demasiado absoluta)
  corregido. Doc-only.
- 2026-08-13: **tarea 12 (skeleton routers API flujo-IA) cerrada**. 4 ficheros guión en `app/api/v1/
  routers/`: `agent` (ai-draft rate-limit B.1/429/409 + agent-runs confidence/sources/trace/failed),
  `approvals` (cola `sla_due,confidence`; approve/edit/reject→resume; 409 doble decisión; A1.1),
  `notifications`, `analytics`. Delegan en servicios (10)+HITL(16); == contrato 06. `compileall` OK. Gate
  `fact-checker` (sonnet): 6/6 VERIFICADO. Doc-only.
- 2026-08-13: **tarea 13 (skeleton pipeline de ingestión) cerrada**. 7 ficheros guión en `app/ingestion/`:
  `loader`/`parser`/`chunker`(H2 tolerante)/`embedder`/`pipeline`(upsert idempotente por uc_id +
  reconciliación)/`cli`/`__main__` (entry-point `python -m app.ingestion` de `make ingest`). Fiel a spec 04.
  `compileall` OK. Gate `fact-checker` (sonnet): 7/7 VERIFICADO. Doc-only.
- 2026-08-13: **tarea 14 (skeleton RAG retriever) cerrada**. 4 ficheros guión en `app/rag/`:
  `retriever` (coseno pgvector top-k + filtros domain/package/estado), `reranker` (peso `estado` explícito,
  desempate no veto), `confidence` (híbrida similitud+grade, umbral config), `citations` (uc_id/title/
  section_type). Puerto vector ya de la 10. `compileall` OK. Gate `fact-checker` (sonnet): 7/7 VERIFICADO.
  Doc-only.
- 2026-08-13: **tarea 15 (skeleton grafo — definición) cerrada**. 10 ficheros guión en `app/agents/`:
  `state` (HelpdeskState add_messages + campos 05), `graph` (build_graph, plano + edges tipados, sin
  checkpointer), `tools`, y `nodes/` (classify structured-output+fallback, retrieve, grade, generate,
  decide, trim). Anti prompt-injection + nota de conformidad de API en todas las menciones LangGraph/
  LangChain. `compileall` OK. Gate `fact-checker` (sonnet): 8/8 VERIFICADO. Doc-only.
- 2026-08-13: **tarea 16 (skeleton grafo — checkpointer + HITL) cerrada** — núcleo de riesgo. 3 ficheros
  guión en `app/agents/`: `checkpointer` (PostgresSaver, thread_id=ticket_{id}_run_{n}, comparte pool 08),
  `hitl` (interrupt→checkpoint→endpoint→resume; reinicio a mitad de run; doble decisión→409 idempotente;
  mapeo interrupt↔ApprovalTask; auto_approve), `runner` (run/resume, AgentRun.failed, Message(public)+
  transición A1.1). `compileall` OK. Gate `fact-checker` (sonnet): 8/8 VERIFICADO. Doc-only.
- 2026-08-13: **tarea 17 (skeleton seeds/fixtures) cerrada**. 1 fichero guión `app/infra/db/seed.py`
  (entry-point `make seed`): 14 capacidades + 6 roles semilla, tenant syntax + cliente demo, 1 usuario por
  rol, tickets/mensajes de ejemplo, KB de muestra. Idempotente (upsert), respeta RLS. Drift resuelto:
  `app/infra/db/seed.py` (Makefile) vs `app/seeds/` (texto tarea). `compileall` OK. Gate `fact-checker`
  (sonnet): 7/7 VERIFICADO. Doc-only.
- 2026-08-13: **tarea 18 (skeleton scheduler de SLA) cerrada** (B.2). 2 ficheros guión en `app/workers/`:
  `__init__` (solo SLA, no colas generales) + `sla_scheduler` (job periódico config; tickets no resueltos
  con sla_due vencido/inminente por tenant respetando RLS; Notification+escalado+audit; idempotente por
  `sla_breached_at`; delega en 10 + puerto clock). `compileall` OK. Gate `fact-checker` (sonnet): 6/6
  VERIFICADO. Doc-only.
- 2026-08-13: **tarea 19 (guión maestro IMPLEMENTATION-GUIDE.md) cerrada**. Creado
  `backend/IMPLEMENTATION-GUIDE.md`: mapa de specs, orden de build por bloques, cómo levantar (make
  install/migrate/ingest/seed/run), mapa hexagonal + ciclo HITL end-to-end, gate "OpenAPI generado ⊇
  contrato", 6 avisos de riesgo, checklist "esqueleto seguible". Rutas verificadas. Gate `fact-checker`
  (sonnet): 8/8 VERIFICADO. Doc-only.
- 2026-08-13: **PLAN CERRADO (19/19)** → `status: completed`, movido a `.claude/plans/completed/backend/`.
  **Retro**: (a) *estimación vs real* — estimado ~4–6 sesiones / ~48 h de tareas; real de ejecución de los
  esqueletos ≈ 11 h agregadas (doc-only acelera mucho: guiones, no lógica). (b) *sorpresas* — varios
  **drifts de scaffold** entre el `__init__.py` de 01 y las specs de tarea (`models.py`↔`models/`,
  `app/seeds/`↔`app/infra/db/seed.py`, `cli.py`↔`__main__.py`); resueltos usando el **Makefile como
  autoritativo** para los entry-points. (c) *gates* — `fact-checker` cazó 3 imprecisiones reales en
  afirmaciones (conteos H2 en 04, regla "siempre app.domain" en 11, grep de pseudo-código en 08),
  corregidas; el resto VERIFICADO a la primera. (d) *pendiente al implementar* — compilar el lockfile
  (`requirements.txt` es stub) y pinar el surface de LangGraph/LangChain; tests de integración RLS + HITL;
  añadir `openapi-spec-validator` para el gate formal del contrato. Doc-only: sin TDD ni gate de mutation
  (escape hatch del plan).
