# `frontend` — Helpdesk Syntax

Frontend del helpdesk con IA generativa de Syntax. **Next.js 16 (App Router) + TypeScript
estricto + Tailwind v4 + shadcn/ui**, desarrollado con **Spec-Driven Design + TDD** contra el
**contrato de API** del backend (OpenAPI 3.1) vía cliente tipado + mocks MSW.

Arquitectura fijada en design-review: app **client-rendered** (el access token vive en memoria →
data-fetching autenticado client-side con TanStack Query); los Server Components son solo _chrome_
estático; `middleware.ts` hace redirect UX por cookie (no es control de seguridad).

## Stack

| Área          | Herramienta                                                            |
| ------------- | ---------------------------------------------------------------------- |
| Framework     | Next.js 16 (App Router), React 19                                      |
| Lenguaje      | TypeScript estricto (`strict` + `noUncheckedIndexedAccess`, sin `any`) |
| Estilos       | Tailwind v4 + shadcn/ui (`components/ui`)                              |
| Data-fetching | TanStack Query + cliente API tipado                                    |
| Formularios   | React Hook Form + Zod                                                  |
| Tablas        | TanStack Table                                                         |
| i18n          | next-intl (`es` / `en`)                                                |
| Tests         | Vitest + Testing Library + MSW · Stryker (mutation) · Playwright (e2e) |

## Scripts

```bash
pnpm --filter frontend dev          # servidor de desarrollo
pnpm --filter frontend build        # build de producción
pnpm --filter frontend lint         # ESLint
pnpm --filter frontend typecheck    # tsc --noEmit
pnpm --filter frontend test         # Vitest (una pasada)
pnpm --filter frontend test:watch   # Vitest en watch
pnpm --filter frontend mutation     # gate de mutation (Stryker, break 80)
pnpm --filter frontend e2e          # smokes e2e de Playwright
pnpm --filter frontend format       # Prettier --write
```

Desde la raíz del monorepo, `pnpm lint` / `pnpm test` / `pnpm typecheck` delegan en este package.

## Estructura

```
src/
  app/            # App Router. (auth) y (app) son route groups; providers.tsx = client providers
  components/ui/  # componentes de shadcn/ui
  features/       # capa por dominio: hooks + api + components (sin fetch suelto)
  lib/            # utilidades (cliente API tipado, rbac, cn, …)
  mocks/          # MSW: handlers + server (Node/tests) + browser (worker de dev)
  test/           # setup de Vitest
  types/          # tipos compartidos (incl. los generados del contrato)
messages/         # catálogos de i18n (es.json, en.json)
e2e/              # specs de Playwright
```

## Configuración

Copia `.env.local.example` a `.env.local`. En tests, MSW arranca siempre desde el server de Node.

> **Next.js 16 trae breaking changes** respecto a versiones anteriores: consulta
> `node_modules/next/dist/docs/` (ver `AGENTS.md`, generado por `next dev`) antes de escribir código
> que dependa de APIs del framework.

## Flujo de trabajo

Spec-Driven Design + TDD orquestado por `task-pipeline`. Antes de tocar código, lee
`.claude/specs/frontend/HOW-TO-START-A-TASK.md` y `docs/guides/task-lifecycle.md`. Cada escenario
Gherkin de la tarea es la fuente 1:1 de un test. Cierre de tarea: lint + typecheck + tests verdes,
gate de mutation (Stryker, break 80) y gate de `fact-checker`.
