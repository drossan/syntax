import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

/**
 * Configuración de Vitest para el package `frontend`.
 *
 * - Entorno `jsdom` (componentes React con RTL).
 * - `setupFiles` arranca el server de MSW y `@testing-library/jest-dom`.
 * - Alias `@/*` → `src/*` (espejo del `paths` de tsconfig, sin depender de plugins extra).
 * - Los tests e2e de Playwright viven en `e2e/` y quedan EXCLUIDOS del runner de Vitest.
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    exclude: ["node_modules", ".next", "e2e"],
    css: false,
  },
});
