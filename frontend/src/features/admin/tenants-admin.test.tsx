import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { meFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import { renderWithSession, SESSION_BASE } from "@/test/render-with-session";

import { TenantsAdmin } from "./tenants-admin";

const TENANTS = `${SESSION_BASE}/api/v1/admin/tenants`;
const supportAdmin = meFixture({ capabilities: [{ capability: "tenant.manage", scope: "global" }] });

let created: unknown;
afterEach(() => {
  created = undefined;
});

function serveTenants(items: Array<{ id: string; slug: string; name: string; status: string }>) {
  server.use(
    http.get(TENANTS, () => HttpResponse.json({ items, page: 1, page_size: 20, total: items.length })),
    http.post(TENANTS, async ({ request }) => {
      created = await request.json();
      return HttpResponse.json({ id: "new", slug: "acme", name: "Acme", status: "active" }, { status: 201 });
    }),
  );
}

describe("TenantsAdmin", () => {
  it("crear un tenant válido lo envía y aparece en el listado", async () => {
    serveTenants([]);
    renderWithSession(<TenantsAdmin />, { me: supportAdmin });

    await userEvent.type(await screen.findByLabelText(/slug/i), "acme");
    await userEvent.type(screen.getByLabelText(/nombre/i), "Acme");

    // Tras crear, el listado se revalida e incluye el nuevo tenant.
    serveTenants([{ id: "new", slug: "acme", name: "Acme", status: "active" }]);
    await userEvent.click(screen.getByRole("button", { name: /crear tenant/i }));

    await waitFor(() => expect(created).toStrictEqual({ slug: "acme", name: "Acme" }));
    expect(await screen.findByText("Acme")).toBeInTheDocument();
  });

  it("no envía si falta el nombre (validación de cliente)", async () => {
    serveTenants([]);
    renderWithSession(<TenantsAdmin />, { me: supportAdmin });

    await userEvent.type(await screen.findByLabelText(/slug/i), "acme");
    await userEvent.click(screen.getByRole("button", { name: /crear tenant/i }));

    expect(await screen.findByText(/nombre.*obligatorio/i)).toBeInTheDocument();
    expect(created).toBeUndefined();
  });
});
