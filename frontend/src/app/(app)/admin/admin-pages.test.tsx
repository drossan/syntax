import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import RolesPage from "@/app/(app)/admin/roles/page";
import TenantsPage from "@/app/(app)/admin/tenants/page";
import UsersPage from "@/app/(app)/admin/users/page";
import { meFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import { renderWithSession, SESSION_BASE } from "@/test/render-with-session";

const API = `${SESSION_BASE}/api/v1`;

function serveAdmin() {
  server.use(
    http.get(`${API}/admin/tenants`, () => HttpResponse.json({ items: [], page: 1, page_size: 20, total: 0 })),
    http.get(`${API}/admin/users`, () => HttpResponse.json({ items: [], page: 1, page_size: 20, total: 0 })),
    http.get(`${API}/admin/roles`, () => HttpResponse.json([])),
  );
}

describe("Admin pages guards", () => {
  it("tenants: con tenant.manage se ve; sin ella, acceso denegado", async () => {
    serveAdmin();
    renderWithSession(<TenantsPage />, {
      me: meFixture({ capabilities: [{ capability: "tenant.manage", scope: "global" }] }),
    });
    expect(await screen.findByRole("heading", { name: /clientes/i })).toBeInTheDocument();
  });

  it("tenants: un client_admin (sin tenant.manage) recibe acceso denegado", async () => {
    renderWithSession(<TenantsPage />, {
      me: meFixture({ capabilities: [{ capability: "user.manage", scope: "tenant" }] }),
    });
    expect(await screen.findByRole("heading", { name: /acceso denegado/i })).toBeInTheDocument();
  });

  it("users: con user.manage se ve la administración de usuarios", async () => {
    serveAdmin();
    renderWithSession(<UsersPage />, {
      me: meFixture({ capabilities: [{ capability: "user.manage", scope: "tenant" }] }),
    });
    expect(await screen.findByRole("heading", { name: /usuarios/i })).toBeInTheDocument();
  });

  it("roles: con role.manage se ve la vista de roles; sin ella, denegado", async () => {
    serveAdmin();
    renderWithSession(<RolesPage />, {
      me: meFixture({ capabilities: [{ capability: "role.manage", scope: "tenant" }] }),
    });
    expect(await screen.findByRole("heading", { name: /roles y capacidades/i })).toBeInTheDocument();
  });

  it("roles: sin role.manage recibe acceso denegado", async () => {
    renderWithSession(<RolesPage />, {
      me: meFixture({ capabilities: [{ capability: "ticket.read", scope: "tenant" }] }),
    });
    expect(await screen.findByRole("heading", { name: /acceso denegado/i })).toBeInTheDocument();
  });
});
