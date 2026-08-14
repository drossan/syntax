---
id: frontend-helpdesk-core
package: frontend
status: completed        # pending | active | completed | cancelled
branch: plan/frontend/helpdesk-core
created: 2026-08-11
updated: 2026-08-13
---

# Frontend — Helpdesk core (Next.js 16 + Tailwind v4 + shadcn/ui)

> Renombrado desde `helpdesk-phase-1` (violaba la convención de `<name-plan>` sin sufijo numérico
> ambiguo; ver design-review M1). `phase-1` era el estado del producto, no el nombre del plan.

## Contexto y problema

Frontend del helpdesk de Syntax: moderno, **gestión de tickets real y completa**, **multi-tenant
desde el día 1**. **Spec-Driven Design + TDD** (tests 1:1 desde Gherkin). Se desarrolla contra el
**contrato de API** del backend (`backend-skeleton-foundation-06`) vía cliente tipado + mocks MSW.

**Arquitectura (fijada en design-review):** app **client-rendered** — el access token vive en memoria
(no legible por Server Components), así que **todo data-fetching autenticado es client-side** (TanStack
Query + cliente tipado); los **Server Components** se usan solo para *chrome* estático. El `middleware.ts`
hace **redirect UX** por presencia de cookie refresh (**no es control de seguridad**: eso lo hace la API).

**Contrato como mecanismo, no como prosa (C1):** `backend-06` debe entregar **OpenAPI 3.1 real**; el
frontend **genera** tipos (`openapi-typescript`) y **valida** los handlers MSW contra el schema, con un
**gate de conformidad** en CI. Sin esto, tipos/mocks/e2e derivan del contrato y validan una ficción.

**Decisión transversal de mutaciones (M3):** optimistic-update con rollback por envelope de error en
mutaciones de ticket idempotentes; invalidación (revalidación) en el resto; **confirm dialog** en acciones
destructivas (rechazar draft, cerrar ticket, borrar user/tenant).

Fase 1 = KB de documentación + aprobación humana obligatoria; visibilidad `public|internal` (Fase 2 fuera).

## Objetivos

1. **Helpdesk funcional (mockeado) navegable por rol y tenant** end-to-end (login→ticket→draft→aprobación).
2. **Gestión de tickets completa** (lista, alta, detalle, estado, asignación, prioridad, tags, adjuntos
   *view-only*, visibilidad, SLA, timeline).
3. **Flujo IA + aprobación** (cola por SLA/confianza; ciclo de draft con **polling**; decisiones + nota-al-humano).
4. **RBAC por capacidades** + tenant switcher; **roles read-only + asignación de roles semilla** (composer diferido).
5. **Base estricta y probada**: TS estricto sin `any`, a11y **por-feature**, gate de mutation por tarea,
   e2e smokes del happy-path crítico, i18n sin strings hardcodeados, **conformidad de contrato en CI**.

## Alcance y fuera de alcance

### Dentro del alcance
- Contrato mecánico: codegen de tipos + MSW validado + util `problem+json → {toast, fieldErrors}` i18n.
- Auth: login; `middleware.ts` (redirect por cookie); bootstrap `/auth/refresh`; **interceptor 401 con
  single-flight** (una sola renovación ante N 401 concurrentes; reuse-detection → logout limpio); UI de
  reset/set/aceptar-invitación de contraseña.
- RBAC cliente (capacidades) + tenant switcher; roles/capacidades read-only + asignación de roles semilla.
- Tickets: bandeja (TanStack Table, filtros, orden determinista, búsqueda, SLA), alta (RHF+Zod), detalle
  (hilo + visibilidad; mutaciones estado/prioridad/asignación con optimistic/confirm; adjuntos view-only;
  SLA + timeline).
- Flujo IA: cola (orden SLA/confianza); ciclo de draft (disparo + polling `GET /agent-runs` + `failed` +
  reintento); decisiones (aprobar/editar/rechazar + nota-al-humano).
- KB (buscador semántico + explorar + vista UC). Admin (tenants/usuarios + invitación). Dashboard.
- Transversales: notificaciones in-app (polling); i18n (ES 100% / EN progresivo); **estados error/loading/
  empty y a11y básica van en la DoD por-feature**; auditoría a11y final en navegador real; tema/dark.
