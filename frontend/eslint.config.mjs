import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // Fichero generado por MSW (worker del navegador).
    "public/mockServiceWorker.js",
    // Artefactos de Stryker (sandbox temporal + reports).
    ".stryker-tmp/**",
    "reports/**",
  ]),
]);

export default eslintConfig;
