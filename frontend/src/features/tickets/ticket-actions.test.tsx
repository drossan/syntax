import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { meFixture, messagePageFixture, ticketFixture, userFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import { renderWithSession, SESSION_BASE } from "@/test/render-with-session";
import type { components } from "@/types/api";

import { TicketDetail } from "./ticket-detail";

type Ticket = components["schemas"]["Ticket"];

const ID = "11111111-1111-1111-1111-111111111111";
const TENANT = "22222222-2222-2222-2222-222222222222";
const USER = "33333333-3333-3333-3333-333333333333";
const TICKET = `${SESSION_BASE}/api/v1/tickets/${ID}`;
const MESSAGES = `${SESSION_BASE}/api/v1/tickets/${ID}/messages`;
const TRANSITION = `${SESSION_BASE}/api/v1/tickets/${ID}/transition`;
const ASSIGN = `${SESSION_BASE}/api/v1/tickets/${ID}/assign`;
const PATCH = TICKET;

/** Agente con capacidades de mutación en su tenant (coincide con el tenant del ticket). */
const agentMe = meFixture({
  user: userFixture({ id: USER, tenant_id: TENANT }),
  capabilities: [
    { capability: "ticket.read", scope: "tenant" },
    { capability: "ticket.transition", scope: "tenant" },
    { capability: "ticket.assign", scope: "tenant" },
  ],
});

let posted: Array<{ url: string; body: unknown }> = [];
afterEach(() => {
  posted = [];
});

/** Sirve GET del ticket (estado dado) + hilo vacío. */
function serveTicket(over: Partial<Ticket> = {}) {
  server.use(
    http.get(TICKET, () =>
      HttpResponse.json(ticketFixture({ id: ID, tenant_id: TENANT, subject: "Ticket X", ...over })),
    ),
    http.get(MESSAGES, () => HttpResponse.json(messagePageFixture([]))),
  );
}

describe("TicketActions (mutaciones de ticket)", () => {
  it("transición optimista: al marcar pendiente el estado se refleja de inmediato", async () => {
    serveTicket({ status: "open" });
    server.use(
      http.post(TRANSITION, async ({ request }) => {
        posted.push({ url: request.url, body: await request.json() });
        await delay(150); // el optimismo debe verse ANTES de esta respuesta
        return HttpResponse.json(ticketFixture({ id: ID, tenant_id: TENANT, status: "pending" }));
      }),
    );

    renderWithSession(<TicketDetail ticketId={ID} />, { me: agentMe });
    await screen.findByText("Abierto");

    await userEvent.click(screen.getByRole("button", { name: "Pendiente" }));

    // Sincrónico tras el click: la respuesta aún no llegó, pero el estado ya cambió (optimista).
    expect(screen.getByText("Pendiente")).toBeInTheDocument();
    expect(posted[0]?.body).toStrictEqual({ status: "pending" });
  });

  it("rollback: si el servidor rechaza el cambio, el estado vuelve al anterior y se avisa", async () => {
    serveTicket({ status: "open" });
    server.use(
      http.post(TRANSITION, () =>
        HttpResponse.json({ type: "about:blank", title: "Conflicto", status: 409 }, { status: 409 }),
      ),
    );

    renderWithSession(<TicketDetail ticketId={ID} />, { me: agentMe });
    await screen.findByText("Abierto");
    await userEvent.click(screen.getByRole("button", { name: "Resuelto" }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Abierto")).toBeInTheDocument());
  });

  it("transición inválida no ofrecida: desde 'cerrado' solo se ofrece reabrir", async () => {
    serveTicket({ status: "closed" });

    renderWithSession(<TicketDetail ticketId={ID} />, { me: agentMe });
    await screen.findByText("Cerrado");

    expect(screen.getByRole("button", { name: "Reabierto" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Pendiente" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Abierto" })).not.toBeInTheDocument();
  });

  it("confirmación al cerrar: pide confirmar y no muta hasta confirmar", async () => {
    serveTicket({ status: "open" });
    server.use(
      http.post(TRANSITION, async ({ request }) => {
        posted.push({ url: request.url, body: await request.json() });
        return HttpResponse.json(ticketFixture({ id: ID, tenant_id: TENANT, status: "closed" }));
      }),
    );

    renderWithSession(<TicketDetail ticketId={ID} />, { me: agentMe });
    await screen.findByText("Abierto");
    await userEvent.click(screen.getByRole("button", { name: "Cerrado" }));

    const dialog = await screen.findByRole("alertdialog");
    expect(posted).toHaveLength(0); // aún no se envió nada
    await userEvent.click(within(dialog).getByRole("button", { name: /confirmar/i }));

    await waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0]?.body).toStrictEqual({ status: "closed" });
  });

  it("cancelar la confirmación no cambia el ticket ni envía mutación", async () => {
    serveTicket({ status: "open" });
    server.use(
      http.post(TRANSITION, async ({ request }) => {
        posted.push({ url: request.url, body: await request.json() });
        return HttpResponse.json(ticketFixture({ id: ID, tenant_id: TENANT, status: "closed" }));
      }),
    );

    renderWithSession(<TicketDetail ticketId={ID} />, { me: agentMe });
    await screen.findByText("Abierto");
    await userEvent.click(screen.getByRole("button", { name: "Cerrado" }));

    const dialog = await screen.findByRole("alertdialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /cancelar/i }));

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(screen.getByText("Abierto")).toBeInTheDocument();
    expect(posted).toHaveLength(0);
  });

  it("asignación: 'Asignarme' asigna el ticket al usuario actual", async () => {
    let assignee: string | null = null; // el GET refleja la asignación (server stateful)
    server.use(
      http.get(TICKET, () =>
        HttpResponse.json(
          ticketFixture({ id: ID, tenant_id: TENANT, subject: "Ticket X", status: "open", assignee_id: assignee }),
        ),
      ),
      http.get(MESSAGES, () => HttpResponse.json(messagePageFixture([]))),
      http.post(ASSIGN, async ({ request }) => {
        const body = (await request.json()) as { assignee_id: string | null };
        assignee = body.assignee_id;
        posted.push({ url: request.url, body });
        return HttpResponse.json(ticketFixture({ id: ID, tenant_id: TENANT, assignee_id: assignee }));
      }),
    );

    renderWithSession(<TicketDetail ticketId={ID} />, { me: agentMe });
    await screen.findByText("Abierto");
    await userEvent.click(screen.getByRole("button", { name: /asignarme/i }));

    expect(await screen.findByText(USER)).toBeInTheDocument();
    expect(posted[0]?.body).toStrictEqual({ assignee_id: USER });
  });

  it("prioridad: cambiarla envía PATCH y refleja la nueva prioridad", async () => {
    serveTicket({ status: "open", priority: "normal" });
    server.use(
      http.patch(PATCH, async ({ request }) => {
        posted.push({ url: request.url, body: await request.json() });
        return HttpResponse.json(ticketFixture({ id: ID, tenant_id: TENANT, priority: "high" }));
      }),
    );

    renderWithSession(<TicketDetail ticketId={ID} />, { me: agentMe });
    await screen.findByText("Abierto");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: /prioridad/i }), "high");

    await waitFor(() => expect(posted[0]?.body).toStrictEqual({ priority: "high" }));
  });

  it("reconciliación (onSettled): tras mutar, revalida y muestra el estado real del servidor", async () => {
    // El optimismo pone 'pending', pero la verdad del servidor (otro agente) es 'resolved'.
    let transitioned = false;
    server.use(
      http.get(TICKET, () =>
        HttpResponse.json(
          ticketFixture({
            id: ID,
            tenant_id: TENANT,
            subject: "Ticket X",
            status: transitioned ? "resolved" : "open",
          }),
        ),
      ),
      http.get(MESSAGES, () => HttpResponse.json(messagePageFixture([]))),
      http.post(TRANSITION, () => {
        transitioned = true;
        return HttpResponse.json(ticketFixture({ id: ID, tenant_id: TENANT, status: "resolved" }));
      }),
    );

    renderWithSession(<TicketDetail ticketId={ID} />, { me: agentMe });
    await screen.findByText("Abierto");
    await userEvent.click(screen.getByRole("button", { name: "Pendiente" }));

    // Tras revalidar (onSettled → invalidate → GET), gana la verdad del servidor.
    expect(await screen.findByText("Resuelto")).toBeInTheDocument();
  });
});