- **e2e Playwright**: smokes del happy-path crítico (login→ticket→draft→aprobación + tenant-switch).

### Fuera de alcance
- SSO/OIDC (Fase 2). Backend real (se consume vía MSW). Nota al desarrollador / visibilidad `developer`.
- Streaming SSE del draft (polling). **Composer** de roles custom (diferido a enforcement real). **Subida**
  de adjuntos (storage stub → solo visualización). e2e de flujos no-críticos (cubiertos por RTL+MSW).
- Email real, canned responses, CSAT UI, merge/duplicados, bulk actions, impersonation, webhooks/push,
  BFF de Next (descartado: SPA llama a la API directamente).

## Recursos externos

- Contrato: `.claude/specs/general/api-contract.md` (**OpenAPI 3.1**, `backend-…-06`). Datos/permisos:
  `.claude/specs/backend/{data-model,rbac}.md` (`backend-…-03/02`). Tipos: `openapi-typescript`; mocks:
  MSW validado contra schema.
- UI: shadcn/ui + Tailwind v4. Query: TanStack Query. Forms: RHF+Zod. Tablas: TanStack Table. i18n:
  next-intl. Tests: Vitest+RTL+MSW+Stryker; Playwright (smokes).

## Estimación global

- **Tareas totales**: 22 (ver lista al final).
- **Esfuerzo estimado**: ~12–16 sesiones (TDD real).
- **Recursos**: 1 dev frontend; **precondición dura**: `backend-06` entrega OpenAPI 3.1 real.

## Criterios de calidad y verificación

- TDD por tarea (rojo antes); tests 1:1 desde Gherkin; `pnpm --filter frontend lint` + `pnpm test` verde.
- Gate de mutation (Stryker, `break: 80`) por tarea. **Gate de conformidad de contrato** en CI (tipos+mocks
  regeneran limpio; falla si drift). e2e smokes (fuera del gate por tarea).
- TS estricto (`any` prohibido); **a11y y estados error/loading/empty en la DoD de cada feature**; RBAC/
  tenant/visibilidad respetados; sin strings hardcodeados.

## Tasks

