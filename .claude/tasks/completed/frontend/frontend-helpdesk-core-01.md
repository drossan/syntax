---
id: frontend-helpdesk-core-01
package: frontend
plan: helpdesk-core
status: done
priority: 1
depends_on: []
estimate: 3h
actual: 3h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# Scaffold Next.js 16 + tooling

## Description

Crear el proyecto `frontend/` (Next 16 App Router, TS estricto) y todo el tooling: Tailwind v4 + shadcn,
Vitest+RTL+MSW, Stryker, Playwright (config), RHF/Zod/TanStack Query/TanStack Table, next-intl, ESLint/
Prettier y la estructura de carpetas.

## Spec

- `frontend/` con Next 16 App Router, `tsconfig` **estricto** (`strict` + `noUncheckedIndexedAccess`).
- Tailwind v4 + shadcn (`components.json`, `src/components/ui/`), tema/dark base.
- Test harness: Vitest + RTL + MSW (server de mocks), Stryker (`break: 80`), Playwright (`playwright.config`).
- Libs: TanStack Query (provider), RHF, Zod, TanStack Table, next-intl (provider + locales `es`/`en`).
- Estructura `src/{app,(auth),(app),components/ui,features,lib,mocks,types,test}`; `.env.local.example`.

## Fuera de alcance

- Lógica de features (tareas siguientes). BFF de Next (descartado). Backend real.

## Scenarios (Gherkin)

<!-- Carve-out (design-review M4): el scaffold no tiene comportamiento de dominio; se verifica con un
     smoke de arranque en lugar del ciclo rojo-primero. -->
```gherkin
Feature: Arranque de la aplicación

  Scenario: La app monta con el harness de test y mocks
    Given un proyecto Next 16 recién scaffoldeado con el tooling configurado
    When se ejecuta la suite de smoke
    Then la app monta sin error, MSW intercepta una petición de prueba, y `pnpm --filter frontend lint` y typecheck pasan en verde
```

## Provides

- Proyecto `frontend/` con estructura, tooling de test (Vitest/RTL/MSW/Stryker/Playwright) y libs base.
  Todas las tareas siguientes asumen este scaffold.

## Definition of Done

- [x] Smoke de arranque en verde (carve-out del scaffold); `pnpm --filter frontend lint` + typecheck OK.
- [x] Estructura, Tailwind+shadcn, harness de test y libs configurados según Spec.
- [x] `Provides` disponible para las dependientes.
- [x] Gate de `fact-checker` superado (18/18 VERIFICADO).
- [x] Docs: README del package + session log en `.claude/context/frontend/frontend-helpdesk-core-01.md`.
