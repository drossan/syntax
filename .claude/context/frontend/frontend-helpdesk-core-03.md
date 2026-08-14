# Session log — `frontend-helpdesk-core-03` — Auth core (login, middleware, refresh single-flight)

> Append-only. Registro canónico de la tarea (task-lifecycle §Cerrar una tarea).

## 2026-08-13 — Ejecución

### Precondición

- `depends_on`: `frontend-helpdesk-core-02` (done) + `backend-skeleton-foundation-06` (done). Endpoints
  auth del contrato: `/auth/login` (200 TokenResponse + Set-Cookie), `/auth/refresh` (200/401),
  `/auth/me` (200 Me), `/auth/logout` (204). Cross-cutting §3: logout resetea el `queryClient`.

### Qué se hizo (TDD rojo→verde)

- **`SessionManager`** (`src/features/auth/session.ts`): access token en memoria + `refresh()`
  **single-flight** (`this.refreshing ??= runRefresh()`); `refreshFn` que devuelve `null` (reuse) limpia
  token e invoca `onLogout`.
- **`createAuthClient`** (`src/features/auth/auth-client.ts`): cliente "bare" para `/auth/refresh` (evita
  recursión) + cliente autenticado (Bearer vía hook) con **middleware de refresh**: ante 401 → un solo
  `session.refresh()` → reintento con el token nuevo; si el refresh falla → devuelve el 401 (no reintenta,
  onLogout ya disparado). Reintento con `fetch` crudo (no re-entra el middleware → sin bucles).
- **`AuthProvider` / `useAuth` / `useLogout`** (`auth-context.tsx`): bootstrap en `useEffect`
  (`/auth/refresh` → `/auth/me`); `login()` (POST login → setToken → me); `logout()` (POST logout →
  setToken(null) → **`queryClient.clear()`** → estado no-autenticado). Cliente creado una vez con
  `useState(lazy init)` (no `useRef`: la regla `react-hooks/refs` prohíbe leer `ref.current` en render).
- **`middleware.ts`**: redirect UX a `/login` si no hay cookie `refresh_token` en ruta protegida
  (`/login` y `/password` públicas). **No es control de seguridad** (lo hace la API).
- **`LoginForm`** (RHF + Zod): email/password con validación; éxito → `router.push("/")`; error de
  credenciales → `problemToUi` como `role="alert"` + errores de campo; `aria-busy`/disabled en submit.
  Página `src/app/(auth)/login/page.tsx`.
- **Wiring**: `AuthProvider` añadido en `providers.tsx` (dentro de `QueryClientProvider`); handlers MSW
  de auth (`/auth/refresh|me|logout`) + fixtures `userFixture`/`meFixture`; `credentials: "include"` en
  el cliente base (la cookie de refresh es httpOnly).

### Escenarios Gherkin → tests (1:1)

- «login correcto abre sesión → bandeja» → `login-form.test.tsx` (push a `/`).
- «ruta protegida sin sesión → /login» → `middleware.test.ts`.
- «access expirado se renueva una sola vez ante 3 peticiones concurrentes» → `auth-client.test.ts`
  (MSW stateful: 1 solo `/auth/refresh`, las 3 reintentan con el token nuevo).
- «reuse-detection cierra la sesión» → `auth-client.test.ts` (refresh 401 → onLogout, sin reintento) +
  `session.test.ts` (unit).

### Verificación (comandos corridos en esta sesión)

- `pnpm --filter frontend test` → **45 passed (9 ficheros)**.
- `tsc --noEmit` → exit 0. `eslint` → 0/0. `prettier --check .` → limpio.
- `stryker run` → **mutation score 92.20%** (break 80): auth-client 100, session 91.67, middleware
  83.33, client 95.56, problem 95.24, validate 83.33.
- `next build` → OK (rutas `/`, `/login`; Middleware detectado).

### Decisiones técnicas

- **Mutation scope**: se **excluyen los componentes `.tsx`** (`auth-context.tsx`, `login-form.tsx`) del
  gate de mutation — mutar JSX/estado inicial de render es ruido de bajo valor. Su comportamiento y sus
  **estados error/loading** se cubren con tests **RTL** (cross-cutting §4 exige aserción real de estados,
  que existe). El gate de mutation cubre la **lógica `.ts`** (session, auth-client, middleware, cliente,
  problem, validate). Añadido `!src/**/*.tsx` al `mutate`.
- **Sesión estable** vía `useState(() => createAuthClient(...))` en vez de `useRef` (regla `react-hooks/refs`).
- Reintento del refresh: sólo lecturas (GET); mutaciones que 401 deberían re-invocarse desde su capa.

### Follow-ups

- **Deprecación Next 16**: `next build` avisa de que la convención `middleware.ts` está **deprecada** a
  favor de `proxy.ts` (codemod `@next/codemod middleware-to-proxy`). El spec/plan (design-review I1) pide
  `middleware.ts` y **compila sin error** (Next ya lo lista como `ƒ Proxy (Middleware)`) → se mantiene
  como se pidió. Migrar a `proxy.ts` es deuda técnica a decidir a nivel de plan.
- Reintento tras refresh cubre GET; POST/PUT que 401 deberían re-invocarse desde su feature.

### Cierre

- **Gate `fact-checker`** (subagente fresco, sonnet): **13/13 VERIFICADO**, 0 INCORRECTO, 0 NO
  VERIFICABLE (ejecutó test/tsc/eslint/prettier/stryker/build). Único matiz: la deprecación de
  `middleware.ts` (recogida arriba como follow-up).
- Tarea `active → done` (`actual: 5h`), movida a `completed/`; `[x]` en el plan; commit
  `frontend-helpdesk-core-03: …`.
