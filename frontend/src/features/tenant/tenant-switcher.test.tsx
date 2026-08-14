import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { useAuth } from "@/features/auth/auth-context";
import { TenantSwitcher } from "@/features/tenant/tenant-switcher";
import { meFixture, userFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import { renderWithSession, SESSION_BASE } from "@/test/render-with-session";

function StatusProbe() {
  return <span>status:{useAuth().status}</span>;
}

const TENANTS = `${SESSION_BASE}/api/v1/admin/tenants`;

function tenantsPage() {
  return {
    items: [
      { id: "t1", slug: "acme", name: "Tenant A", status: "active" },
      { id: "t2", slug: "globex", name: "Tenant B", status: "active" },
    ],
    page: 1,
    page_size: 20,
    total: 2,
  };
}

/**
 * Escenarios Gherkin: Soporte (ámbito global) cambia de tenant; el cliente no ve el switcher.
 * Task frontend-helpdesk-core-05.
 */
describe("TenantSwitcher", () => {
  it("Soporte (ámbito global) ve el switcher y al elegir otro tenant cambia el tenant activo", async () => {
    server.use(http.get(TENANTS, () => HttpResponse.json(tenantsPage())));

    renderWithSession(<TenantSwitcher />, {
      me: meFixture({
        capabilities: [{ capability: "ticket.read", scope: "global" }],
        user: userFixture({ tenant_id: "t1" }),
      }),
    });

    const select = await screen.findByRole("combobox", { name: "Tenant activo" });
    await within(select).findByRole("option", { name: "Tenant B" });

    await userEvent.selectOptions(select, "t2");

    expect((select as HTMLSelectElement).value).toBe("t2");
  });

  it("el cliente (sin ámbito global) no ve el switcher", async () => {
    renderWithSession(
      <>
        <StatusProbe />
        <TenantSwitcher />
      </>,
      {
        me: meFixture({
          capabilities: [{ capability: "ticket.read", scope: "tenant" }],
          user: userFixture(),
        }),
      },
    );

    await screen.findByText("status:authenticated");
    expect(screen.queryByRole("combobox", { name: "Tenant activo" })).not.toBeInTheDocument();
  });
});
