import { defineConfig, devices } from "@playwright/test";

/**
 * Config de Playwright para los smokes e2e del happy-path crítico
 * (login → ticket → draft IA → aprobación + tenant-switch).
 *
 * Los tests reales los escribe `frontend-helpdesk-core-21`; aquí solo queda el
 * andamiaje. `webServer` levanta la app en CI/local antes de correr los specs.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: "html",
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    // Los smokes corren contra la app con MSW (mock stateful del camino dorado) — sin backend real.
    command: "NEXT_PUBLIC_ENABLE_MSW=true pnpm dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 120000,
  },
});
