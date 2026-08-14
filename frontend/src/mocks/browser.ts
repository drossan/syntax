import { setupWorker } from "msw/browser";

import { e2eHandlers } from "./e2e/handlers";

/**
 * Worker de MSW para el navegador (dev + smokes e2e). Usa el mock **stateful** del camino dorado
 * (`e2e/handlers`). Lo arranca `MswGate` de forma condicional según `NEXT_PUBLIC_ENABLE_MSW`.
 */
export const worker = setupWorker(...e2eHandlers);
