import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

// La bandeja usa useUrlListState (task 22) → mock estático de next/navigation.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(""),
}));

import InboxPage from "@/app/(app)/page";
import { meFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import { renderWithSession, SESSION_BASE } from "@/test/render-with-session";

/** La home `/` es la bandeja, protegida por `ticket.read` (guard de cliente). */
describe("Inbox page (/)", () => {
  it("con la capacidad ticket.read muestra la bandeja", async () => {
    server.use(
      http.get(`${SESSION_BASE}/api/v1/tickets`, () =>
        HttpResponse.json({ items: [], page: 1, page_size: 20, total: 0 }),
      ),
    );
    renderWithSession(<InboxPage />, {
      me: meFixture({ capabilities: [{ capability: "ticket.read", scope: "tenant" }] }),
    });

    expect(await screen.findByRole("heading", { name: "Bandeja de tickets" })).toBeInTheDocument();
  });

  it("sin la capacidad ticket.read muestra acceso denegado (fail-closed)", async () => {
    renderWithSession(<InboxPage />, { me: meFixture({ capabilities: [] }) });

    expect(await screen.findByRole("heading", { name: /acceso denegado/i })).toBeInTheDocument();
  });
});
