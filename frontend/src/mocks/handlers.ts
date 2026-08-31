import { createOpenApiHttp } from "openapi-msw";

import type { paths } from "@/types/api";
import { meFixture, ticketFixture, ticketPageFixture, tokenFixture } from "./fixtures";

/**
 * Handlers de MSW tipados contra el contrato (openapi-msw). El helper `response(code)` valida
 * el body contra el schema en tiempo de COMPILACIÓN: un mock que no cumple el schema no
 * typecheckea (design-review C1 — el contrato como mecanismo). `baseUrl` con `*` matchea
 * cualquier origen (dev usa `http://localhost:8000/api/v1`).
 *
 * Compartidos por el server (Node/tests) y el worker (navegador/dev). Las tareas de feature
 * añaden aquí los handlers de sus recursos; la validación runtime vive en
 * `src/mocks/contract/validate.ts`.
 */
const http = createOpenApiHttp<paths>({ baseUrl: "*/api/v1" });

export const handlers = [
  http.post("/auth/login", ({ response }) => response(200).json(tokenFixture())),
  http.post("/auth/refresh", ({ response }) => response(200).json(tokenFixture())),
  http.get("/auth/me", ({ response }) => response(200).json(meFixture())),
  http.post("/auth/logout", ({ response }) => response(204).empty()),
  http.post("/auth/password/forgot", ({ response }) => response(202).empty()),
  http.post("/auth/password/reset", ({ response }) => response(204).empty()),
  http.get("/tickets", ({ response }) => response(200).json(ticketPageFixture())),
  http.post("/tickets", ({ response }) => response(201).json(ticketFixture())),
  // Default: sin run activo — los tests que sí quieren uno lo sobrescriben con `server.use(...)`.
  http.get("/tickets/{id}/agent-runs/active", ({ response }) => response(200).json(null)),
  // Default: ambos ajustes en su valor de arranque — los tests que quieren otro los sobrescriben.
  http.get("/admin/settings", ({ response }) =>
    response(200).json({ auto_approve: false, ai_auto_draft: true }),
  ),
  http.patch("/admin/settings", async ({ request, response }) =>
    response(200).json(await request.json()),
  ),
];
