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
 * Cubre el flujo completo de los dos perfiles reales de usuario: `support-admin` (rol global, todas
 * las capacidades — navegación, alta/ajustes de tenant, invitación de usuario, asignación de rol,
 * aprobaciones, KB, notificaciones) y `client-agent` (usuario de tenant acotado por RBAC — nav
 * reducida, alta de ticket real). Solo `ticket-ai-auto-draft.spec.ts` dispara el ciclo completo de
 * `agent.trigger` (coste real de OpenAI, ~10-15s); el resto de specs no lo repite.
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
