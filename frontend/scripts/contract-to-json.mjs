// @ts-check
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { parse } from "yaml";

/**
 * Convierte el contrato OpenAPI 3.1 (`.claude/specs/general/api-contract.yaml`) a un JSON
 * versionado en el frontend (`src/mocks/contract/openapi.json`). Ese JSON es la fuente de
 * verdad en RUNTIME para la validación de conformidad de los mocks con ajv (los tipos TS que
 * genera `openapi-typescript` son solo compile-time). Se ejecuta como parte de `pnpm gen:api`.
 */
const here = dirname(fileURLToPath(import.meta.url));
const contractPath = resolve(here, "../../.claude/specs/general/api-contract.yaml");
const outDir = resolve(here, "../src/mocks/contract");
const outPath = resolve(outDir, "openapi.json");

const doc = parse(readFileSync(contractPath, "utf8"));
mkdirSync(outDir, { recursive: true });
writeFileSync(outPath, `${JSON.stringify(doc, null, 2)}\n`);

console.log(`contract → ${outPath}`);
