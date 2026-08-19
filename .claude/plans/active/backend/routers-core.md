---
id: backend-routers-core
package: backend
status: active
branch: plan/backend/routers-core
created: 2026-08-19
updated: 2026-08-19
---

# Backend — Routers core (auth multi-tenant · tickets · messages+attachments · admin · kb)

## Contexto

El plan `domain-services` (mergeado a `main`, PR #4) dejó la lógica de negocio pura: 6 servicios de
dominio + los puertos (`Protocol`) que necesitan. Ningún adaptador real los implementa todavía, y los 11
routers de `app/api/v1/routers/*` siguen siendo esqueleto doc-only (solo docstring "GUIÓN"). Este es el
**plan 11 del roadmap** (`IMPLEMENTATION-GUIDE.md §2`, bloque 4): conectar HTTP ↔ dominio para los routers
marcados **"→ tarea 11" en su propio guión**: `auth`, `tickets`, `messages`, `admin_tenants`,
`admin_users`, `admin_roles`, `kb`. Los 4 restantes (`agent`, `approvals`, `notifications`, `analytics`)
están marcados "→ tarea 12" — **fuera de este plan**.

**Cambio de nivel de test respecto al plan anterior**: `domain-services` fue 100% unit con fakes (sin
Docker). Este plan **sí necesita Postgres** (`docker compose up -d db`): los adaptadores de repositorio
son la primera vez que se ejercita RLS/tenant-scope de verdad, y los routers se prueban con el cliente
HTTP de FastAPI contra una DB real (mismo patrón de fixtures que `database-foundation`:
`migrated_database`/`app_engine`/`superuser_engine` en `tests/conftest.py`).

**Hallazgo central de `grilling`, con impacto de diseño**: el contrato (`LoginRequest{email,password}`)
no lleva identificador de tenant, y el owner confirmó que un usuario **puede pertenecer a varios
tenants** (con pantalla de selección en el frontend si hay más de uno). El modelo actual (`User.
tenant_id` `NOT NULL`, único `(tenant_id, email)`) asume 1 usuario = 1 tenant y **no lo soporta**. Esto
**amplía el plan** con un rediseño de identidad (ver Objetivo 0) que toca la migración de
`database-foundation` (ya cerrada) — una migración nueva, no una reversión de la anterior.

**Decisiones tomadas con el owner durante `grilling`** (ver Registro de cambios para el detalle completo):
1. `kb` **entra** con un adaptador `VectorStore` **stub** (retriever real = tarea 14).
2. `attachments` **entra**: puerto `Storage` nuevo + adaptador a **filesystem local**.
3. Las extensiones a puertos/servicios de `domain-services` (ya cerrado) que los routers necesitan de
   verdad se hacen **dentro** de este plan.
4. **Identidad multi-tenant** (rediseño, ver Objetivo 0): `User` pasa a ser identidad **global** (sin
   `tenant_id`/`status` propios; email único global); nueva tabla `user_tenant(user_id, tenant_id,
   status)` con el status **por membresía**; `refresh_session` gana `tenant_id` (una sesión es de un
   tenant concreto). Login en dos pasos con un `identity_token` corto cuando hay 2+ tenants.
5. `get_tenant_context` decide `tenant_scope` vs `global_scope` **por el ámbito concedido de la
   capacidad requerida** (no por un flag fijo del `Subject`): si `(cap, "global") in subject.
   capabilities` → `global_scope()`; si no, `tenant_scope(subject.tenant_id)`.
6. `Deny(out_of_scope)` de `rbac_service.authorize()` se documenta como **defensa en profundidad hoy sin
   caso real que la dispare** (con RLS+filtro app-level activos, un subject `tenant` nunca obtiene un
   recurso de otro tenant al que aplicarle `authorize()`; solo `global_scope` + `authorize()` podría
   ejercitarla, y ahí `scope="global"` no entra en esa rama). Se llama a `authorize()` siempre, por
   disciplina, aunque hoy sea redundante — mismo criterio que el "riesgo conocido documentado" de
   `approval_service` en el plan anterior.
7. `GET`/`PATCH /admin/settings` (`TenantSettings{auto_approve}`) **entra** en `admin_tenants.py` +
   migración nueva para `Tenant.auto_approve`, aunque su único consumidor futuro (nodo `decide` del
   grafo) es la tarea 15 — el admin ya puede configurarlo antes de que exista quien lo lea.

**Decisiones tomadas tras `design-review`** (subagente adversarial; ver Registro de cambios para el
detalle de los 6 hallazgos):
8. Objetivo 0 (identidad global, una sola contraseña por persona) se **mantiene tal cual** pese a que el
   revisor mostró que existe una alternativa barata (cuentas separadas por tenant, sin migración) — el
   owner confirmó explícitamente que quiere **una sola contraseña compartida** entre membresías, no solo
   "pertenecer a varios tenants" (que la alternativa barata también cumpliría).
9. La tarea 02 se **amplía**: además de reescribir `auth_service`, cierra el contrato/specs que Objetivo 0
   rompe — `User`/`UserInvite`/`UserUpdate`/`/admin/users` en `api-contract.yaml`, y actualiza
   `data-model.md`/`rbac.md`/CU-BE-01 para que reflejen el modelo nuevo (no quedan huecos de specs
   desincronizadas sin dueño).
10. `/admin/settings` se protege con una capacidad **nueva** `tenant.settings.manage` (ámbito `tenant`,
    catálogo `rbac.md`) — el propio tenant puede gestionar su `auto_approve` (coherente con ADR-0009),
    no solo Soporte global vía `tenant.manage`.
11. FR-038 (notificar tras `ticket.assign`/`ticket.reply`) **NO** se cablea en este plan — hueco nombrado
    explícito en Fuera de alcance para el plan 12 (que ya toca `notifications.py`).
12. `app/core/security.py` se añade explícitamente a "Dentro del alcance" (tarea 02): el `identity_token`
    corto necesita un claim `purpose` y permitir omitir `tenant_id`, tocando `create_access_token`/
    `decode_access_token`.

**Decisiones tomadas tras `scenario-coverage`** (QA fresco; ver Registro de cambios para el detalle
completo de los 8 hallazgos críticos y las decisiones tomadas):
13. `RoleRepository.effective_capabilities` **cambia de firma** a `effective_capabilities(user_id,
    tenant_id)` — sin acotar por tenant, un usuario con roles distintos en dos tenants (ya soportado por
    `user_role.tenant_id`) filtraría capacidades de un tenant a la sesión de otro (fix de seguridad, no
    una decisión discrecional).
14. `login`/`select_tenant`/`switch_tenant`/`get_tenant_context` comprueban `Tenant.status != disabled`
    — un tenant deshabilitado no debe permitir login ni operar dentro de él.
15. El email se **normaliza a minúsculas** en escritura y lectura (`User.email`) — más crítico ahora que
    es clave de unicidad global (antes era por tenant).
16. `GET /messages/{id}/attachments/{attachment_id}` (nuevo, tarea 08) sirve el contenido de un adjunto —
    sin él, `attachments` quedaba incompleto en HTTP (solo se podía subir, nunca recuperar).
17. El `identity_token` es **reutilizable dentro de su TTL corto** (no de un solo uso) — más simple, el
    TTL ya acota el riesgo.
18. `GET`/`PATCH /admin/settings` gana un **query param `tenant_id` opcional**: obligatorio si el subject
    accede en ámbito `global` (Soporte, sin tenant propio); ignorado (usa el suyo) en ámbito `tenant`.
19. Se **cablea auditoría** (`AuditLogRepository.add`) en `admin_tenants`/`admin_users`/`admin_roles`
    (tarea 06) — mismo patrón que `ticket_service`, puerto ya existente.
20. `PATCH /admin/users/{id}`: `{id}` es el `User.id` **global**; el router cruza con
    `subject.tenant_id` para localizar la membership — sin membership en ese tenant → 404 (mismo patrón
    que el aislamiento cross-tenant de tickets).
21. `TicketService.transition`/`update_fields` **no ganan CAS** — el riesgo de lost-update en dos
    transiciones concurrentes sobre el mismo ticket se **documenta como riesgo conocido** (mismo criterio
    que el riesgo post-CAS de `approval_service` en el plan anterior), sin reabrir el diseño de
    `ticket_service` (plan `domain-services`, ya cerrado) por una ventana de carrera estrecha.
22. Se añade **`POST /auth/switch-tenant`** (nuevo, tarea 05): con una sesión ya autenticada (access
    token), cambia a otra membership del mismo usuario sin repetir credenciales — a diferencia de
    `select_tenant` (que parte de un `identity_token` post-login), este parte de un access token válido.

## Objetivos

0. **Rediseño de identidad multi-tenant** (bloquea todo lo demás de `auth`/RBAC).
   - **Migración nueva** (Alembic, sobre el esquema ya migrado de `database-foundation`): `user` pierde
     `tenant_id`/`status` (email único **global**); nueva tabla `user_tenant(user_id, tenant_id, status,
     created_at)` (PK compuesta o `id` propio + unique `(user_id, tenant_id)`); `refresh_session` gana
     `tenant_id` (FK); `tenant` gana `auto_approve: bool default false`.
   - **Entidades de dominio**: `User` pierde `tenant_id`/`status`; nueva entidad `UserTenantMembership`
     (`user_id`, `tenant_id`, `status: UserStatus`); `RefreshSession` gana `tenant_id`.
   - **`auth_service` reescrito**: `login(email, password)` (sin `tenant_id`) → email normalizado a
     minúsculas para la búsqueda; si 1 sola membership `active` en un tenant **no `disabled`**, emite
     `TokenResponse` normal; si 2+, emite un `identity_token` corto (JWT `purpose=tenant_selection`, sin
     `tenant_id`, sin refresh-cookie, **reutilizable dentro de su TTL**) + la lista de tenants; 0 → error
     genérico igual que credenciales inválidas (no revela si el email existe sin membership). Nuevo
     método `select_tenant(identity_token, tenant_id) -> AuthResult` que valida la membership `active` +
     `Tenant.status != disabled` y emite el `TokenResponse` real. Nuevo `switch_tenant(access_token,
     tenant_id) -> AuthResult`: mismo chequeo, pero partiendo de un access token ya válido (sesión activa
     cambiando de tenant sin repetir credenciales). `invite()`/`accept_invitation()` pasan a operar sobre
     `UserTenantMembership.status`, no sobre `User.status` (que ya no existe). Nuevo `change_password(
     user_id, current, new)`.
   - *Criterio de éxito*: login con 1 tenant no pide selección (UX sin fricción); login con 2+ nunca
     emite refresh-cookie en el primer paso; `select_tenant`/`switch_tenant` con una membership no-
     `active` (`invited`/`disabled`), de un tenant al que no pertenece, o de un tenant `disabled` →
     rechazado con el mismo error genérico.
1. **Envelope de error único**: cada `DomainError` y cada `Deny` de `rbac_service` se traducen a
   `application/problem+json` (RFC 9457) — nunca una traza cruda al cliente.
   - *Criterio de éxito*: exception handler central cubre las 5 `DomainError` + fallback 500;
     `Deny(no_capability)`→403, `Deny(out_of_scope)`→404.
2. **`deps.get_current_subject`/`get_tenant_context`/`require_capability`**: JWT → `Subject` (capacidades
   resueltas server-side vía `effective_capabilities(user_id, tenant_id)` — **acotadas al tenant de la
   sesión activa**, no todas las del usuario) → `tenant_scope`/`global_scope` según el ámbito **de la
   capacidad requerida** (decisión 5 arriba). Si el subject tiene la misma capacidad en ámbito `tenant` Y
   `global`, gana `global`.
   - *Criterio de éxito*: token expirado/inválido/con `purpose` incorrecto → 401; capacidad ausente → 403;
     capacidad con ámbito `global` abre `global_scope()`; con ámbito `tenant`, `tenant_scope(subject.
     tenant_id)`; un usuario con roles distintos en dos tenants NUNCA ve las capacidades del otro tenant
     en su sesión activa.
3. **Adaptadores SQLAlchemy** para los puertos de identidad (`TenantRepository` [+ `list`],
   `UserRepository`, `UserTenantMembershipRepository` [nuevo], `RoleRepository` [+ `list`/`update`/
   `delete`, `effective_capabilities` acotado por tenant], `RefreshSessionRepository`,
   `AuthTokenRepository`) y de negocio (`TicketRepository`, `MessageRepository`).
   - *Criterio de éxito*: tests de integración (Postgres real) confirman que cada adaptador respeta el
     contrato del puerto, incl. el CAS de `rotate_if_active`/`decide_if_pending` bajo concurrencia real
     (no solo secuencial) y el aislamiento de `user_tenant` (un usuario solo ve sus propias membresías).
4. **7 routers** ⊇ contrato `api-contract.yaml` para esos paths (incl. `/admin/settings`).
   - *Criterio de éxito*: shape exacto del contrato; paginación real (`Page{items,page,page_size,
     total}`); sin lógica de negocio en el router.
5. **Puerto `Storage` (nuevo) + adaptador filesystem local** para adjuntos.
6. **Puerto `VectorStore` (nuevo, recortado) + adaptador stub** para `kb`.

## Alcance y fuera de alcance

### Dentro del alcance
- **Migración Alembic nueva**: `user` (drop `tenant_id`/`status`, unique `email` global), `user_tenant`
  (tabla nueva), `refresh_session.tenant_id` (columna nueva), `tenant.auto_approve` (columna nueva).
- `app/domain/entities/identity.py`: `User` sin `tenant_id`/`status`; `UserTenantMembership` (nueva);
  `RefreshSession` con `tenant_id`.
- `app/domain/ports/repositories.py`: `UserTenantMembershipRepository` (nuevo); `RoleRepository` (+
  `list`/`update`/`delete`); `TicketRepository` (paginación/filtros/orden); `TenantRepository` (+ `list`,
  `get_settings`/`update_settings` o campo `auto_approve` directo en `Tenant`).
- `app/domain/services/auth_service.py`: reescritura de `login`, `invite`, `accept_invitation`; nuevos
  `select_tenant`, `change_password`.
- `app/core/security.py`: claim `purpose` + `tenant_id` opcional en `create_access_token`/
  `decode_access_token` (soporte del `identity_token` corto de dos pasos).
- `app/domain/services/ticket_service.py`: método nuevo para el PATCH parcial (subject/priority/category).
- `app/api/v1/routers/{auth,tickets,messages,admin_tenants,admin_users,admin_roles,kb}.py` (código real).
- `app/api/v1/schemas/*.py`: schemas Pydantic espejo del contrato (`Page[T]`, `Problem`, por-recurso,
  más el `identity_token`/lista de tenants del login en 2 pasos — **ampliación del contrato compartido**,
  coordinar con el frontend antes de cerrar la tarea 03).
- `.claude/specs/general/api-contract.yaml` (tarea 02): rehacer `User`/`UserInvite`/`UserUpdate`/
  `/admin/users` para reflejar la membership (ya no columna `tenant_id`/`status` directa en `User`).
- `.claude/specs/backend/{data-model.md,rbac.md,casos-de-uso/CU-BE-01-*.md}` (tarea 02): actualizar al
  modelo de identidad nuevo; `rbac.md` gana la capacidad `tenant.settings.manage` (ámbito `tenant`).
- `app/infra/db/repositories/*.py`: adaptadores concretos de los puertos de identidad + negocio listados.
- `app/infra/storage/*.py` (nuevo): puerto `Storage` + adaptador filesystem local.
- `app/infra/vectorstore/*.py` (nuevo): puerto `VectorStore` recortado + stub.
- `app/core/deps.py`: `get_current_subject`, `get_tenant_context`, `require_capability`.
- Exception handlers centrales (`DomainError`→problem+json, `Deny`→403/404).
- Tests de **integración** (Postgres real, Docker) para migración/adaptadores/routers.

### Fuera de alcance
- Routers `agent`, `approvals`, `notifications`, `analytics` → **tarea 12** (flujo-IA).
- Retriever RAG real (`app/rag/retriever.py`) → **tarea 14**; `kb` en este plan usa el stub.
- Adaptador de storage en nube (S3/GCS) → diferido; esta fase es solo filesystem local.
- Rate-limiting real de `/auth/login`/`/auth/refresh`/`/auth/select-tenant` (429 documentado) → hueco
  nombrado sin dueño (footgun de infra — Redis/middleware — no inventado aquí).
- `POST /tickets/{id}/ai-draft`, cualquier disparo del grafo LangGraph → tarea 12/15/16.
- OpenAPI gate "generado ⊇ contrato" automatizado en CI → tarea 19.
- Seeds de datos (tenant sistema, roles semilla) → tarea 17.
- Migrar/backfill datos de usuarios existentes de un esquema 1-tenant a N-tenant → **no aplica**: no hay
  datos de producción (repo pre-lanzamiento), la migración nueva no necesita backfill.
- Roles/capacidades **por membership** más allá de lo que `user_role.tenant_id` (ya existente) permite
  hoy → si el owner quiere roles distintos por tenant para el mismo usuario, ya lo soporta el esquema
  actual de `user_role`; no se añade nada nuevo ahí.
- **Wiring de notificaciones (FR-038)**: los endpoints de esta plan disparan eventos que deberían notificar
  (`ticket.assign`, `ticket.reply`), pero `NotificationService.emit()` no se cablea desde `ticket_service`/
  el router de mensajes aquí (hallazgo de `design-review`) — hueco nombrado explícito para el **plan 12**,
  que ya toca `notifications.py`.
- **CAS en `TicketService.transition`/`update_fields`**: riesgo conocido documentado (lost-update en dos
  transiciones concurrentes sobre el mismo ticket), sin compensación en este plan — mismo criterio que el
  riesgo post-CAS de `approval_service` (hallazgo de `scenario-coverage`, decisión del owner).
- **Filtro `domain` en `GET /tickets`**: funcionalmente inerte hasta que exista un clasificador que asigne
  `Ticket.domain` (planes 12/15) — el filtro existe (lo exige el contrato) pero ningún ticket tendrá
  `domain` distinto de `None` hasta entonces; documentado, no es un bug de esta tarea.
- **Reinvitar un email ya `active` en el MISMO tenant**: se rechaza con `Conflict` (409) — no está definido
  qué pasa si se reinvita un email ya `invited` en el mismo tenant (no-op vs refrescar el token); se deja
  como comportamiento no especificado de esta tarea, no bloqueante (el caso ambiguo es de baja frecuencia
  y no tiene impacto de seguridad).
- **Race de `invite()` creando un `User` global nuevo** (TOCTOU: comprobar-si-existe → crear si no): se
  acepta que una colisión concurrente (dos admins invitando el mismo email nuevo a la vez) puede hacer que
  uno de los dos reciba `PortError` (violación de la unicidad de `email`, envuelta) en vez de un resultado
  silencioso — el cliente puede reintentar. No se añade un CAS dedicado para este caso, de frecuencia muy
  baja (alta de un usuario nuevo es un evento raro, no un hot path).

## Recursos externos

- `.claude/specs/general/api-contract.yaml`: paths `auth/*` (incl. ampliación login 2 pasos, a
  documentar), `tickets/*`, `messages/*` (+attachments), `admin/tenants`, `admin/users`,
  `admin/roles`+`capabilities`, `admin/settings`, `kb/*`; schemas `Page`, `Problem`.
- CUs: CU-BE-01 (auth/sesiones — **desactualizado tras este rediseño, revisar/ampliar**), CU-BE-03
  (autorización/aislamiento), CU-BE-04 (ciclo de vida ticket), CU-BE-09 (administración).
- `rbac.md` (capacidades por endpoint).
- `app/domain/ports/repositories.py`, `app/domain/services/*.py` (plan 10, se extienden aquí).
- `app/infra/db/repositories/base.py` (`BaseRepository`, "especulativo, puede remodelarse aquí").
- `app/infra/db/session.py` (`tenant_scope`/`global_scope`).
- `app/core/security.py` (`decode_access_token`/`create_access_token`, ya existen).
- `tests/conftest.py` (fixtures de Postgres real del plan `database-foundation`).
- `alembic/versions/` (migración inicial de `database-foundation`, referencia para la nueva).

## Estimación global

- **Tareas**: 9 (migración+entidades identidad · auth_service reescrito+deps+router auth · envelope de
  error+schemas · adaptadores identidad · admin tenants/users/roles+settings · adaptador+extensión
  ticket+router · adaptador message+storage+router · kb+router — ver detalle en Tasks).
- **Esfuerzo**: nivel integración (Postgres real), con una tarea de migración/rediseño de identidad no
  trivial al principio; más lento que `domain-services`, comparable o algo mayor que
  `database-foundation`; ~2-3 sesiones asistidas.
- **Recursos**: requiere `docker compose up -d db`.

## Criterios de calidad y verificación

- TDD, nivel **integración** para migración/repos/adaptadores/routers (Postgres+pgvector real, Docker).
- Gates por tarea: `ruff`(+`S`) · `ruff format` · `mypy --strict` · `cosmic-ray` (`break:80`) donde
  aplique (adaptadores CRUD triviales pueden ser N/A documentado, criterio M4 de `database-foundation`)
  · `/sdd-lint` · `fact-checker`.
- Hexagonal: adaptadores en `app/infra/*`; routers no importan SQLAlchemy directamente.
- OpenAPI generado se compara manualmente contra el contrato al cerrar cada router (gate automatizado es
  tarea 19).
- La ampliación del contrato (login en 2 pasos) se refleja en `api-contract.yaml` en la propia tarea 02,
  no como un efecto colateral silencioso — el frontend deriva sus mocks de ese fichero.

## Tasks

- [x] `backend-routers-core-01` (P1) — Migración Alembic (identidad multi-tenant: `user` global +
  `user_tenant` + `refresh_session.tenant_id` + `tenant.auto_approve`) + entidades de dominio actualizadas
  (`User`, `UserTenantMembership`, `RefreshSession`) · depends_on: —
- [x] `backend-routers-core-02` (P1) — `auth_service` reescrito (`login` 2 pasos, `select_tenant`,
  `switch_tenant`, `invite`/`accept_invitation` sobre membership, `change_password`, normalización de
  email, chequeo `Tenant.status`) + `security.py` (`purpose`/`tenant_id` opcional) + sincroniza
  `api-contract.yaml` (login 2 pasos, `/auth/switch-tenant` + `User`/`UserInvite`/`UserUpdate`/
  `/admin/users`) + `data-model.md`/`rbac.md` (+ capacidad `tenant.settings.manage`)/CU-BE-01 ·
  depends_on: 01
- [x] `backend-routers-core-03` (P1) — Envelope de error (`DomainError`+`Deny`→problem+json) + schemas
  compartidos (`Page[T]`, `Problem`) · depends_on: —
- [x] `backend-routers-core-04` (P1) — Adaptadores SQLAlchemy de identidad: `TenantRepository` (+
  `list`, `auto_approve`), `UserRepository`, `UserTenantMembershipRepository` (nuevo), `RoleRepository`
  (+ `list`/`update`/`delete`, `effective_capabilities` acotado por tenant), `RefreshSessionRepository`,
  `AuthTokenRepository` · depends_on: 01, 03
- [x] `backend-routers-core-05` (P1) — `deps.get_current_subject`/`get_tenant_context`/
  `require_capability` (decisión de ámbito por-capacidad, precedencia global>tenant) + router `auth`
  completo (incl. `select-tenant`, `switch-tenant`, password forgot/reset/change) · depends_on: 02, 04
- [x] `backend-routers-core-06` (P2) — Routers `admin_tenants`(+`/admin/settings` bajo
  `tenant.settings.manage`, con `tenant_id` query param para ámbito global)/`admin_users` (`PATCH .../{id}`
  = `User.id` global)/`admin_roles` (+ `GET /admin/capabilities`) + auditoría (`AuditLogRepository`) en
  las 3 · depends_on: 05
- [x] `backend-routers-core-07` (P1) — `TicketRepository` (paginación/filtros/orden) + `TicketService`
  (método PATCH parcial) + router `tickets` · depends_on: 05
- [x] `backend-routers-core-08` (P2) — `MessageRepository` + puerto `Storage` (nuevo) + adaptador
  filesystem local + router `messages` (incl. attachments + descarga) · depends_on: 07
- [ ] `backend-routers-core-09` (P3) — Puerto `VectorStore` (nuevo, recortado) + adaptador stub + router
  `kb` · depends_on: 05

## Registro de cambios del plan

- 2026-08-19: creado (draft para grilling). Decisiones tomadas con el owner antes de redactar: (1) `kb`
  entra con adaptador `VectorStore` stub; (2) `attachments` entra con puerto `Storage` + adaptador
  filesystem local; (3) extensiones a `domain-services` dentro de este plan.
- 2026-08-19: `grilling`. **Hallazgo con impacto de diseño**: `LoginRequest` no lleva tenant y `User.
  email` es único por `(tenant_id, email)` — no soporta que un usuario pertenezca a varios tenants.
  Preguntado, el owner confirmó que SÍ debe soportarlo (pantalla de selección si hay 2+ tenants).
  Decisiones resultantes: (4) rediseño de identidad — `User` global (sin `tenant_id`/`status`), tabla
  `user_tenant(user_id,tenant_id,status)` con status por membership, `refresh_session.tenant_id` nuevo;
  login en 2 pasos con `identity_token` corto cuando hay 2+ tenants (en vez de repetir credenciales) —
  **amplía el plan** de 7 a 9 tareas, con una migración nueva sobre el esquema de `database-foundation`
  (sin backfill: no hay datos de producción). (5) `get_tenant_context` decide `tenant_scope`/
  `global_scope` por el ámbito concedido de la **capacidad requerida**, no por un flag fijo del Subject
  (permite mezclar capacidades tenant+global en el mismo rol). (6) `Deny(out_of_scope)` de
  `rbac_service.authorize()` se documenta como defensa en profundidad sin caso real que la dispare hoy
  (con RLS+filtro app-level, un subject `tenant` nunca llega a `authorize()` con un recurso de otro
  tenant); se sigue llamando siempre, por disciplina — mismo criterio que el riesgo conocido de
  `approval_service` en el plan anterior. (7) `GET`/`PATCH /admin/settings` (`TenantSettings.
  auto_approve`) entra en `admin_tenants.py` + migración nueva para `Tenant.auto_approve`, pese a no
  tener consumidor real hasta la tarea 15 — mismo criterio que otros huecos nombrados sin dueño.
- 2026-08-19: `design-review` (subagente fresco, sin routing válido en `models.design-review` — el valor
  configurado `claude-opus-4-8` no es un id de modelo vigente; se avisó y se lanzó heredando el modelo de
  sesión). **6 hallazgos, ninguno "me parece bien" sin evidencia**: (1) el esquema actual YA soporta el
  mismo email en varios tenants (filas `User` separadas, `UniqueConstraint(tenant_id,email)`) — la
  alternativa barata (sin migración) existía y no se documentó como descartada; preguntado, el owner
  confirmó que quiere explícitamente **una sola contraseña compartida** entre membresías (no solo
  "pertenecer a varios tenants"), así que **Objetivo 0 se mantiene** tal cual, ahora con esa justificación
  explícita registrada. (2) el contrato (`User`/`UserInvite`/`UserUpdate`/`/admin/users`) tiene
  `tenant_id`/`status` como campo directo, roto bajo identidad global — **tarea 02 ampliada** para
  sincronizarlo. (3) `data-model.md`/`rbac.md`/CU-BE-01 quedaban desactualizados sin dueño — **tarea 02
  ampliada** para actualizarlos. (4) `/admin/settings` heredaba `tenant.manage` (global-only), contra la
  intención de ADR-0009 (el propio tenant debería poder desactivar `auto_approve`) — **capacidad nueva
  `tenant.settings.manage`** (ámbito `tenant`), añadida a `rbac.md` en la tarea 02, consumida en la 06.
  (5) FR-038 (notificar `ticket.assign`/`ticket.reply`) quedaba en un limbo sin declararse — **hueco
  nombrado explícito** en Fuera de alcance, para el plan 12. (6) `app/core/security.py` no estaba en el
  alcance declarado pese a que el `identity_token` lo necesita — **añadido explícitamente** a Dentro del
  alcance (tarea 02). El resto del plan (schemas compartidos, adaptadores de negocio, `Storage`
  filesystem, `VectorStore` stub, decisión de ámbito por-capacidad, defensa `out_of_scope`) sobrevivió sin
  objeción del revisor.
- 2026-08-19: `scenario-coverage` (subagente QA, sonnet — modelo válido en `models.scenario-coverage`).
  Pasada exhaustiva sobre las 9 tareas + el plan; encontró **1 bug de seguridad real** y varios huecos de
  diseño/escenario. **Fixes sin alternativa razonable, aplicados directamente** (no eran decisiones
  discrecionales): (13) `RoleRepository.effective_capabilities` sin acotar por `tenant_id` filtraría
  capacidades de un tenant a la sesión de OTRO tenant del mismo usuario (el esquema `user_role.tenant_id`
  ya permite roles distintos por tenant) — cambiada la firma a `effective_capabilities(user_id,
  tenant_id)`. (14) ningún flujo comprobaba `Tenant.status=disabled` — añadido a `login`/`select_tenant`/
  `switch_tenant`/`get_tenant_context`. (15) el email no se normalizaba (mayúsculas/minúsculas), más
  grave ahora que es clave de unicidad global — normalización a minúsculas en escritura y lectura.
  **Decisiones del owner** sobre los forks reales: (16) añadido `GET /messages/{id}/attachments/
  {attachment_id}` (sin él, adjuntos no se podían recuperar vía HTTP). (17) `identity_token` reutilizable
  dentro de su TTL (no de un solo uso). (18) `/admin/settings` gana `tenant_id` query param opcional
  (obligatorio en ámbito global, ignorado en ámbito tenant). (19) se cablea `AuditLogRepository` en los 3
  routers admin (mismo patrón que `ticket_service`). (20) `PATCH /admin/users/{id}` usa `User.id` global,
  cruzado con el tenant del subject (404 si no hay membership ahí). (21) `TicketService.transition`/
  `update_fields` **no** ganan CAS — riesgo de lost-update documentado como conocido, sin reabrir el
  diseño de `ticket_service` (plan `domain-services`, ya cerrado) por una ventana de carrera estrecha —
  mismo criterio que el riesgo post-CAS de `approval_service`. (22) añadido `POST /auth/switch-tenant`
  (cambiar de tenant con una sesión ya activa, sin re-login). Además, decenas de escenarios de frontera/
  error/estado se incorporaron directamente a las 9 tareas (paginación, `sort` fuera de whitelist,
  expiración de `identity_token`, confusión de `purpose` entre tokens, membresías en estados mixtos,
  concurrencia real del CAS de `rotate_if_active`, colisión de `filename` en adjuntos, límites de tamaño,
  `q` obligatorio en `kb.search`, etc. — ver `## Scenarios` de cada tarea). **(B) Fuera de alcance
  confirmado sin sorpresas**: rate-limiting de login/refresh/select-tenant, retriever RAG real/ingesta KB,
  storage en nube, flujo-IA (`ai-draft`/grafo), gate OpenAPI automatizado, seeds, backfill de datos —
  todos ya nombrados en el plan, el QA no propuso nada nuevo fuera de esos bullets.
- 2026-08-19: **tareas 01+02 cerradas — fusionadas en una sola sesión de trabajo** (desviación del flujo
  estándar "una tarea `active` a la vez", **aprobada por el owner**). Motivo: cambiar `User`/
  `RefreshSession` en el dominio (tarea 01) rompía `auth_service.py`/`test_auth_service.py` (~8 usos de
  `User.tenant_id`/`User.status`), que la tarea 01 declara explícitamente fuera de alcance — y el fix
  real necesitaba el puerto `UserTenantMembershipRepository` de la tarea 04. Cerrar 01 sola habría dejado
  el repo con tests rotos hasta cerrar 02 (violando su propia DoD "todos los tests en verde"). Presentadas
  3 opciones (fusionar / aceptar rotura transitoria documentada / `xfail`), el owner eligió **fusionar**.
  **Hallazgo adicional durante la fusión**: la migración `0001` (plan cerrado `database-foundation`) no
  estaba congelada — su `upgrade()`/`downgrade()` llamaban a `Base.metadata.create_all()`/`drop_all()`
  sobre los modelos ORM **en vivo**, así que al editar `identity.py` para esta tarea, `0001` habría
  generado directamente el esquema NUEVO en cualquier `upgrade head` desde cero, dejando a `0002` sin
  nada real que alterar (verificado con un `upgrade head` limpio, que falló). Presentadas 3 opciones
  (congelar 0001 / guards de idempotencia en 0002 / squash 0001+0002), el owner eligió **congelar 0001**
  (reescrita para definir su propio `sa.MetaData()` autocontenido con las 18 tablas explícitas,
  reproduciendo el shape histórico exacto). Resultado: 392 tests verdes, `ruff`/`mypy` strict limpios,
  mutation 95.33%/100% (`auth_service.py`/`security.py`, umbral 80%), `/sdd-lint` con 3 ERROR encontrados
  y corregidos en CU-BE-01/02 (re-verificados RESUELTOS por un segundo subagente), `fact-checker` 11/12
  VERIFICADO + 1 NO VERIFICABLE reconocida. Detalle completo en los session logs de ambas tareas
  (`.claude/context/backend/backend-routers-core-01.md`/`-02.md`).
- 2026-08-19: tarea 03 cerrada (envelope de error `problem+json` + schemas `Page[T]`/`Problem`
  compartidos). Tarea 04 cerrada (adaptadores SQLAlchemy de identidad: `Tenant`/`User`/
  `UserTenantMembership`/`Role`/`RefreshSession`/`AuthToken`, con `_enum_bridge` para el mismatch
  domain/ORM y `effective_capabilities` acotado por tenant desde el diseño). Detalle en
  `.claude/context/backend/backend-routers-core-03.md`/`-04.md`.
- 2026-08-19: **tarea 05 cerrada** — `app.core.deps` (`get_current_subject`/`get_tenant_context`/
  `require_capability`) + router `auth` completo. Primera vez que se ejercita el ciclo de vida completo
  de una request HTTP real sobre el dominio de identidad (hasta ahora solo unit-con-fakes o adaptadores
  aislados), y aparecieron **3 bugs reales de infra** que ningún test anterior podía detectar: (1)
  `RoleRepository.effective_capabilities` leía el ámbito del catálogo (`capability.scope`) en vez de
  derivarlo de la asignación (`user_role.tenant_id`), rompiendo la precedencia `global`>`tenant` cuando
  la misma capacidad llega por dos vías; (2) `get_session()` nunca hacía `commit()` — los `flush()` de
  los adaptadores se perdían al cerrar la sesión al final del request; (3) `tenant_scope`/`global_scope`
  abrían `session.begin()` incondicionalmente, rompiendo cuando `get_current_subject` ya había iniciado
  una transacción en la misma sesión (autobegin). Los 3 se confirmaron reproduciendo el fallo antes de
  arreglarlos, con test de regresión. También se encontró y eliminó código MUERTO en `switch_tenant`
  (un `if access_token is None: raise HTTPException(401)` inalcanzable, porque `get_current_subject`
  —dependencia hermana, mismo `oauth2_scheme` cacheado— ya rechaza `None` antes). Mutation gate del
  router `auth` necesitó 2 rondas (29.82%→0.00% survival) tras añadir tests de los endpoints
  `password/forgot`/`password/reset` (sin ningún test previo) y de los atributos exactos de la cookie de
  refresh. `/sdd-lint` semántico: 0 ERROR, 4 AVISO reconocidos (huecos de spec nombrados, no bloqueantes
  — CU-BE-01 sin FR explícito para el flujo multi-tenant, entre otros). `fact-checker`: 12/12 VERIFICADO.
  470 tests verdes en el backend completo. Detalle en
  `.claude/context/backend/backend-routers-core-05.md`.
- 2026-08-19: **tarea 06 cerrada** — routers `admin_tenants`/`admin_users`/`admin_roles` (de esqueleto
  doc-only a código real), con auditoría (`AuditLogRepository`) en toda mutación. Cerró 3 huecos de
  puerto/entidad que el propio `## Spec` de la tarea exigía y que no existían: `AuditLogEntry` sin
  `tenant_id` (obligatorio en la tabla de negocio real, solo se había probado con fakes hasta ahora),
  `RoleRepository` sin asignación `user_role` (`assign`/`unassign_all`/`list_assigned`) ni catálogo
  completo de capacidades (`list_all_capabilities`)/gestión de capabilities de un rol
  (`set_capabilities`), y sin adaptador real de `AuditLogRepository` (`SqlAlchemyAuditLogRepository`,
  nuevo). `api-contract.yaml` ganó el query param `tenant_id` de `/admin/settings` (decisión 18 de
  `scenario-coverage`, nunca sincronizada al contrato hasta ahora). Mutation gate en 2-3 rondas por
  router (12.50%/2.78%/6.67% survival final); `/sdd-lint` encontró 1 ERROR real (faltaba el escenario
  de "no escalar privilegios" en el Gherkin de la tarea, criterio de aceptación de CU-BE-09 ligado a
  FR-037) — corregido con escenario + test; 4 AVISO de sincronización spec↔tarea reconocidos, no
  bloqueantes. `fact-checker` 16/16 VERIFICADO. 514 tests verdes en el backend completo. Detalle en
  `.claude/context/backend/backend-routers-core-06.md`.
- 2026-08-19: **tarea 07 cerrada** — `TicketRepository` (paginación/filtros/orden real, antes solo
  `list(tenant_id)`) + `TicketService.update_fields` (PATCH parcial) + router `tickets` completo:
  primer router/adaptador de NEGOCIO (RLS real) de la sesión. Necesitó 2 adaptadores/puerto nuevos no
  anticipados explícitamente en la DoD para que `ticket_service.create()` (ya cerrado en
  `domain-services`) tuviera dependencias reales: `SqlAlchemyMessageRepository` (mínimo, `add`/
  `list_by_ticket` — la tarea 08 lo amplía) y `StubSlaPolicy` (`data-model.md` §11 deja la política
  real para la tarea 18; el stub siempre devuelve `None`, sin inventar horas por prioridad). Capacidad
  nueva `ticket.update` añadida a `rbac.md` (el catálogo no tenía ninguna para "editar campos sin
  cambiar de estado"). **Bug real de infraestructura encontrado**: la migración 0002 (identidad
  multi-tenant) creó `user_tenant` sin `GRANT` para el rol runtime `syntax_app` — el `GRANT ALL TABLES`
  de la migración 0001 solo cubre tablas ya existentes, no las que llegan después. Ninguna tarea
  anterior lo detectó porque sus tests de router usaban `superuser_engine` (bypassa permisos) incluso
  para las requests HTTP; esta tarea es la primera en usar `app_engine` (rol real) en un test de
  router, lo que expuso el fallo de inmediato (`permission denied for table user_tenant` al asignar un
  ticket). Corregido en la propia migración (pre-lanzamiento, sin datos reales). Mutation gate verde en
  el adaptador (11.41%) y el router (7.62%); `/sdd-lint` encontró 1 hallazgo (`ticket.update` prometía
  cubrir `csat` en `rbac.md` pero la tarea no lo mencionaba explícitamente ni lo testeaba — el código SÍ
  lo cableaba correctamente vía `set_csat`; se corrigió añadiendo los tests/escenarios/aclaración de
  spec que faltaban) + 2 AVISO de sincronización spec↔CU reconocidos. `fact-checker` 17/18 VERIFICADO +
  1 INCORRECTO (conteo de tests del session log) corregido. 559 tests verdes en el backend completo.
  Detalle en `.claude/context/backend/backend-routers-core-07.md`.
- 2026-08-19: **tarea 08 cerrada** — puerto `Storage` (nuevo, filesystem local) + `MessageRepository`
  ampliado para adjuntos (`Attachment`, nueva entidad) + router `messages` completo (hilo con filtro de
  visibilidad server-side a nivel de query, subida/descarga de adjuntos). Se pidió permiso al owner
  para añadir `python-multipart` (dependencia nueva, requerida por FastAPI para `UploadFile`/multipart
  — el endpoint de subida ya estaba en el contrato desde antes de esta tarea) — autorizada. La
  capacidad de escritura de un mensaje/adjunto (`ticket.reply` vs `note.internal.write`) se decide en
  RUNTIME por su `visibility`, no en tiempo de definición de ruta — no encajaba en
  `Depends(require_capability(...))`, resuelto invocando `get_tenant_context` directamente y
  comprobando la capacidad específica a mano. Mutation gate verde en el adaptador de storage (2.94%) y
  el router (7.69% tras un refuerzo). `/sdd-lint`: 0 ERROR, 2 AVISO (mismo origen: `spec.md`/CU-BE-04
  no anticipan adjuntos, funcionalidad nacida directamente del contrato) — el subagente semántico murió
  por un error de conexión en su primer intento y se relanzó con normalidad. `fact-checker` 17/17
  VERIFICADO. 587 tests verdes en el backend completo. Detalle en
  `.claude/context/backend/backend-routers-core-08.md`.
