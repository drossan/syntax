import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ticketFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import { renderWithSession, SESSION_BASE } from "@/test/render-with-session";

import { TicketCreateForm } from "./ticket-create-form";

const TICKETS = `${SESSION_BASE}/api/v1/tickets`;

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

afterEach(() => push.mockReset());

/** Escenarios Gherkin: creación válida, validación de cliente, error 422 del servidor. */
describe("TicketCreateForm", () => {
  it("creación válida → crea el ticket y navega a su detalle", async () => {
    server.use(
      http.post(TICKETS, () =>
        HttpResponse.json(ticketFixture({ id: "cccccccc-0000-0000-0000-000000000009" }), { status: 201 }),
      ),
    );
    renderWithSession(<TicketCreateForm />);

    await userEvent.type(await screen.findByLabelText(/asunto/i), "No puedo publicar");
    await userEvent.type(screen.getByLabelText(/descripción/i), "Detalle del problema");
    await userEvent.click(screen.getByRole("button", { name: /crear ticket/i }));

    await waitFor(() =>
      expect(push).toHaveBeenCalledWith("/tickets/cccccccc-0000-0000-0000-000000000009"),
    );
  });

  it("validación de cliente → sin asunto muestra error y no llama a la API", async () => {
    let posted = 0;
    server.use(
      http.post(TICKETS, () => {
        posted += 1;
        return HttpResponse.json(ticketFixture(), { status: 201 });
      }),
    );
    renderWithSession(<TicketCreateForm />);

    await userEvent.type(await screen.findByLabelText(/descripción/i), "Solo descripción");
    await userEvent.click(screen.getByRole("button", { name: /crear ticket/i }));

    expect(await screen.findByText(/el asunto es obligatorio/i)).toBeInTheDocument();
    expect(posted).toBe(0);
    expect(push).not.toHaveBeenCalled();
  });

  it("error de validación del servidor (422) → muestra el error en el campo correspondiente", async () => {
    server.use(
      http.post(TICKETS, () =>
        HttpResponse.json(
          {
            type: "about:blank",
            title: "Datos inválidos",
            status: 422,
            errors: [{ field: "subject", message: "Asunto duplicado en tu tenant" }],
          },
          { status: 422 },
        ),
      ),
    );
    renderWithSession(<TicketCreateForm />);

    await userEvent.type(await screen.findByLabelText(/asunto/i), "Repetido");
    await userEvent.click(screen.getByRole("button", { name: /crear ticket/i }));

    expect(await screen.findByText(/asunto duplicado en tu tenant/i)).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });
});