- [x] `frontend-helpdesk-core-01` (P1) — Scaffold Next 16 + TS estricto + Tailwind v4 + shadcn + Vitest/RTL/MSW + Stryker + Playwright(config) + RHF/Zod/Query/Table + next-intl + estructura  · *(carve-out: smoke-start en vez de rojo-primero)*  · depends_on: —
- [x] `frontend-helpdesk-core-02` (P1) — Cliente API: **codegen tipos** (`openapi-typescript`) + **MSW validado contra schema** + **util error `problem+json→{toast,fieldErrors}`** i18n + manejo 429 + **gate de conformidad**  · depends_on: frontend-helpdesk-core-01, backend-skeleton-foundation-06
- [x] `frontend-helpdesk-core-03` (P1) — Auth core: login + `middleware.ts` (redirect por cookie) + bootstrap `/auth/refresh` + **interceptor 401 single-flight** + reuse-detection→logout + contexto/hooks  · depends_on: frontend-helpdesk-core-02, backend-skeleton-foundation-06
- [x] `frontend-helpdesk-core-04` (P2) — UI contraseña (B.3): reset / set / aceptar invitación (RHF+Zod)  · depends_on: frontend-helpdesk-core-03
- [x] `frontend-helpdesk-core-05` (P1) — RBAC cliente (capacidades) + rutas/menús por rol + contexto de tenant + **tenant switcher**  · depends_on: frontend-helpdesk-core-03, backend-skeleton-foundation-02
- [x] `frontend-helpdesk-core-06` (P2) — App shell/layout (nav, header, tema/dark, responsive, switch idioma)  · depends_on: frontend-helpdesk-core-05
- [x] `frontend-helpdesk-core-07` (P2) — Tickets: bandeja (TanStack Table, filtros, orden determinista, búsqueda, indicadores SLA)  · depends_on: frontend-helpdesk-core-06, backend-skeleton-foundation-03, backend-skeleton-foundation-06
- [x] `frontend-helpdesk-core-08` (P2) — Alta de ticket (RHF+Zod)  · depends_on: frontend-helpdesk-core-07
- [x] `frontend-helpdesk-core-09` (P2) — Ticket detalle: hilo + **filtro de visibilidad `public|internal`** (lectura)  · depends_on: frontend-helpdesk-core-07, backend-skeleton-foundation-03, backend-skeleton-foundation-06
- [x] `frontend-helpdesk-core-10` (P2) — Ticket mutaciones: estado/prioridad/asignación (**optimistic + confirm**)  · depends_on: frontend-helpdesk-core-09
- [x] `frontend-helpdesk-core-11` (P3) — Adjuntos: **solo visualización** (subida diferida)  · depends_on: frontend-helpdesk-core-09
- [x] `frontend-helpdesk-core-12` (P3) — SLA + timeline de actividad del ticket  · depends_on: frontend-helpdesk-core-09
- [x] `frontend-helpdesk-core-13` (P2) — Cola de aprobaciones (orden por SLA/confianza)  · depends_on: frontend-helpdesk-core-09, backend-skeleton-foundation-05, backend-skeleton-foundation-06
- [x] `frontend-helpdesk-core-14` (P2) — Ciclo de draft IA (disparo + **polling** `GET /agent-runs` + `failed` + reintento)  · depends_on: frontend-helpdesk-core-13
- [x] `frontend-helpdesk-core-15` (P2) — Decisiones: aprobar/editar/rechazar + nota-al-humano (**confirm** en rechazar)  · depends_on: frontend-helpdesk-core-14
- [x] `frontend-helpdesk-core-16` (P3) — Base de conocimiento: buscador semántico + explorar por dominio/package + vista UC + relacionados  · depends_on: frontend-helpdesk-core-06, backend-skeleton-foundation-06
- [x] `frontend-helpdesk-core-17` (P3) — Admin: CRUD tenants + usuarios + **invitación**  · depends_on: frontend-helpdesk-core-06, backend-skeleton-foundation-02, backend-skeleton-foundation-03, backend-skeleton-foundation-06
- [x] `frontend-helpdesk-core-18` (P3) — Roles: **vistas read-only de roles/capacidades + asignación de roles semilla** (composer diferido)  · depends_on: frontend-helpdesk-core-17, backend-skeleton-foundation-02
- [x] `frontend-helpdesk-core-19` (P3) — Dashboard/analytics (métricas, gráficas)  · depends_on: frontend-helpdesk-core-07, frontend-helpdesk-core-13
- [x] `frontend-helpdesk-core-20` (P3) — Transversales: notificaciones in-app (polling) + i18n completitud (ES/EN) + auditoría a11y en navegador real  · depends_on: frontend-helpdesk-core-06
- [x] `frontend-helpdesk-core-21` (P3) — **e2e Playwright** (smokes del happy-path crítico: login→ticket→draft→aprobación + tenant-switch)  · depends_on: frontend-helpdesk-core-15, frontend-helpdesk-core-05, frontend-helpdesk-core-20
- [x] `frontend-helpdesk-core-22` (P3) — Requisitos transversales de helpdesk (**URL-state, no-leído, nav-guard, offline**)  · *(scenario-coverage T5/T6/T7/T10)*  · depends_on: frontend-helpdesk-core-07, frontend-helpdesk-core-08

## Registro de cambios del plan

- 2026-08-11: creado como `helpdesk-phase-1` (materializado desde el plan de programa aprobado).
- 2026-08-11: decisiones heredadas del grilling backend + promociones scenario-coverage (B.1/B.2/B.3).
- 2026-08-11: **refinado con `grilling`** (4 ramas): base Query/RHF/Zod/Table/next-intl; auth middleware-cookie + refresh; i18n infra+ES+EN progresivo; (e2e completo — luego revertido).
- 2026-08-11: **`design-review`** (subagente adversario). Decisiones del owner: **e2e → smokes críticos** (C5);
  **role builder → read-only + asignación de semilla, composer diferido** (C6); **aplicar todo el resto**:
  - **C1** contrato mecánico: `backend-06` entrega **OpenAPI 3.1 real** (precondición); `frontend-02` hace
    **codegen de tipos + MSW validado contra schema + gate de conformidad**.
  - **C2** deps cross-plan declaradas (05→backend-02; 07/09→backend-03,06; 13→backend-05,06; 17→backend-02/03/06; 18→backend-02).
  - **C3/C4/I5** splits: auth core (03) / UI contraseña (04); detalle-lectura (09) / mutaciones (10) /
    adjuntos (11) / SLA+timeline (12); cola (13) / ciclo draft (14) / decisiones (15).
  - **I1** app **client-rendered** fijada; middleware = redirect UX (no seguridad); HOW-TO ajustado.
  - **I2** interceptor 401 **single-flight** + reuse-detection→logout (contra el `RefreshSession` del backend).
  - **I3** util compartida `problem+json→UI` en 02. **I4** estados+a11y a la **DoD por-feature**; axe en navegador real (20).
  - **M1** renombrado `helpdesk-phase-1`→**`helpdesk-core`**. **M2** adjuntos **view-only**. **M3** decisión transversal
    optimistic/revalidación/confirm. **M4** carve-out smoke-start del scaffold.
  - Resistió: i18n día 1, RBAC por capacidad, polling vs SSE, mocks de error, dep 02→backend-06.
