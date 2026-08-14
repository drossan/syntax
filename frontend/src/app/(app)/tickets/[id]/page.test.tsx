import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import TicketDetailPage from "@/app/(app)/tickets/[id]/page";
import { meFixture, messagePageFixture, ticketFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import { renderWithSession, SESSION_BASE } from "@/test/render-with-session";

const TICKET_ID = "11111111-1111-1111-1111-111111111111";

/** Ruta dinámica de detalle: protegida por `ticket.read`; `params` es una Promise (Next 16). */
describe("Ticket detail page (/tickets/[id])", () => {
  it("con ticket.read renderiza el detalle del ticket", async () => {
    server.use(
      http.get(`${SESSION_BASE}/api/v1/tickets/${TICKET_ID}`, () =>
        HttpResponse.json(ticketFixture({ id: TICKET_ID, subject: "Asunto del detalle" })),
      ),
      http.get(`${SESSION_BASE}/api/v1/tickets/${TICKET_ID}/messages`, () =>
        HttpResponse.json(messagePageFixture()),
      ),
    );

    const ui = await TicketDetailPage({ params: Promise.resolve({ id: TICKET_ID }) });
    renderWithSession(ui, {
      me: meFixture({ capabilities: [{ capability: "ticket.read", scope: "tenant" }] }),
    });

    expect(await screen.findByRole("heading", { name: "Asunto del detalle" })).toBeInTheDocument();
  });

  it("sin ticket.read muestra acceso denegado (fail-closed)", async () => {
    const ui = await TicketDetailPage({ params: Promise.resolve({ id: TICKET_ID }) });
    renderWithSession(ui, { me: meFixture({ capabilities: [] }) });

    expect(await screen.findByRole("heading", { name: /acceso denegado/i })).toBeInTheDocument();
  });
});
