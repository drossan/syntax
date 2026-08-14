# Estándar de testing (transversal)

> Convenciones de test del repo. Aplica **hoy** al package `frontend` (TDD real). El `backend` es
> **doc-only** ([[../adr/0012-backend-fase-1-doc-only-fase-2-diferida]]): `stack.packages.backend.test-runner: none`,
> sin tests hasta que haya código real (§4). Referenciada desde los `HOW-TO-START-A-TASK.md`. No duplica el
> flujo canónico (`docs/guides/task-lifecycle.md`) ni las políticas de `cross-cutting.md`: las **enlaza**.

## 1. TDD desde el escenario (fuente 1:1)

- **Red → Green → Refactor**: test que falla **antes** de la implementación. Sin test rojo previo no se
  escribe código de producción (**carve-out** del scaffold: smoke de arranque, design-review M4).
- Cada test sale **1:1 de un escenario Gherkin** (cada `Then` es un assert). Con `features.sdd` activo, los
  escenarios viven en los **casos de uso** (`casos-de-uso/CU-*.md`); una tarea nueva **enlaza** a su CU.
- Se testea **comportamiento observable**, no detalles de implementación (un refactor no rompe el test).

## 2. Niveles de test por artefacto (frontend)

| Artefacto | Nivel |
|---|---|
| Componente UI / de feature | **RTL** (comportamiento del usuario, no internals) |
| Hook / `lib/` (cliente API, rbac, utils) | **unit** (Vitest) |
| Página / data-fetching / route handler | **integración con MSW** (mock del contrato) |
| Flujo crítico (login → ticket → draft IA → aprobación) | **e2e** (Playwright) — **fuera** del gate por tarea |

- **Estados error/loading/empty** por-feature con **aserción real** (no solo render) —
  [`../frontend/cross-cutting.md`](../frontend/cross-cutting.md) §4.
- **a11y básica** (roles, foco, teclado) en la DoD de cada feature; auditoría `axe` amplia en navegador real.
- **Anti-XSS**: por cada superficie que renderice contenido externo, test "marcado tipo script se muestra
  como texto y no se ejecuta" (cross-cutting §1).

## 3. Gates de cierre (por tarea)

- **Todos los tests en verde**: `pnpm --filter frontend test` (o repo-wide `pnpm test`).
- **Lint/format/typecheck**: `pnpm --filter frontend lint`; TS estricto, `any` prohibido.
- **Mutation gate** (Stryker, `break: 80`) sobre los ficheros tocados: un survivor por debajo del umbral =
  aserción/escenario que falta (a menudo un `Then` sin assert real) → reforzar hasta matarlo. Ver `/mutation`.
- **Conformidad de contrato** en CI (`gen:api:check`): tipos+mocks regeneran limpio; falla ante drift
  ([[../adr/0002-contrato-openapi-first]]).
- **`/sdd-lint`** (SDD): valida los artefactos (spec EARS · CU Gherkin · ADR MADR) antes de `fact-checker`.

## 4. Backend (cuando pase a código real)

Hoy sin tests (doc-only). Al implementarlo: ajustar `.claude/task-pipeline.yml` (`stack.packages.backend`
→ `test-runner: pytest`, `mutation-tool: mutmut` u otra) y endurecer su HOW-TO con los niveles:

- **Dominio** (servicios/puertos) → **unit** con mocks de puertos (sin infra).
- **Repos / endpoints** → **integración** contra Postgres+pgvector en Docker.
- **Adapters** (LLM/embeddings/storage) → **suite de contrato** del puerto.
- **Aislamiento RLS** ([[../adr/0006-aislamiento-multi-tenant-app-level-mas-rls]]) y **HITL/checkpointer**
  ([[../adr/0007-hitl-asincrono-postgressaver-checkpointer]]) → **tests de integración obligatorios** (el
  footgun `SET app.tenant_id` en pool async y el resume tras reinicio no se verifican con unit tests).

## 5. Determinismo

- Sin dependencia de reloj/orden reales: fechas/relojes inyectados (puerto `clock`), datos de fixture.
- El orden determinista del contrato se **asserta** (no se asume): tickets `-updated_at`, `/approvals`
  `sla_due,confidence`, etc.
