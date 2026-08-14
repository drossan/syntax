# Session log — `frontend-helpdesk-core-02` — Cliente API tipado + MSW validado + util de errores

> Append-only. Registro canónico de la tarea (task-lifecycle §Cerrar una tarea).

## 2026-08-13 — Ejecución

### Precondición verificada

- `depends_on`: `frontend-helpdesk-core-01` (done) + `backend-skeleton-foundation-06` (done).
- **Precondición dura satisfecha**: `.claude/specs/general/api-contract.yaml` es un **OpenAPI 3.1.0 real**
  (1166 líneas; 38 schemas; paths auth/tickets/messages/ai-flow/kb/admin/analytics/notifications;
  envelope `Problem` RFC 9457 con `errors[]`; base `/api/v1`). El codegen corre contra él.

### Decisión de dependencias (consultada al owner)

Stack de la capa de contrato elegido por el owner: **ecosistema openapi-*** →
`openapi-typescript` (tipos, ya en Spec) + `openapi-fetch` (cliente tipado) + `openapi-msw` (handlers
tipados) + `ajv` (validación runtime). **Plumbing adicional declarado**: `yaml` (convierte el contrato
`.yaml` a JSON que consume ajv en runtime; los tipos TS son solo compile-time).

### Qué se hizo (TDD rojo→verde)

- **Codegen** `pnpm gen:api`: `openapi-typescript` → `src/types/api.ts` (1968 líneas) **+**
  `scripts/contract-to-json.mjs` (yaml→`src/mocks/contract/openapi.json`, 38 schemas). Determinista
  (regenerar no produce diff). **Gate de conformidad** `pnpm gen:api:check` = `gen:api` + `git diff
  --exit-code` (falla si el contrato cambia sin regenerar tipos/JSON).
- **Cliente** `src/lib/api/client.ts` (`createApiClient(hooks, baseUrl)`, openapi-fetch tipado con
  `paths`): header `Authorization: Bearer` (si hay token); **hook 401** `onUnauthorized` (enganche del
  refresh single-flight de la task 03); **429** con `fetch` que reintenta con **backoff** (respeta
  `Retry-After`, si no exponencial `200·2^intento`), **clona la Request** por intento (mutaciones), y
  avisa vía `onRateLimit`. `delay`/`maxRetries` inyectables (tests deterministas).
- **Util** `src/lib/api/problem.ts` `problemToUi(problem, translate?)` → `{ toast{title,detail},
  fieldErrors }`: `errors[]` (con field+message) → fieldErrors RHF; title/detail localizados por el
  servidor (fallback `translate("errors.generic")` si title vacío).
- **MSW tipado** `src/mocks/handlers.ts` con `createOpenApiHttp<paths>` (`response(code).json` valida el
  body contra el schema **en compile-time**) + `src/mocks/fixtures.ts`. Handlers base: `POST
  /auth/login`, `GET /tickets`, `POST /tickets`.
- **Validación runtime** `src/mocks/contract/validate.ts` `validateResponse(schema, data)` con
  `Ajv2020` (OpenAPI 3.1 = JSON Schema 2020-12) sobre `openapi.json`; `strict:false`,
  `validateFormats:false` (sin ajv-formats los formatos son no-op).
- Retirado el smoke `/__smoke` y su test (superados por los handlers reales + client tests).

### Escenarios Gherkin → tests (1:1)

- «tipos generados / conformidad pasa» → `validate.test.ts` (fixtures conformes + `gen:api:check`).
- «mock que no cumple → validación falla señalando el recurso» → `validate.test.ts` (enum inválido,
  tipo primitivo, allErrors, mensaje propio).
- «problem+json → fieldErrors + toast» → `problem.test.ts`.
- «cliente según status 200/401/429/422» + token/backoff → `client.test.ts` (14 casos).

### Verificación (comandos corridos en esta sesión)

- `pnpm --filter frontend test` → **28 passed (28)** (4 ficheros).
- `pnpm --filter frontend exec tsc --noEmit` → **exit 0**.
- `pnpm --filter frontend exec eslint` → **0/0** (ignorados `.stryker-tmp/**`, `reports/**`).
- `pnpm --filter frontend exec prettier --check .` → limpio.
- `pnpm --filter frontend exec stryker run` → **mutation score 92.13%** (break 80): client 95.45,
  problem 95.24, validate 83.33. Survivors restantes = equivalentes/cosméticos (cache, `.trim()`,
  `?? []` con datos presentes, arrow de delay por defecto).
- `pnpm gen:api` idempotente (sin diff al regenerar).

### Decisiones técnicas

- **`vite-tsconfig-paths` no**: alias `@` a mano (heredado de task 01).
- **`.stryker-tmp/` y `reports/`**: añadidos a `.gitignore`/eslint/prettier (un sandbox de Stryker
  quedó de una ejecución que crasheó y ensuciaba lint/format).
- **Fix del runner de Stryker**: `plugins: ["@stryker-mutator/vitest-runner"]` explícito en
  `stryker.config.json` (pnpm no lo auto-cargaba por el glob → "no TestRunner plugins were loaded").
- **`mutate` de Stryker** acotado a `src/lib/**` + `src/features/**` + `validate.ts`; excluidos
  tests, `utils.ts` (shadcn), `.d.ts`.

### Follow-ups

- El **single-flight** real del 401 y la reuse-detection→logout son de `frontend-helpdesk-core-03`
  (este cliente solo expone el hook `onUnauthorized`).
- Handlers MSW por recurso se ampliarán en cada tarea de feature (la superficie tipada ya está).

### Cierre

- **Gate `fact-checker`** (subagente fresco, sonnet): 13/14 VERIFICADO + **1 defecto real cazado** en
  el gate de conformidad → **corregido en la sesión**:
  - **Defecto**: `pnpm gen:api:check` fallaba (exit 1) en checkout limpio por **drift de formato** (no
    de contenido): `openapi-typescript` emite `api.ts` a 4 espacios y `contract-to-json.mjs` emite
    arrays JSON multilínea, pero los ficheros commiteados estaban prettificados (2 esp./inline) porque
    `prettier --write .` los reformateó. Regenerar producía crudo ≠ commiteado → el gate rompía.
  - **Fix**: `gen:api` ahora prettifica su salida (`... && prettier --write src/types/api.ts
    src/mocks/contract/openapi.json`). Verificado: `pnpm gen:api:check` → **exit 0** contra el estado
    commiteado; salida generada byte-idéntica a la versionada.
  - Resto de afirmaciones (28 tests, tsc 0, eslint 0, prettier OK, stryker 92.13%) VERIFICADAS por el
    subagente ejecutando cada comando.
- Tarea `active → done` (`actual: 5h`), movida a `completed/`; `[x]` en el plan; commit
  `frontend-helpdesk-core-02: …`.
