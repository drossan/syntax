import { setupServer } from "msw/node";

import { handlers } from "./handlers";

/**
 * Server de MSW para entornos Node (tests de Vitest). Arranca en `src/test/setup.ts`.
 */
export const server = setupServer(...handlers);
