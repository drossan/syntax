---
id: frontend-multi-tenant-login
package: frontend
status: completed
branch: plan/frontend/multi-tenant-login
issue:
created: 2026-08-21
updated: 2026-08-21
---

# Login multi-tenant: selección de tenant y switch-tenant real

## Contexto y problema

El contrato (`api-contract.yaml`, desde `b262a4b`) ya define el login multi-tenant: `POST
/auth/login` devuelve `oneOf [TokenResponse, LoginTenantSelection]` (2+ membresías → `identity_token`
+ `tenants: TenantChoice[]`, sin refresh-cookie); `POST /auth/select-tenant` (identity_token +
tenant_id → `TokenResponse`); `POST /auth/switch-tenant` (tenant_id, sesión ya activa →
`TokenResponse`). Backend: `CU-BE-01` ya lo especifica con Gherkin completo.

El frontend nunca lo implementó:

- `auth-context.tsx.login()` asumía siempre `access_token`; una sesión anterior (PR #6, ya en `main`)
  lo dejó devolviendo un error fijo `"Selección de tenant no disponible"` ante `LoginTenantSelection`
  — evita el crash, pero el login multi-tenant sigue sin funcionar.
- `TenantSwitcher` es **cosmético**: su `setActiveTenant` solo cambia un `useState` local; nunca
  llama a `POST /auth/switch-tenant`. Verificado en el contrato: `GET /tickets` y el resto de
  endpoints de negocio **no aceptan** `?tenant_id=` — el tenant se deriva del `subject.tenant_id`
  del JWT. Sin cambiar de verdad de sesión, nadie puede ver los datos de otro tenant aunque el
  switcher "cambie" de valor. `tenant-switcher.test.tsx` solo comprueba que el `<select>` cambia de
  valor, nunca que cargan datos del tenant nuevo — el gap pasa inadvertido en tests.
- El switcher hoy solo es visible para Soporte (ámbito `global`). Verificado en
  `.claude/specs/backend/data-model.md` (líneas 30, 75): `user_tenant` (membership) es la MISMA
  tabla para clientes y Soporte — el ámbito `global` de Soporte solo afecta a qué *capacidades*
  tiene una vez dentro de un tenant, no a qué tenants puede *elegir*. Un cliente con 2+ membresías
  tiene hoy el mismo problema (sin forma de cambiar de tenant sin re-login) y no hay razón para no
  arreglarlo igual.

Este plan cierra los tres huecos: pantalla de selección de tenant en el login (cards), wiring real
de `switch-tenant`, y visibilidad del switcher para **cualquier** usuario con 2+ tenants (no solo
Soporte).

## Objetivos

1. **Login con 2+ tenants permite elegir uno y entrar** (`POST /auth/select-tenant`).
   - *Criterio de éxito*: test RTL — tras login con `LoginTenantSelection`, se muestran cards con
     cada tenant; elegir una autentica y navega a `/`.
2. **Un error al seleccionar tenant (401/422) no rompe el flujo** — se informa y se puede reintentar
   (el `identity_token` es reutilizable dentro de su TTL, `RN-3` de `CU-BE-01`).
   - *Criterio de éxito*: test — `select-tenant` con error muestra alerta accesible sobre la propia
     pantalla de cards (no vuelve al login), con un botón "Volver a iniciar sesión" que solo aparece
     tras ese error; el usuario puede elegir otra card o reintentar la misma.
3. **El switcher cambia de tenant de verdad** (`POST /auth/switch-tenant`), no solo el valor del
   `<select>`.
   - *Criterio de éxito*: test — tras elegir un tenant en el switcher, las queries dependientes de
     tenant se refetchean contra el tenant nuevo; si la llamada falla, la vista se queda con los
     datos (válidos) del tenant anterior — la caché solo se limpia tras éxito.
4. **Cualquier usuario con 2+ membresías `active` ve el switcher**, no solo Soporte.
   - *Criterio de éxito*: test — un usuario cliente con 2 membresías ve el switcher y puede cambiar
     de tenant igual que Soporte; con 1 sola membresía, nadie lo ve (comportamiento actual intacto).

## Alcance y fuera de alcance

### Dentro del alcance
- `auth-context.tsx`: `login()` devuelve la rama de selección en vez de un error fijo; nuevo método
  `selectTenant(identityToken, tenantId)`; nuevo método `switchTenant(tenantId)`; extracción del
  helper común (`completeSession`) que completa la sesión desde un `TokenResponse` — ya hace
  `GET /auth/me` y por tanto expone `availableTenants` (ver abajo) fresco cada vez que se llama
  (bootstrap, login, `selectTenant` y `switchTenant`), sin fetch adicional.
- `Me` gana `available_tenants: TenantChoice[]` (mis propias membresías `active` en tenants
  no-`disabled`, incluido el tenant activo actual — lo necesita el switcher para marcar la opción
  seleccionada) en vez de un endpoint nuevo — mismo patrón ya usado con `Me.active_tenant_id`
  (PR #6). `Me` ya se pide siempre, así que no añade una petición nueva al bootstrap, y evita crear
  un endpoint de auth desde un plan de frontend (el contrato lo define el backend). No toca
  `GET /admin/tenants`.
- Nuevo componente de UI para elegir tenant tras el login (cards, shadcn `Card`), integrado en el
  flujo de `login-form.tsx` sin ruta nueva (el `identity_token` no debe viajar por URL/historial);
  con estado pendiente (deshabilitada mientras resuelve) y guarda de concurrencia (una elección a la
  vez) — hallazgo de `scenario-coverage`.
- `tenant-context.tsx` / `TenantSwitcher`: `canSwitchTenant` pasa a calcularse como
  `availableTenants.length > 1` (ya no por capacidad `global`); `setActiveTenant` pasa a ser una
  operación real (async, con estado pendiente/error, deshabilitado mientras resuelve — hallazgo de
  `scenario-coverage`), respaldada por `switchTenant`. **`TenantSwitcher` deja de usar
  `use-tenants.ts`** (pasa a leer `availableTenants` de `auth-context`) — pero **`use-tenants.ts` NO
  se retira**: `frontend/src/features/admin/tenants-admin.tsx` importa el mismo hook para la
  pantalla de administración de tenants y debe seguir haciéndolo (corrección sobre lo que decía
  antes esta misma sección — verificado leyendo `tenants-admin.tsx`, hallazgo de
  `scenario-coverage`; mi verificación previa de `design-review` fue incompleta).
- `use-approvals.ts`: su `queryKey` no está escopada por tenant (a diferencia de `use-tickets.ts`/
  `use-analytics.ts`), pese a que `CU-FE-02` (RN-2) ya promete invalidar la cola de aprobaciones al
  cambiar de tenant. Hoy es inofensivo (el switch cosmético limpia toda la caché); en cuanto esta
  tarea lo haga real (`clear()` solo tras éxito), una respuesta tardía del tenant anterior podría
  pisar la vista del nuevo — se corrige aquí (hallazgo de `scenario-coverage`, decisión del owner).
- Docstrings de `subjectTenantId`/`activeTenantId` (`tenant-context.tsx`) y de `hasCapability`
  (`capabilities.ts`) actualizados: tras un switch real ambos son siempre iguales; se mantienen
  separados solo por la forma que ya asume `useCan`/`hasCapability`, no porque puedan diverger hoy
  (hallazgo de `design-review` §3).
- `completeSession` (helper de la tarea 01, reutilizado por `selectTenant`/`switchTenant`): si
  `GET /auth/me` falla justo tras obtener un `TokenResponse` válido, debe devolver `{ error }` y NO
  marcar `authenticated` — hoy el código no tiene esa rama (hallazgo de `scenario-coverage`,
  transversal a las tareas 01/03/04).
- Extensión de `CU-FE-01` (selección de tenant en login) y `CU-FE-02` (switch-tenant real +
  ampliación a cualquier usuario, no solo Soporte) con sus escenarios Gherkin, y de `spec.md`
  (`US-5`, `FR-011` reformulados sin restringir a Soporte) — `features.sdd` está `on`, la spec es la
  fuente del Gherkin de aceptación.

### Fuera de alcance
- El resto del contrato (`LoginTenantSelection`, `TenantChoice`, `/auth/select-tenant`,
  `/auth/switch-tenant`) ya existe y no se toca — solo se añade el campo `Me.available_tenants`
  descrito arriba.
- Backend real (doc-only en este package). Nota (hallazgo colateral de `design-review`, no de este
  plan): `backend/app/api/v1/routers/auth.py` ya tiene login/select-tenant/switch-tenant/me
  implementados de verdad — la premisa "doc-only" del `CLAUDE.md` raíz ya no describe el estado real
  del package. No se corrige aquí; es un hallazgo a valorar aparte con el owner.
- El gap ya conocido de `GET /admin/tenants` (exige `tenant.manage`; un Soporte global sin esa
  capacidad ve lista vacía) — es de la pantalla de administración, no del switcher, y no lo toca
  este plan.
- Refrescar `available_tenants` fuera de un login/select/switch/bootstrap: si alguien revoca o añade
  una membership a media sesión sin que haya un cambio de tenant de por medio, el switcher queda con
  la lista vieja hasta el siguiente de esos eventos o un reload — riesgo aceptado, documentado
  (hallazgo de `design-review` §4; el owner decidió no resolverlo ahora).
- Integración RTL de punta a punta encadenando login-con-selección (01) → uso posterior del
  switcher (04) en la misma sesión — cada pieza se testea aislada; no se añade un test de esa
  cadena completa (hallazgo de `scenario-coverage`, el owner no lo pidió).
- **Hipótesis sin reproducir** (`scenario-coverage`, no hecho confirmado): con la cookie de refresh
  httpOnly compartida por dominio, cambiar de tenant en una pestaña podría mover también a otra
  pestaña abierta en su siguiente refresh silencioso, sin que el usuario lo pidiera ahí. Anotado
  como riesgo conocido; el owner decidió no investigarlo en esta ronda de tareas.
- E2E (Playwright) del flujo multi-tenant — opcional por convención (`HOW-TO-START-A-TASK.md`), no
  entra en el gate por tarea.
- Nueva ruta/URL para la selección de tenant en el login (se descarta explícitamente: pasar el
  `identity_token` por query string/historial expondría un token de sesión ahí).
- Unificar `subjectTenantId`/`activeTenantId` en un solo campo de `TenantContextValue` — quedan como
  dos campos (ahora siempre iguales tras un switch real) para no romper `use-can.ts`/
  `capabilities.ts`, que ya dependen de esa forma exacta. Refactor futuro si molesta de verdad.

## Recursos externos

- `.claude/specs/backend/casos-de-uso/CU-BE-01-autenticacion-y-sesiones.md` — Gherkin completo del
  backend (login 2 pasos, select/switch-tenant, reuse-detection). Fuente de verdad de los códigos de
  error y el TTL/reusabilidad del `identity_token`.
- `.claude/specs/backend/data-model.md` líneas 30 y 75 — `user_tenant` es la membership compartida
  por cliente y Soporte; confirma que "a qué tenants puedo cambiar" es la misma query para cualquiera.
- `.claude/specs/frontend/casos-de-uso/CU-FE-01-login-y-sesion.md` (FR-003…FR-007) y
  `CU-FE-02-rbac-cliente-y-cambio-de-tenant.md` (FR-008…FR-011) — se amplían ambos.
- `.claude/specs/general/api-contract.yaml` líneas 31-116 (`/auth/login`, `/auth/select-tenant`,
  `/auth/switch-tenant`) y `Me`/`User`/`TenantChoice`/`LoginTenantSelection` en `components.schemas`.
- Decisión de la sesión previa (ya en `main`, PR #6): `Me.active_tenant_id` es el único campo del
  contrato con el tenant de la sesión activa; `auth-context.tsx` ya expone `sessionTenantId` a partir
  de él — esta base se reutiliza y se completa aquí.
- Decisiones de `grilling` (owner, 2026-08-21) y de `design-review` (owner, 2026-08-21) — ver
  Registro de cambios.

## Estimación global

- **Tareas totales**: 4 (ver lista abajo).
- **Esfuerzo estimado**: 4-5 sesiones (la tarea 04 creció tras `scenario-coverage`: fix de
  `use-approvals.ts`, estados pendientes/concurrencia, corrección de `use-tenants.ts`).
- **Recursos**: ninguno externo; todo mockeado vía MSW.

## Criterios de calidad y verificación

- TDD en las capas que aplican (unit para `auth-context`, RTL para los componentes, integración MSW
  donde corresponda) — ver tabla de niveles en `HOW-TO-START-A-TASK.md`.
- `pnpm --filter frontend lint` y `pnpm test` repo-wide en verde tras cada tarea.
- Gate de mutation testing (Stryker, `break: 80`) por tarea sobre los ficheros que toca.
- `pnpm gen:api:check` en verde tras la tarea 03 (regenerar == lo commiteado, incl. `Me.available_tenants`).
- Regresión explícita: los tests ya existentes de login single-tenant (`login-form.test.tsx`,
  `auth-context.test.tsx`) y de `tenant-switcher.test.tsx` siguen en verde — el caso de 1 tenant no
  cambia de comportamiento.

## Tasks

- [x] `frontend-multi-tenant-login-01` (P1) — `auth-context`: selección de tenant en login +
  `selectTenant` + helper común de sesión  · depends_on: —
- [x] `frontend-multi-tenant-login-02` (P1) — UI de cards (shadcn `Card`) de selección de tenant,
  integrada en el login  · depends_on: `frontend-multi-tenant-login-01`
- [x] `frontend-multi-tenant-login-03` (P2) — Contrato `Me.available_tenants` + `auth-context`:
  `availableTenants` expuesto + `switchTenant`  · depends_on: `frontend-multi-tenant-login-01`
- [x] `frontend-multi-tenant-login-04` (P2) — `tenant-context`/`TenantSwitcher`: switch real +
  visibilidad para cualquier usuario 2+ tenants + docs `CU-FE-02`/`spec.md`  ·
  depends_on: `frontend-multi-tenant-login-03`

## Registro de cambios del plan

- 2026-08-21: creado.
- 2026-08-21: `grilling` — decisiones:
  1. `subjectTenantId`/`activeTenantId` se mantienen como dos campos separados (no se colapsan).
  2. Error en `select-tenant`: alerta sobre la pantalla de cards, sin volver al login ni descartar
     las demás cards.
  3. Botón "Volver a iniciar sesión" en la pantalla de cards: solo visible tras un error.
  4. `switch-tenant` real: `queryClient.clear()` solo tras éxito (no optimista).
  5. `shadcn add card`: si trae dependencias npm nuevas, se pausa y se pregunta antes de instalar.
  6. Alcance ampliado: el switcher deja de ser solo-Soporte (ver Contexto) → añade
     `Me.available_tenants`, expuesto por `auth-context`, y una tarea 04 nueva (antes era la 03).
     Task 03 original (switch-tenant + wiring) se divide en 03 (contrato + auth-context) y 04
     (tenant-context/TenantSwitcher + docs).
- 2026-08-21: `design-review` (subagente fresco, sin `model` explícito — `models.design-review:
  claude-opus-4-8` en `task-pipeline.yml` es un id inválido, se avisó y se cayó a inherit).
  Veredicto: el plan no aguantaba sin cambios. Hallazgos y resolución:
  1. **[Bloqueante, corregido]** `GET /auth/my-tenants` como endpoint nuevo violaba la convención de
     propiedad del contrato (lo define el backend) y quedaba huérfano (sin tarea backend). Resuelto:
     se fusiona en `Me.available_tenants` — mismo patrón que `Me.active_tenant_id`, sin petición
     nueva en el bootstrap (`Me` ya se pide siempre). Corregido en Alcance/Recursos/Tasks arriba.
  2. **[Corregido]** Pedir la lista siempre, para todo usuario, por una historia P2 — resuelto por
     el mismo cambio del punto 1 (viene gratis dentro de `Me`).
  3. **[Corregido]** `subjectTenantId`/`activeTenantId` quedan siempre iguales tras un switch real,
     pero la documentación existente (`capabilities.ts`) seguía describiéndolos como divergentes.
     Resuelto: tarea 04 actualiza esos docstrings (no se colapsan los campos, solo se corrige lo que
     dicen sobre sí mismos).
  4. **[Riesgo aceptado, documentado]** `available_tenants` no se refresca fuera de un
     login/select/switch/bootstrap — anotado en Fuera de alcance, no se resuelve en este plan.
  5. **[Hallazgo colateral, no bloqueante]** `backend/` ya no es "doc-only" (routers reales en
     `auth.py`) pese a lo que dice el `CLAUDE.md` raíz — anotado en Fuera de alcance, a valorar
     aparte con el owner, no lo corrige este plan.
  Decisiones que resistieron el intento de tumbarlas (sin cambios): cards sin ruta nueva, alerta +
  botón "volver a login" solo tras error, `queryClient.clear()` solo tras éxito, no colapsar
  `subjectTenantId`/`activeTenantId` ahora, prioridades P1 (01/02) vs P2 (03/04).
- 2026-08-21: `scenario-coverage` (subagente fresco, `model: sonnet` — alias válido en
  `models.scenario-coverage`). Informe completo en las 4 tareas. Decisiones del owner:
  1. **[Corrección aplicada, no era una decisión]** `use-tenants.ts` NO se retira — solo
     `TenantSwitcher` deja de usarlo; `tenants-admin.tsx` lo sigue necesitando. Corregía una
     verificación mía incorrecta de `design-review`/plan original.
  2. **[Aplicado]** `completeSession` debe manejar el fallo de `GET /auth/me` tras tokens válidos
     (devuelve `{ error }`, no marca `authenticated`) — tarea 01, transversal a 03/04.
  3. **[Aplicado, decisión owner]** `use-approvals.ts` sin tenant en su `queryKey` (bug preexistente,
     expuesto por esta tarea): se arregla en la tarea 04, no en un plan aparte.
  4. **[Aplicado, decisión owner]** Estados pendientes + guardas de concurrencia (doble click,
     elegir dos tenants a la vez) en las tareas 02 y 04: se añaden.
  5. **[Anotado, decisión owner]** Hipótesis sin reproducir del refresh compartido entre pestañas:
     se deja anotada como riesgo conocido, sin investigar en esta ronda.
  6. **[Aplicado]** Escenarios menores incorporados sin discusión: botón "volver a login" (02),
     `<select>` revierte al tenant anterior si falla el switch (04), a11y de las cards (02),
     recarga de página en la pantalla de cards (02), `availableTenants` incluye el tenant activo
     actual (03).
  7. **[Descartado, decisión owner]** Integración RTL de punta a punta login→switcher: no se añade.
- 2026-08-21: **cierre del plan** — las 4 tareas `done`. Nota retro:
  - **Estimación vs. real**: 01 2h/3h, 02 2h/2h, 03 2h/2h, 04 4h/3h. Total estimado 10h, real 10h —
    la sobreestimación de la 04 (crecida tras `scenario-coverage`) compensó la subestimación de la 01
    (el ciclo TDD correcto — revertir, ver rojo, reaplicar — y el mutation-hardening de código
    preexistente en el mismo fichero costaron más que el cambio de producto en sí).
  - **Dependencia no vista**: el gate de mutation muta el FICHERO COMPLETO tocado por la tarea, no
    solo el diff — cada tarea tuvo que reforzar cobertura de código preexistente en los mismos
    ficheros (bootstrap, `onLogout`, `useAuth`/`useTenant` fuera de contexto, `useApprovals` sin
    tenant) que no estaba en su alcance literal. A tener en cuenta al estimar tareas futuras que
    tocan ficheros ya grandes/compartidos.
  - **Bug real encontrado por el propio TDD** (tarea 03): `completeSession` solo limpiaba
    `token`/`status` en su rama de error, no `user`/`sessionTenantId`/`capabilities`/
    `availableTenants` — inofensivo para `login`/`selectTenant` (llamados ya `unauthenticated`) pero
    dejaba estado a medias en `switchTenant` (llamado ya autenticado). El escenario de la tarea 03 lo
    expuso antes de llegar a producción.
  - **Deuda anotada, no resuelta** (fuera de alcance explícito del plan, ver arriba): refresh
    compartido entre pestañas al cambiar de tenant (hipótesis sin reproducir); `GET /admin/tenants`
    con Soporte sin `tenant.manage`; `backend/` ya no es doc-only pese al `CLAUDE.md` raíz; `FR-028`
    de `spec.md` es un requisito EARS compuesto (AVISO de `sdd-lint`, no bloqueante).
  - Rama `plan/frontend/multi-tenant-login` con 4 commits (uno por tarea). PR pendiente de que el
    owner decida abrirla.
