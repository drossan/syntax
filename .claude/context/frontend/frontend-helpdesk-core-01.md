# Session log — `frontend-helpdesk-core-01` — Scaffold Next.js 16 + tooling

> Append-only. Registro canónico de la tarea (task-lifecycle §Cerrar una tarea).

## 2026-08-13 — Arranque

- **Plan** `frontend/helpdesk-core` movido `pending → active`; rama `plan/frontend/helpdesk-core`
  creada desde `dev` (working tree limpio; repo sin remoto → `git pull` N/A).
- **Tarea 01** movida `pending → active`. `depends_on: []` → sin bloqueos.
- **Blocker de toolchain resuelto (precondición, fuera del alcance literal de la tarea):** la raíz
  declaraba `"packageManager": "pnpm@9"` — corepack 0.35.0 lo rechaza («expected a semver version»),
  dejando **toda** la cadena pnpm inoperativa. Fijado a `"pnpm@9.15.9"` (último 9.x). Verificado:
  `pnpm -v` → `9.15.9`.
- **Versiones confirmadas vía registry:** `next@16.3.0` es `latest` (dist-tag) → el "Next.js 16" del
  plan es real y disponible. Node local `v20.19.1`.
- Carve-out design-review M4: el scaffold se valida con **smoke de arranque** (app monta, MSW
  intercepta, lint+typecheck verde), no con ciclo rojo-primero.

## 2026-08-13 — Scaffold ejecutado

### Qué se hizo

- **Base** `create-next-app@16` no interactivo: Next **16.3.0** + React **19.2.8**, App Router,
  TS estricto, Tailwind **v4** (`@tailwindcss/postcss`), ESLint 9 (flat config), `src-dir`, alias `@/*`.
- **tsconfig**: añadido `noUncheckedIndexedAccess: true` (junto a `strict`) → sin `any`.
- **shadcn/ui** `init -d`: estilo `base-nova` (primitivas `@base-ui/react`), `components.json`,
  `src/components/ui/button.tsx`, `src/lib/utils.ts` (`cn`), variables en `globals.css`.
- **Libs de dominio**: `@tanstack/react-query`, `@tanstack/react-table`, `react-hook-form`,
  `@hookform/resolvers`, `zod`, `next-intl`.
- **Harness de test**: `vitest` + `@vitejs/plugin-react` + `jsdom` + Testing Library (react/dom/
  jest-dom/user-event) + `msw`; `@stryker-mutator/{core,vitest-runner}`; `@playwright/test`;
  `prettier`. `vitest.config.ts` (env jsdom, alias `@`, setup, e2e excluido).
- **MSW**: `src/mocks/{handlers,server,browser}.ts` + worker `public/mockServiceWorker.js`
  (`msw init`). Handler de humo `GET http://localhost:8000/__smoke → {ok:true}`.
- **Providers**: `src/app/providers.tsx` (client) con `QueryClientProvider` + `NextIntlClientProvider`
  (locale `es` por defecto); cableado en `layout.tsx` (`lang="es"`, título de la app).
- **i18n**: `messages/{es,en}.json` (semilla).
- **Configs**: `stryker.config.json` (runner vitest, `break: 80`), `playwright.config.ts` (testDir
  `e2e`, webServer `pnpm dev`), `.prettierrc.json`/`.prettierignore`, `.env.local.example`.
- **Estructura**: `src/{app/(auth),app/(app),components/ui,features,lib,mocks,types,test}` + `e2e/`
  (`.gitkeep` en las vacías).
- **Docs**: `README.md` del package reescrito. `AGENTS.md`/`CLAUDE.md` los gestiona `next dev/build`
  (avisan de breaking changes de Next 16) → conservados, no editados.

### Decisiones técnicas (y porqué)

- **`plugin-react@5` + `vite@7`, NO `plugin-react@6`**: la v6 es la variante *rolldown/react-compiler*
  (peers `@rolldown/plugin-babel` + `babel-plugin-react-compiler`) y exige `vite@8`. Innecesaria para
  un harness de test → set estándar babel + vite 7 (satisface el peer `^6||^7||^8` de vitest 4).
- **`jsdom@26`, NO `jsdom@30`**: jsdom 30 arrastra `undici@8.9`, que llama a
  `webidl.util.markAsUncloneable` inexistente en Node 20.19.1 → Vitest no arrancaba (error reproducido).
  jsdom 26 no depende de undici; el `fetch` del test lo provee el global de Node, que MSW intercepta.
- **`vite-tsconfig-paths` eliminado**: alias `@/*` resuelto a mano en `vitest.config.ts` (una dep menos).
- next-intl solo como **provider cliente** (sin plugin de `next.config` ni routing por locale): el
  routing i18n y el switch de idioma son de tareas 06/20.

### Verificación (comandos corridos en esta sesión)

- `pnpm --filter frontend test` (vitest run) → **2 passed (2)** (smoke home RTL + smoke MSW intercept).
- `pnpm --filter frontend exec tsc --noEmit` → **exit 0**.
- `pnpm --filter frontend exec eslint` → **0 errores, 0 warnings** (worker de MSW ignorado en eslint).
- `pnpm --filter frontend exec prettier --check .` → **All matched files use Prettier code style**.
- `pnpm --filter frontend exec next build` → **Compiled successfully**, TypeScript OK, páginas
  estáticas generadas, sin errores.

### Cierre

- **Gate `fact-checker`** (subagente fresco, sonnet): **18/18 VERIFICADO**, 0 INCORRECTO, 0 NO
  VERIFICABLE → pasa.
- Tarea `active → done` (`actual: 3h`), movida a `.claude/tasks/completed/frontend/`. Checkbox `[x]`
  en el plan. Commit `frontend-helpdesk-core-01: …` en `plan/frontend/helpdesk-core`.
- **Follow-ups / notas para tareas siguientes:**
  - Versiones a vigilar al usarlas: `@tanstack/react-table@9.x` (tarea 07) y `lucide-react@1.x` —
    majors nuevos; validar imports al integrarlas.
  - jsdom pineado a 26 (Node 20). Si se sube Node a 22+, se puede revisar jsdom 30.
  - next-intl: falta el plugin de `next.config` + routing por locale (tareas 06/20).
  - Toolchain: `packageManager` de la raíz fijado a `pnpm@9.15.9` (era `pnpm@9`, inválido para corepack).
