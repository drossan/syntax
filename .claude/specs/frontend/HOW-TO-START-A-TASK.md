# Cómo arrancar una sesión nueva para una tarea — `frontend`

> Package **`frontend`** de Syntax: **Next.js 16 (App Router) + TypeScript estricto +
> Tailwind v4 + shadcn/ui**, con **Spec-Driven Design + TDD**. Código real, tests desde los
> escenarios Gherkin. Referenciado desde el `CLAUDE.md` raíz. Flujo canónico:
> `docs/guides/task-lifecycle.md`. El plan y las tareas salen de `/plan-task`.

> ## 🚦 GATE TDD — IMPERATIVO, NO NEGOCIABLE (preset `full`)
>
> **Antes de tocar una línea de código de implementación:**
>
> 1. La tarea está en `.claude/tasks/active/frontend/<task-id>.md` con `status: active` y **todas**
>    sus `depends_on` en `done`. Si no → **PARAR y avisar**.
> 2. Estamos en la rama del plan `plan/frontend/<name-plan>` (nunca en integración ni `main`).
>    Solo **una** tarea `active` por plan (comparten rama).
> 3. **Test rojo ANTES de la implementación** (Red). Los tests salen **1:1 de los escenarios
>    Gherkin** de `## Scenarios (Gherkin)` (cada `Then` es un assert). Niveles de test por artefacto:
>
>    | Artefacto | Nivel de test esperado |
>    |---|---|
>    | Componente UI / de feature | **RTL** (React Testing Library): comportamiento observable del usuario, no detalles de implementación |
>    | Hook / `lib/` (cliente API, rbac, utils) | **unit** (Vitest) |
>    | Página / data-fetching / route handler | **integración con MSW** (mock del contrato de API) |
>    | Flujo crítico (login → ticket → draft IA → aprobación) | **e2e opcional** (Playwright), fuera del gate por tarea |
>
>    Sin test rojo previo NO se escribe código de producción. **Carve-out (design-review M4)**: el
>    scaffold (tarea 01, sin comportamiento que testear) usa un **smoke de arranque** (la app monta, MSW
>    intercepta, un test trivial en verde) en lugar del ciclo rojo-primero.
>
>    Además: **estados error/loading/empty y a11y básica (roles, foco, teclado) van en la DoD de CADA
>    feature** (no en un barrido final); el pase `axe` amplio se hace en navegador real (Playwright).
> 4. Green (mínimo para pasar) → Refactor (con tests en verde). **Reglas de arquitectura**:
>    - **TS estricto**: `strict` + `noUncheckedIndexedAccess`; **`any` prohibido**.
>    - **App client-rendered** (design-review I1): el access token vive en memoria → el **data-fetching
      autenticado es client-side** (TanStack Query + cliente tipado); **Server Components solo para *chrome*
      estático**. El `middleware.ts` es **redirect UX** (solo ve la cookie refresh), **no control de seguridad**.
>    - Capa `features/<dominio>/` (hooks + api + components); **sin `fetch` suelto** en componentes:
>      todo dato de servidor pasa por **TanStack Query** + el **cliente API tipado** (derivado del
>      contrato, `.claude/specs/general/api-contract.md`).
>    - **RBAC y tenant** aplicados en cliente (menús/rutas/acciones) asumiendo que el server también
>      los aplica; el filtro de **visibilidad de mensajes** (`public`/`internal`/`developer`) nunca
>      muestra al cliente lo que es Syntax-only.
>    - No dupliques componentes/lógica (`.claude/specs/general/coding-standards.md`).
> 5. Cierre: **toda** la DoD en verde, incl. documentación en tres capas (TSDoc en símbolos públicos,
>    doc técnica, session log), `pnpm --filter frontend lint` y `pnpm test` repo-wide en verde, y el
>    **gate de mutation** (Stryker, `break: 80`) sobre los ficheros tocados.
> 6. **Gate `fact-checker`** (no-negociable): tras mutation y antes de commit/resumen. `INCORRECTO`
>    bloquea; `NO VERIFICABLE` = aviso a reconocer; `VERIFICADO` pasa.

## Prompt de arranque (copia y pega)

```
Voy a ejecutar la tarea <task-id> del plan <name-plan> (frontend).

Lee en este orden y repórtame en 3-4 líneas el plan que vas a seguir:
1. `.claude/specs/frontend/HOW-TO-START-A-TASK.md` (este fichero).
2. `docs/guides/task-lifecycle.md` (flujo canónico).
3. `.claude/plans/active/frontend/<name-plan>.md` (contexto, objetivos, orden, dependencias).
4. Las specs aplicables (contrato de API, rbac, data-model, coding-standards) — ver tabla abajo.
5. `.claude/tasks/active/frontend/<task-id>.md` + `.claude/context/frontend/<task-id>.md`.

Ejecuta con el ciclo TDD. REGLAS ESTRICTAS:
- GATE TDD: status active + depends_on done; rama del plan; test rojo ANTES del código.
- TS estricto (`any` prohibido); Server/Client Components correctos; datos vía TanStack Query +
  cliente API tipado; RBAC/tenant/visibilidad respetados; sin duplicar.
- Commits `<task-id>: <conventional commit>` en la rama del plan.
- Docs (3 capas) antes de declarar hecho. Lint/format/typecheck en verde. Cero secretos.
Al terminar: `pnpm --filter frontend lint` + `pnpm test` repo-wide en verde; gate mutation;
`fact-checker`; cerrar session log; mover task a completed/ + `[x]` en el plan; siguiente tarea.
```

## Specs aplicables (paso 3 del gate)

| Si la tarea crea / toca… | Lee la spec |
|---|---|
| **Toda tarea (SDD)** | `.claude/specs/frontend/spec.md` (requisitos EARS) + `.claude/specs/frontend/casos-de-uso/` (Gherkin, **único hogar**) |
| Cliente API / tipos / mocks MSW | `.claude/specs/general/api-contract.md` |
| Rutas/menús/acciones por rol o tenant | `.claude/specs/backend/rbac.md` |
| Formas de ticket/mensaje/aprobación (shape de datos) | `.claude/specs/backend/data-model.md` |
| **Toda feature (transversal)** | `.claude/specs/frontend/cross-cutting.md` (anti-XSS, i18n fecha/tz, ciclo de caché, estados error/loading/empty) |
| Cualquier código (transversal) | `.claude/specs/general/coding-standards.md` |
| Cualquier test (transversal) | `.claude/specs/general/testing.md` |

> **SDD activo** (`features.sdd: true`). El `## Scenarios (Gherkin)` de una tarea **nueva** **enlaza** al
> caso de uso correspondiente (`casos-de-uso/CU-FE-*.md`) en vez de copiar los escenarios (los CU son el
> único hogar del Gherkin de aceptación). Las tareas **ya completadas** con Gherkin inline **no** se migran.
> Al cierre corre el gate **`/sdd-lint`** (tras `mutation`, antes de `fact-checker`): un ERROR bloquea.

## Reglas anti-context-bloat

- `grep -n` en vez de leer ficheros completos; delegar barridos amplios a `Explore`.
- `2>&1 | tail -N` en test/build; no re-leer un fichero recién editado solo para verificar.
