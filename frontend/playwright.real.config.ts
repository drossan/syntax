import { defineConfig, devices } from "@playwright/test";

/**
 * Config de Playwright para e2e **contra el backend real** (Postgres + OpenAI real), no MSW.
 * `pnpm e2e:real` — requiere:
 *   1. `docker compose -f backend/docker-compose.yml up -d db`
 *   2. Backend arrancado (`make -C backend run` o equivalente) en `NEXT_PUBLIC_API_BASE_URL`
 *      (default `http://localhost:8000`, ver `.env.local`).
 *   3. `python -m app.infra.db.seed` corrido al menos una vez (`globalSetup` lo confirma, no lo
 *      dispara él mismo — requeriría un venv de Python desde Node, frágil entre entornos).
 *
 * Coste real: cada spec dispara al menos una llamada real a OpenAI (vía `agent.trigger`) — la suite se
 * mantiene deliberadamente pequeña (los caminos que MSW no puede verificar de verdad: CORS+cookies
 * cross-origin del login real, y el ciclo completo de `ai_auto_draft`), no exhaustiva.
 */
export default defineConfig({
  testDir: "./e2e-real",
  fullyParallel: false, // comparten el mismo tenant/DB seed — evita colisiones de rate-limit/estado
  forbidOnly: !!process.env.CI,
  retries: 0, // un reintento repetiría una llamada real a OpenAI — mejor ver el fallo real
  timeout: 60_000, // el ciclo classify→retrieve→grade→generate real puede tardar >10s
  reporter: "html",
  globalSetup: "./e2e-real/global-setup.ts",
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "pnpm dev",
    url: "http://localhost:3000",
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
