import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { meFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import { renderWithSession, SESSION_BASE } from "@/test/render-with-session";

import { RolesCatalog } from "./roles-catalog";

const API = `${SESSION_BASE}/api/v1`;
const me = meFixture({ capabilities: [{ capability: "role.manage", scope: "tenant" }] });

function serveCatalog() {
  server.use(
    http.get(`${API}/admin/roles`, () =>
      HttpResponse.json([
        { id: "r1", name: "client_agent", kind: "system", tenant_id: null, capabilities: ["ticket.reply", "ticket.read"] },
      ]),
    ),
    http.get(`${API}/admin/capabilities`, () =>
      HttpResponse.json([{ name: "ticket.reply", scope: "tenant", description: "Responder tickets" }]),
    ),
  );
}

describe("RolesCatalog", () => {
  it("muestra los roles semilla y sus capacidades (solo lectura)", async () => {
    serveCatalog();
    renderWithSession(<RolesCatalog />, { me });

    expect(await screen.findByText("client_agent")).toBeInTheDocument();
    expect(screen.getByText("ticket.reply")).toBeInTheDocument();
    expect(screen.getByText("ticket.read")).toBeInTheDocument();
  });

  it("no ofrece composer de roles custom y anuncia que llegará con el enforcement", async () => {
    serveCatalog();
    renderWithSession(<RolesCatalog />, { me });

    await screen.findByText("client_agent");
    expect(screen.queryByRole("button", { name: /crear rol|nuevo rol|componer/i })).not.toBeInTheDocument();
    expect(screen.getByText(/enforcement/i)).toBeInTheDocument();
  });
});