- 2026-08-11: descompuesto en 21 task files con Gherkin real (TDD).
- 2026-08-11: **`scenario-coverage`** (subagente QA fresco sobre las 21 tareas + plan). Incorporación
  **híbrida** (decisión del owner): (a) **políticas transversales** → nueva spec
  `.claude/specs/frontend/cross-cutting.md` (anti-XSS, i18n fecha/número/tz, ciclo de caché logout/
  tenant-switch, estados error/loading/empty por-feature, reconciliación 403/fail-closed, concurrencia
  optimista); (b) **tarea 22 nueva** con los requisitos que ninguna tarea cubría (URL-state T5, no-leído
  T10, nav-guard T6, offline T7); (c) escenarios dirigidos de **aislamiento-tenant y concurrencia** como
  `## Refuerzos` en 05/07/09/10/13/15/17; (d) **informe QA completo** guardado en
  `.claude/context/frontend/scenario-coverage-2026-08-11.md` (cola larga que recoge cada sesión TDD).
  **(B)** 14 huecos fuera del alcance declarado → reconocidos y **diferidos** (mapean a bullets de
  `### Fuera de alcance`; no se convierten en tarea). Total: **22 tareas**.
- 2026-08-11: frontend **listo para handoff** (grilling + design-review + scenario-coverage superados).
- 2026-08-13: **tareas 07–22 completadas** (TDD real, mutation gate ≥80 por tarea, fact-checker por tarea).
  Estado final: **297 tests unit/RTL/MSW verdes (68 files)**, typecheck y lint limpios, gate de conformidad de
  contrato (`gen:api:check`) sin drift, y **2 smokes e2e Playwright** (camino dorado + tenant-switch) en verde.

## Nota retro (2026-08-13)
- **Estimación vs real**: estimado ~12–16 sesiones; ejecutado en una pasada continua (~19 h de trabajo real
  agregado por los session logs). Las tareas de lógica pura (07–08, 22) fueron más rápidas; las de flujo
  react-query (10, 14, 15, 17) requirieron tests unitarios de hooks (`renderHook` + spies) para superar el
  gate de mutación — patrón que emergió pronto y se reutilizó.
- **Sorpresas / gaps de contrato** (documentados en los session logs, ninguno bloqueó): `/tickets` sin
  `q`/`tag`/tenant param (07/21); `ApprovalTask` sin confidence/SLA (13); `AgentRun` sin `draft_body` (14);
  sin GET de adjuntos ni endpoint de audit/actividad (11/12); `KBDocument` sin secciones/relacionados (16);
  sin DELETE/PATCH de tenant (17); "leído" no expuesto server-side → derivado en cliente (22).
- **Dependencias no vistas**: colisión de basename `.ts`/`.tsx` (15, 18) — resuelta renombrando la lógica pura;
  React Strict Mode duplica efectos → singleton para arrancar MSW en navegador (21); Stryker excluye `.tsx`
  (la lógica testeable vive en `.ts`).
- **Pendientes / follow-ups del owner**: (a) auditoría **axe en navegador real** — requiere `@axe-core/playwright`
  (dep nueva, no añadida sin aprobación); (b) guard de **nav soft** del App Router (hoy beforeunload); (c) los
  gaps de contrato de arriba, cuando el backend los cubra.
- **Cierre del plan**: PR de `plan/frontend/helpdesk-core` → rama de integración y merge quedan a decisión del
  owner (no se abrió PR ni se hizo push automáticamente).
