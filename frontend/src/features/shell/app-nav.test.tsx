import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AppNav } from "@/features/shell/app-nav";
import { meFixture, userFixture } from "@/mocks/fixtures";
import { renderWithSession } from "@/test/render-with-session";

vi.mock("next/navigation", () => ({
  usePathname: () => "/approvals",
}));

/**
 * Escenario Gherkin: «la navegación refleja las capacidades del rol».
 * Task frontend-helpdesk-core-06.
 */
describe("AppNav", () => {
  it("no muestra la administración de clientes sin la capacidad `tenant.manage`", async () => {
    renderWithSession(<AppNav />, {
      me: meFixture({
        capabilities: [{ capability: "ticket.read", scope: "tenant" }],
        user: userFixture(),
      }),
    });

    expect(await screen.findByRole("link", { name: "Bandeja" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Clientes" })).not.toBeInTheDocument();
  });

  it("muestra la administración de clientes con `tenant.manage`", async () => {
    renderWithSession(<AppNav />, {
      me: meFixture({
        capabilities: [
          { capability: "ticket.read", scope: "global" },
          { capability: "tenant.manage", scope: "global" },
        ],
        user: userFixture(),
      }),
    });

    expect(await screen.findByRole("link", { name: "Clientes" })).toBeInTheDocument();
  });

  it("muestra Roles con `role.manage`, no sin ella (ruta antes huérfana, sin link)", async () => {
    renderWithSession(<AppNav />, {
      me: meFixture({
        capabilities: [{ capability: "ticket.read", scope: "tenant" }],
        user: userFixture(),
      }),
    });
    expect(screen.queryByRole("link", { name: "Roles" })).not.toBeInTheDocument();

    renderWithSession(<AppNav />, {
      me: meFixture({
        capabilities: [
          { capability: "ticket.read", scope: "global" },
          { capability: "role.manage", scope: "global" },
        ],
        user: userFixture(),
      }),
    });
    expect(await screen.findByRole("link", { name: "Roles" })).toBeInTheDocument();
  });

  it("marca la sección activa con aria-current, y ninguna otra", async () => {
    renderWithSession(<AppNav />, {
      me: meFixture({
        capabilities: [
          { capability: "ticket.read", scope: "tenant" },
          { capability: "approval.decide", scope: "global" },
        ],
        user: userFixture(),
      }),
    });

    const active = await screen.findByRole("link", { name: "Aprobaciones" });
    expect(active).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Bandeja" })).not.toHaveAttribute("aria-current");
  });
});
