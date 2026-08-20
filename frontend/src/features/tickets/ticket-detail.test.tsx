import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { meFixture, messageFixture, messagePageFixture, ticketFixture, userFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import { renderWithSession, SESSION_BASE } from "@/test/render-with-session";

import { TicketDetail } from "./ticket-detail";

const TICKET_ID = "11111111-1111-1111-1111-111111111111";
const TICKET = `${SESSION_BASE}/api/v1/tickets/${TICKET_ID}`;
const MESSAGES = `${SESSION_BASE}/api/v1/tickets/${TICKET_ID}/messages`;

const publicMsg = messageFixture({ id: "p", visibility: "public", body: "Mensaje público visible" });
const internalMsg = messageFixture({ id: "i", visibility: "internal", body: "Nota interna secreta" });

/** me de cliente (sin note.internal.read) y de soporte (con note.internal.read global). */
const clientMe = meFixture({
  user: userFixture({ roles: ["client_agent"] }),
  active_tenant_id: "cliente-a",
  capabilities: [{ capability: "ticket.read", scope: "tenant" }],
});
const supportMe = meFixture({
  capabilities: [
    { capability: "ticket.read", scope: "global" },
    { capability: "note.internal.read", scope: "global" },
  ],
});

function serveTicketWith(messages: ReturnType<typeof messageFixture>[]) {
  server.use(
    http.get(TICKET, () => HttpResponse.json(ticketFixture({ id: TICKET_ID, subject: "No publica el sitio" }))),
    http.get(MESSAGES, () => HttpResponse.json(messagePageFixture(messages))),
  );
}

describe("TicketDetail", () => {
  it("el cliente ve el mensaje público y NO la nota interna (defensa en profundidad)", async () => {
    serveTicketWith([publicMsg, internalMsg]);
    renderWithSession(<TicketDetail ticketId={TICKET_ID} />, { me: clientMe });

    expect(await screen.findByText("Mensaje público visible")).toBeInTheDocument();
    expect(screen.queryByText("Nota interna secreta")).not.toBeInTheDocument();
  });

  it("soporte ve tanto el mensaje público como la nota interna", async () => {
    serveTicketWith([publicMsg, internalMsg]);
    renderWithSession(<TicketDetail ticketId={TICKET_ID} />, { me: supportMe });

    expect(await screen.findByText("Mensaje público visible")).toBeInTheDocument();
    expect(screen.getByText("Nota interna secreta")).toBeInTheDocument();
  });

  it("muestra el hilo en orden cronológico con autor y fecha", async () => {
    const later = messageFixture({ id: "b", body: "Segundo", created_at: "2026-08-13T12:00:00Z" });
    const earlier = messageFixture({ id: "a", body: "Primero", created_at: "2026-08-13T09:00:00Z" });
    serveTicketWith([later, earlier]);
    renderWithSession(<TicketDetail ticketId={TICKET_ID} />, { me: clientMe });

    await screen.findByText("Primero");
    const items = screen.getAllByRole("listitem");
    expect(within(items[0]!).getByText("Primero")).toBeInTheDocument();
    expect(within(items[1]!).getByText("Segundo")).toBeInTheDocument();
    // fecha renderizada (formateada por locale/tz)
    expect(within(items[0]!).getByText(/2026/)).toBeInTheDocument();
  });

  it("hilo sin mensajes → estado vacío", async () => {
    serveTicketWith([]);
    renderWithSession(<TicketDetail ticketId={TICKET_ID} />, { me: clientMe });

    expect(await screen.findByText(/aún no hay mensajes/i)).toBeInTheDocument();
  });

  it("ticket inaccesible (404) → no-encontrado/sin-acceso, sin filtrar datos", async () => {
    server.use(
      http.get(TICKET, () =>
        HttpResponse.json({ type: "about:blank", title: "No encontrado", status: 404 }, { status: 404 }),
      ),
      http.get(MESSAGES, () => HttpResponse.json(messagePageFixture([internalMsg]))),
    );
    renderWithSession(<TicketDetail ticketId={TICKET_ID} />, { me: clientMe });

    expect(await screen.findByText(/no encontrado o sin acceso/i)).toBeInTheDocument();
    expect(screen.queryByText("No publica el sitio")).not.toBeInTheDocument();
    expect(screen.queryByText("Nota interna secreta")).not.toBeInTheDocument();
  });
});
