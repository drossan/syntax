import "@testing-library/jest-dom/vitest";

import { cleanup, configure } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";

import { server } from "@/mocks/server";

/**
 * `findBy*`/`waitFor` por defecto esperan 1000ms — insuficiente para el `next/dynamic({ssr: false})`
 * de `MarkdownEditor` bajo carga de CPU (p.ej. Stryker corriendo en paralelo), donde se observaron
 * fallos intermitentes con el placeholder de carga aún en el DOM.
 */
configure({ asyncUtilTimeout: 5000 });

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
