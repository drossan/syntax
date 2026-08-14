import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";

import { server } from "@/mocks/server";

/**
 * Setup global de la suite de tests.
 *
 * MSW intercepta TODO el tráfico HTTP: `onUnhandledRequest: "error"` hace fallar
 * cualquier petición sin handler, de modo que ningún test dependa de la red real.
 */
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));

afterEach(() => {
  cleanup();
  server.resetHandlers();
});

afterAll(() => server.close());
