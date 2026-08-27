import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { useAuth } from "@/features/auth/auth-context";
import { meFixture, messageFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import { renderWithSession, SESSION_BASE } from "@/test/render-with-session";

import { TicketReplyForm } from "./ticket-reply-form";

/** Igual que `can.test.tsx`: confirma que la sesión resolvió DE VERDAD antes de leer "sigue vacío". */
function StatusProbe() {
  return <span>status:{useAuth().status}</span>;
}

const TICKET_ID = "11111111-1111-1111-1111-111111111111";
const MESSAGES = `${SESSION_BASE}/api/v1/tickets/${TICKET_ID}/messages`;

const clientAgentMe = meFixture({
  capabilities: [{ capability: "ticket.reply", scope: "tenant" }],
});
const supportAgentMe = meFixture({
  capabilities: [
    { capability: "ticket.reply", scope: "global" },
    { capability: "note.internal.write", scope: "global" },
  ],
});
const clientViewerMe = meFixture({
  capabilities: [{ capability: "ticket.read", scope: "tenant" }],
});

describe("TicketReplyForm", () => {
  it("sin ticket.reply ni note.internal.write no renderiza nada", async () => {
    renderWithSession(
      <>
        <StatusProbe />
        <TicketReplyForm
          ticketId={TICKET_ID}
          resourceTenantId="22222222-2222-2222-2222-222222222222"
        />
      </>,
      { me: clientViewerMe },
    );

    // Espera a que la sesión resuelva de verdad (docstring de `renderWithSession`) antes de confirmar
    // que sigue vacío — sin esto, "sin nada en el DOM" no distingue "sin capacidad" de "aún cargando".
    await screen.findByText("status:authenticated");
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
  });

  it("con solo ticket.reply: publica un mensaje público, sin selector de visibilidad", async () => {
    let posted: unknown;
    server.use(
      http.post(MESSAGES, async ({ request }) => {
        posted = await request.json();
        return HttpResponse.json(
          messageFixture({ id: "new-msg", body: "Ya está resuelto", visibility: "public" }),
          { status: 201 },
        );
      }),
    );
    renderWithSession(
      <TicketReplyForm
        ticketId={TICKET_ID}
        resourceTenantId="22222222-2222-2222-2222-222222222222"
      />,
      { me: clientAgentMe },
    );

    const textarea = await screen.findByLabelText(/responder/i);
    expect(screen.queryByLabelText(/visibilidad/i)).not.toBeInTheDocument();

    await userEvent.type(textarea, "Ya está resuelto");
    await userEvent.click(screen.getByRole("button", { name: /enviar/i }));

    await waitFor(() =>
      expect(posted).toStrictEqual({ body: "Ya está resuelto", visibility: "public" }),
    );
  });

  it("con note.internal.write: puede elegir nota interna y se envía como internal", async () => {
    let posted: unknown;
    server.use(
      http.post(MESSAGES, async ({ request }) => {
        posted = await request.json();
        return HttpResponse.json(
          messageFixture({ id: "new-msg", body: "Nota para el equipo", visibility: "internal" }),
          { status: 201 },
        );
      }),
    );
    renderWithSession(
      <TicketReplyForm
        ticketId={TICKET_ID}
        resourceTenantId="22222222-2222-2222-2222-222222222222"
      />,
      { me: supportAgentMe },
    );

    await userEvent.type(await screen.findByLabelText(/responder/i), "Nota para el equipo");
    await userEvent.selectOptions(screen.getByLabelText(/visibilidad/i), "internal");
    await userEvent.click(screen.getByRole("button", { name: /enviar/i }));

    await waitFor(() =>
      expect(posted).toStrictEqual({ body: "Nota para el equipo", visibility: "internal" }),
    );
  });

  it("no envía un mensaje vacío (validación de cliente)", async () => {
    let called = false;
    server.use(
      http.post(MESSAGES, () => {
        called = true;
        return HttpResponse.json(messageFixture(), { status: 201 });
      }),
    );
    renderWithSession(
      <TicketReplyForm
        ticketId={TICKET_ID}
        resourceTenantId="22222222-2222-2222-2222-222222222222"
      />,
      { me: clientAgentMe },
    );

    await userEvent.click(await screen.findByRole("button", { name: /enviar/i }));

    expect(await screen.findByText(/no puede estar vacío/i)).toBeInTheDocument();
    expect(called).toBe(false);
  });

  it("limpia el campo tras publicar con éxito", async () => {
    server.use(http.post(MESSAGES, () => HttpResponse.json(messageFixture(), { status: 201 })));
    renderWithSession(
      <TicketReplyForm
        ticketId={TICKET_ID}
        resourceTenantId="22222222-2222-2222-2222-222222222222"
      />,
      { me: clientAgentMe },
    );

    const textarea = await screen.findByLabelText(/responder/i);
    await userEvent.type(textarea, "Gracias por avisar");
    await userEvent.click(screen.getByRole("button", { name: /enviar/i }));

    await waitFor(() => expect(textarea).toHaveValue(""));
  });

  it("un error del servidor se muestra y no limpia el campo", async () => {
    server.use(
      http.post(MESSAGES, () =>
        HttpResponse.json(
          { type: "about:blank", title: "No se pudo publicar el mensaje.", status: 500 },
          { status: 500 },
        ),
      ),
    );
    renderWithSession(
      <TicketReplyForm
        ticketId={TICKET_ID}
        resourceTenantId="22222222-2222-2222-2222-222222222222"
      />,
      { me: clientAgentMe },
    );

    const textarea = await screen.findByLabelText(/responder/i);
    await userEvent.type(textarea, "Gracias por avisar");
    await userEvent.click(screen.getByRole("button", { name: /enviar/i }));

    expect(await screen.findByText("No se pudo publicar el mensaje.")).toBeInTheDocument();
    expect(textarea).toHaveValue("Gracias por avisar");
  });
});
