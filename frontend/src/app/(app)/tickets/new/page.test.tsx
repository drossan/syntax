import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import NewTicketPage from "@/app/(app)/tickets/new/page";
import { meFixture } from "@/mocks/fixtures";
import { renderWithSession } from "@/test/render-with-session";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

/** La página de alta está protegida por `ticket.create` (guard de cliente). */
describe("New ticket page (/tickets/new)", () => {
  it("con ticket.create muestra el formulario de alta", async () => {
    renderWithSession(<NewTicketPage />, {
      me: meFixture({ capabilities: [{ capability: "ticket.create", scope: "tenant" }] }),
    });
    expect(await screen.findByRole("heading", { name: /nuevo ticket/i })).toBeInTheDocument();
  });

  it("sin ticket.create muestra acceso denegado (fail-closed)", async () => {
    renderWithSession(<NewTicketPage />, { me: meFixture({ capabilities: [] }) });
    expect(await screen.findByRole("heading", { name: /acceso denegado/i })).toBeInTheDocument();
  });
});
