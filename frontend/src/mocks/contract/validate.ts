import Ajv2020, { type ValidateFunction } from "ajv/dist/2020";

import openapi from "./openapi.json";

/**
 * Validación runtime de conformidad: comprueba que un dato (p.ej. una respuesta mockeada)
 * cumple el schema de su recurso en el contrato OpenAPI 3.1. Es lo testeable del "gate de
 * conformidad" — el drift de tipos lo caza `pnpm gen:api:check` (git diff), y el drift de
 * mocks lo caza además el typecheck (handlers tipados con openapi-msw).
 *
 * OpenAPI 3.1 usa el dialecto JSON Schema 2020-12 → se usa `Ajv2020`. Los `format` son
 * anotaciones (no se validan), coherente con el default de JSON Schema.
 */
const contractSchemas = (openapi as { components: { schemas: Record<string, unknown> } }).components
  .schemas;

const ajv = new Ajv2020({
  strict: false,
  allErrors: true,
  // Sin ajv-formats no hay formatos registrados: validar formatos es un no-op → mutante equivalente.
  // Stryker disable next-line BooleanLiteral
  validateFormats: false,
});
ajv.addSchema(openapi, "contract");

const validatorCache = new Map<string, ValidateFunction>();

/** Resultado de una validación de conformidad. */
export interface ValidationResult {
  valid: boolean;
  errors: string[];
}

/**
 * Valida `data` contra `#/components/schemas/<schemaName>` del contrato.
 *
 * @param schemaName Nombre del schema del recurso (p.ej. `"Ticket"`).
 * @param data Dato a validar (respuesta o fixture).
 * @returns `{ valid, errors }`; cada error va prefijado con el recurso divergente.
 * @throws Si `schemaName` no existe en el contrato.
 */
export function validateResponse(schemaName: string, data: unknown): ValidationResult {
  if (!(schemaName in contractSchemas)) {
    throw new Error(`Schema desconocido en el contrato: ${schemaName}`);
  }

  let validate = validatorCache.get(schemaName);
  if (!validate) {
    validate = ajv.compile({ $ref: `contract#/components/schemas/${schemaName}` });
    validatorCache.set(schemaName, validate);
  }

  const valid = validate(data);
  const errors = (validate.errors ?? []).map((error) =>
    `${schemaName}${error.instancePath} ${error.message ?? ""}`.trim(),
  );

  return { valid, errors };
}
