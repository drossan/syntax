
## 2026-08-13 — cierre
- **Nuevos**: `e2e/{golden-path.spec.ts, tenant-switch.spec.ts}`, `src/mocks/e2e/handlers.ts` (mock stateful del camino dorado), `src/mocks/msw-gate.tsx` (arranque MSW en navegador). **Modificados**: `src/mocks/browser.ts` (usa e2eHandlers), `src/app/providers.tsx` (+MswGate), `playwright.config.ts` (webServer con `NEXT_PUBLIC_ENABLE_MSW=true` + timeout).
- **Cableado que faltaba** (heredado stub): el worker MSW del navegador nunca se arrancaba; ahora `MswGate` lo arranca (singleton para evitar el doble `start()` de React Strict Mode) cuando el flag está on.
- **Setup del entorno**: `pnpm exec playwright install chromium` (binario del navegador para el dev-dep ya existente `@playwright/test`; NO es una dependencia npm nueva — package.json sin cambios, verificado). Chromium 151/v1234.
- **Tests (salida real)**: `pnpm e2e` → **2 passed** (golden-path + tenant-switch); `pnpm test` → 274/63 verde; typecheck limpio; lint `No issues found`.
- **Gate de mutación**: N/A — la 21 está fuera del gate por diseño (e2e); los ficheros tocados viven en `src/mocks/**` (fuera de los globs de Stryker).
- **Fact-checker** (sonnet, independiente): **10/10 VERIFICADO** (re-ejecutó `pnpm e2e` → 2 passed).
- **Cómo correr**: `pnpm --filter frontend e2e` (Playwright levanta `next dev` con MSW; requiere `playwright install chromium` una vez). En CI corre igual (webServer con `NEXT_PUBLIC_ENABLE_MSW=true`).
- **Limitación documentada**: el smoke de tenant verifica el cableado del switch (selección + revalidación), no diferenciación de datos por tenant — `GET /tickets` no expone param de tenant (gap de contrato). **Tiempo real**: ~1.7h.
