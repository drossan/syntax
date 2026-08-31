# Spec — Frontend del helpdesk Syntax (Next.js 16 · SPA client-rendered)

> **Capa SDD** (`features.sdd`). Es el **"QUÉ"** del frontend: requisitos en **EARS**. El **"CÓMO"** de
> cada actor vive en los [casos de uso](#casos-de-uso); las **decisiones** de arquitectura, en los
> [ADR](../adr/adr-index.md); las **políticas transversales** detalladas, en
> [`cross-cutting.md`](./cross-cutting.md). El frontend se desarrolla **contra el contrato de API**
> ([[../adr/0002-contrato-openapi-first]]) vía cliente tipado + mocks MSW; el backend real no es
> precondición (se consume mockeado).

## Resumen

Frontend del helpdesk de Syntax: **SPA client-rendered** (Next.js 16 App Router + TS estricto + Tailwind
v4 + shadcn/ui) con **gestión de tickets completa**, **multi-tenant desde el día 1** y el **flujo IA +
aprobación humana**, todo navegable por rol y tenant.

## User stories

- **US-1 (P1)** — Como **usuario/agente**, quiero iniciar sesión de forma segura y que la sesión se renueve sola, para trabajar sin interrupciones.
- **US-2 (P1)** — Como **plataforma cliente**, quiero mostrar solo rutas/acciones que el rol permite, para reflejar el RBAC (defensa en profundidad sobre la API).
- **US-3 (P1)** — Como **agente/usuario**, quiero gestionar tickets (lista, alta, detalle, estado, asignación), para llevar el soporte end-to-end.
- **US-4 (P1)** — Como **agente de Soporte**, quiero disparar un borrador IA y **aprobarlo/editarlo/rechazarlo**, para responder con control humano.
- **US-5 (P2)** — Como **usuario con acceso a varios tenants** (cliente o personal de Soporte), quiero cambiar entre ellos, para operar sin fugas de datos entre clientes.
- **US-6 (P3)** — Como **usuario**, quiero buscar en la base de conocimiento, para autoservirme antes de abrir un ticket.
- **US-7 (P3)** — Como **administrador**, quiero gestionar tenants/usuarios e invitar, para operar la plataforma.

## Requisitos funcionales (EARS)

> Detalle de políticas transversales en [`cross-cutting.md`](./cross-cutting.md); shape de datos en
> [`../backend/data-model.md`](../backend/data-model.md); permisos en
> [`../backend/rbac.md`](../backend/rbac.md).

### Contrato, auth y sesión — [[../adr/0002-contrato-openapi-first]] · [[../adr/0003-frontend-spa-client-rendered]] · [[../adr/0004-auth-jwt-access-memoria-refresh-cookie-rotacion]]

- **FR-001** — El sistema DEBERÁ generar el cliente tipado y los tipos desde `api-contract.yaml` (`openapi-typescript`) y **validar los handlers MSW** (éxito y error) contra el schema, con un **gate de conformidad** en CI. <!-- requisito de build/CI sin actor → sin caso de uso; se verifica por su criterio de éxito de conformidad de contrato y su NFR de conformidad -->.
- **FR-002** — Cuando la API responde con envelope `problem+json`, el sistema DEBERÁ mapearlo a `{toast, fieldErrors}` localizados (util `problemToUi`).
- **FR-003** — El sistema DEBERÁ mantener el **access token en memoria** y hacer todo data-fetching autenticado **client-side** (TanStack Query + cliente tipado).
- **FR-004** — Cuando falta la cookie refresh en una ruta privada, el `middleware.ts` DEBERÁ **redirigir** al login (UX, no control de seguridad).
- **FR-005** — Cuando llegan **N respuestas 401 concurrentes**, el interceptor DEBERÁ renovar la sesión **una sola vez** (single-flight) y reintentar las peticiones.
- **FR-006** — Si la renovación detecta reuse (refresh robado/rotado), entonces el sistema DEBERÁ hacer **logout limpio**.
- **FR-007** — Cuando el usuario cierra sesión, el sistema DEBERÁ **resetear el `queryClient`** y detener todo polling (draft, notificaciones, colas).
- **FR-028** — Si el login resuelve **2+ membresías `active`** del usuario en tenants distintos, el sistema DEBERÁ ofrecer elegir uno antes de completar la sesión; si la elección es rechazada, DEBERÁ informarlo y permitir reintentar sin repetir credenciales.

### RBAC de cliente y tenant — [[../adr/0005-rbac-por-capacidad-y-ambito]]

- **FR-008** — El sistema DEBERÁ mostrar rutas, menús y acciones **según las capacidades** de la sesión, nunca según el nombre del rol.
- **FR-009** — Si las capacidades de la sesión no se resuelven, entonces el sistema DEBERÁ **no ofrecer** ninguna acción/ruta privilegiada (fail-closed).
- **FR-010** — Si la API deniega una acción visible con **403**, entonces el sistema DEBERÁ informarlo **sin mutar estado** (reconciliación).
- **FR-011** — Cuando el usuario cambia de tenant, el sistema DEBERÁ **invalidar las cachés dependientes de tenant** y descartar respuestas en vuelo del tenant anterior. Si el cambio es rechazado por la API, el sistema NO DEBERÁ limpiar esa caché hasta confirmar el éxito, de forma que la vista permanezca con los datos del tenant anterior.

### Tickets — [[../adr/0011-entrega-draft-por-polling-no-sse-fase-1]]

- **FR-012** — El sistema DEBERÁ mostrar la bandeja de tickets con filtros, búsqueda, indicadores de SLA y el **orden determinista** del contrato, reflejando los filtros/orden en la **URL** (URL-state).
- **FR-013** — Cuando el usuario da de alta un ticket, el sistema DEBERÁ validar el formulario (RHF+Zod) antes de enviarlo.
- **FR-014** — Mientras se muestra el detalle de un ticket, el sistema DEBERÁ ocultar los mensajes `internal` a quien no tenga `note.internal.read`.
- **FR-015** — Cuando el usuario muta un ticket idempotente (estado/prioridad/asignación), el sistema DEBERÁ aplicar **optimistic-update** con **rollback** por envelope de error.
- **FR-016** — Si la acción es destructiva (rechazar draft, cerrar ticket, borrar user/tenant), entonces el sistema DEBERÁ pedir **confirmación** antes de ejecutarla.
- **FR-017** — El sistema DEBERÁ mostrar los adjuntos en **solo lectura** (sin subida en Fase 1).
- **FR-029** — Cuando el cuerpo de un mensaje del hilo (de cualquier autor) contiene sintaxis
  Markdown, el sistema DEBERÁ renderizarlo formateado mediante un allow-list explícito de elementos,
  manteniendo la garantía anti-XSS de NFR-004 (nunca HTML crudo interpretado).

### Flujo IA — [[../adr/0007-hitl-asincrono-postgressaver-checkpointer]] · [[../adr/0009-confianza-hibrida-y-auto-approve-por-tenant]]

- **FR-018** — El sistema DEBERÁ mostrar la **cola de aprobaciones** ordenada por SLA/confianza.
- **FR-019** — Cuando se dispara un draft, el sistema DEBERÁ hacer **polling** de `GET /agent-runs` hasta `succeeded`/`failed`, con estado de carga y **reintento** ante `failed`.
- **FR-020** — Cuando el agente decide, el sistema DEBERÁ permitir **aprobar, editar o rechazar** el borrador con **nota-al-humano** (confirm en rechazar).

### KB, admin y transversales

- **FR-021** — El sistema DEBERÁ ofrecer buscador semántico de la KB y explorar por dominio/package, con vista de UC.
- **FR-022** — El sistema DEBERÁ permitir CRUD de tenants/usuarios e **invitación**, y vistas **read-only** de roles/capacidades + asignación de roles semilla.
- **FR-023** — Cada feature con fetch DEBERÁ declarar y testear sus estados **loading / error / empty** (accesibles).
- **FR-024** — El sistema DEBERÁ renderizar **todo contenido de origen usuario/IA como texto inerte** (anti-XSS; sin `dangerouslySetInnerHTML` sobre contenido no confiable).
- **FR-025** — Si la conexión se pierde (offline), entonces el sistema DEBERÁ degradar de forma legible y reintentar al recuperar.
- **FR-026** — Si hay cambios sin guardar y el usuario navega fuera, entonces el sistema DEBERÁ avisar (nav-guard).
- **FR-027** — Cuando llega una notificación in-app, el sistema DEBERÁ reflejar el contador de **no-leído** (polling).

## Requisitos no funcionales

- **NFR-001** — **TS estricto**: `strict` + `noUncheckedIndexedAccess`; **`any` prohibido**.
- **NFR-002** — **a11y por-feature**: roles, foco y teclado en la DoD de cada feature; auditoría `axe` en navegador real.
- **NFR-003** — **i18n**: ES 100% / EN progresivo; fechas/números/SLA/timezone por locale (next-intl/`Intl`); una clave sin traducir **degrada** a fallback legible (no la clave cruda). Detalle: [`cross-cutting.md`](./cross-cutting.md) §2.
- **NFR-004** — **Anti-XSS**: contenido externo como texto inerte; markdown sanitizado con allow-list. Detalle: [`cross-cutting.md`](./cross-cutting.md) §1.
- **NFR-005** — **Concurrencia optimista**: respuestas fuera de orden y conflictos (409) dejan el estado consistente con la última acción real. Detalle: [`cross-cutting.md`](./cross-cutting.md) §6.
- **NFR-006** — **Conformidad de contrato**: tipos+mocks regeneran limpio; CI falla ante drift ([[../adr/0002-contrato-openapi-first]]).

## Criterios de éxito

- **SC-001** — El gate de conformidad de contrato (`gen:api:check`) pasa sin drift en CI.
- **SC-002** — Un usuario sin una capacidad **no ve** su acción/ruta; si la API responde 403, la UI **no** cambia estado.
- **SC-003** — Ante N 401 concurrentes se produce **una sola** renovación (single-flight); reuse → logout limpio.
- **SC-004** — Al cambiar de tenant, ninguna vista muestra datos del tenant anterior (caché invalidada, en-vuelo descartado).
- **SC-005** — Cada feature con fetch tiene test de sus estados loading/error/empty con aserción real (supera el gate de mutation).
- **SC-006** — Marcado tipo `<script>` en contenido externo se muestra como **texto** y no se ejecuta.
- **SC-007** — Los smokes e2e del happy-path crítico (login→ticket→draft→aprobación + tenant-switch) pasan en verde.

## Casos de uso

- [CU-FE-01: Login y sesión de cliente](./casos-de-uso/CU-FE-01-login-y-sesion.md)
- [CU-FE-02: RBAC de cliente y cambio de tenant](./casos-de-uso/CU-FE-02-rbac-cliente-y-cambio-de-tenant.md)
- [CU-FE-03: Bandeja de tickets](./casos-de-uso/CU-FE-03-bandeja-de-tickets.md)
- [CU-FE-04: Alta de ticket](./casos-de-uso/CU-FE-04-alta-de-ticket.md)
- [CU-FE-05: Detalle, visibilidad y mutaciones](./casos-de-uso/CU-FE-05-detalle-visibilidad-y-mutaciones.md)
- [CU-FE-06: Flujo IA — cola, draft y decisiones](./casos-de-uso/CU-FE-06-flujo-ia-cola-draft-decisiones.md)
- [CU-FE-07: Base de conocimiento](./casos-de-uso/CU-FE-07-base-de-conocimiento.md)
- [CU-FE-08: Administración y roles](./casos-de-uso/CU-FE-08-administracion-y-roles.md)
- [CU-FE-09: Transversales (notificaciones, i18n, estados)](./casos-de-uso/CU-FE-09-transversales.md)

## Fuera de alcance

- **Backend real** (se consume vía MSW), **SSO/OIDC**, **subida** de adjuntos (storage stub → solo vista),
  **composer** de roles custom (diferido a enforcement real), **streaming SSE** del draft (polling).
- Email real, canned responses, CSAT UI, merge/duplicados, bulk actions, impersonation, webhooks/push, **BFF de Next** (descartado, [[../adr/0003-frontend-spa-client-rendered]]).

## Aclaraciones pendientes

> Follow-ups del owner (no bloquean; declarados en la retro de `helpdesk-core`): auditoría **axe en
> navegador real** (requiere `@axe-core/playwright`, dep nueva no añadida sin aprobación) y **nav-guard soft**
> del App Router (hoy `beforeunload`). Sin entradas `NECESITA ACLARACIÓN` abiertas.
