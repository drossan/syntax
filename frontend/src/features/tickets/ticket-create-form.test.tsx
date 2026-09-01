import { screen, waitFor, within } from "@testing-library/react";
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
    await userEvent.type(await screen.findByLabelText(/descripción/i), "Detalle del problema");
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
    expect(screen.getByLabelText(/asunto/i)).toHaveAttribute("aria-invalid", "true");
  });

  it("un error de servidor en un campo desconocido no rompe el formulario ni navega", async () => {
    server.use(
      http.post(TICKETS, () =>
        HttpResponse.json(
          {
            type: "about:blank",
            title: "Datos inválidos",
            status: 422,
            errors: [{ field: "unknown_field", message: "Campo que la UI no conoce" }],
          },
          { status: 422 },
        ),
      ),
    );
    renderWithSession(<TicketCreateForm />);

    await userEvent.type(await screen.findByLabelText(/asunto/i), "Asunto válido");
    await userEvent.click(screen.getByRole("button", { name: /crear ticket/i }));

    await waitFor(() => expect(screen.getByLabelText(/asunto/i)).toBeInTheDocument());
    expect(screen.queryByText(/campo que la ui no conoce/i)).not.toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it("un error de servidor en el campo 'body' se asocia a la descripción", async () => {
    server.use(
      http.post(TICKETS, () =>
        HttpResponse.json(
          {
            type: "about:blank",
            title: "Datos inválidos",
            status: 422,
            errors: [{ field: "body", message: "La descripción supera el límite permitido" }],
          },
          { status: 422 },
        ),
      ),
    );
    renderWithSession(<TicketCreateForm />);

    await userEvent.type(await screen.findByLabelText(/asunto/i), "Asunto válido");
    await userEvent.click(screen.getByRole("button", { name: /crear ticket/i }));

    expect(await screen.findByText(/la descripción supera el límite permitido/i)).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it("un fallo de red (sin envelope problem+json) cae al mensaje de error genérico", async () => {
    server.use(http.post(TICKETS, () => HttpResponse.error()));
    renderWithSession(<TicketCreateForm />);

    await userEvent.type(await screen.findByLabelText(/asunto/i), "Asunto válido");
    await userEvent.click(screen.getByRole("button", { name: /crear ticket/i }));

    expect(await screen.findByText("No se pudo crear el ticket.")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it("el editor muestra el texto tecleado de verdad, no un valor forzado a vacío", async () => {
    renderWithSession(<TicketCreateForm />);

    const descripcion = await screen.findByLabelText(/descripción/i);
    await userEvent.type(descripcion, "detalle real del problema");

    expect(descripcion).toHaveValue("detalle real del problema");
  });

  it("las opciones de prioridad muestran sus etiquetas traducidas", async () => {
    renderWithSession(<TicketCreateForm />);

    await screen.findByLabelText(/asunto/i);
    const select = screen.getByLabelText(/prioridad/i);
    expect(within(select).getByRole("option", { name: "Baja" })).toBeInTheDocument();
    expect(within(select).getByRole("option", { name: "Normal" })).toBeInTheDocument();
    expect(within(select).getByRole("option", { name: "Alta" })).toBeInTheDocument();
    expect(within(select).getByRole("option", { name: "Urgente" })).toBeInTheDocument();
  });

  it("una descripción vacía sigue permitiendo crear el ticket, sin enviar body", async () => {
    let posted: unknown;
    server.use(
      http.post(TICKETS, async ({ request }) => {
        posted = await request.json();
        return HttpResponse.json(
          ticketFixture({ id: "cccccccc-0000-0000-0000-000000000009" }),
          { status: 201 },
        );
      }),
    );
    renderWithSession(<TicketCreateForm />);

    await userEvent.type(await screen.findByLabelText(/asunto/i), "Sin descripción");
    await userEvent.click(screen.getByRole("button", { name: /crear ticket/i }));

    await waitFor(() => expect(push).toHaveBeenCalled());
    expect(posted).not.toHaveProperty("body");
  });

  it("el Markdown compuesto con el toolbar del editor llega intacto a la creación del ticket", async () => {
    let posted: unknown;
    server.use(
      http.post(TICKETS, async ({ request }) => {
        posted = await request.json();
        return HttpResponse.json(
          ticketFixture({ id: "cccccccc-0000-0000-0000-000000000009" }),
          { status: 201 },
        );
      }),
    );
    renderWithSession(<TicketCreateForm />);

    await userEvent.type(await screen.findByLabelText(/asunto/i), "Con formato");
    const descripcion = await screen.findByLabelText(/descripción/i);
    await userEvent.type(descripcion, "detalle");
    const toolbar = document.querySelector<HTMLElement>(".w-md-editor-toolbar");
    if (!toolbar) throw new Error("toolbar no encontrado");
    await userEvent.click(within(toolbar).getByRole("button", { name: /negrita/i }));
    await userEvent.click(screen.getByRole("button", { name: /crear ticket/i }));

    await waitFor(() => expect(push).toHaveBeenCalled());
    expect((posted as { body: string }).body).toContain("**");
  });

  it("usar el toolbar (no teclear) marca el formulario como modificado (guard de salida)", async () => {
    const addEventListenerSpy = vi.spyOn(window, "addEventListener");
    renderWithSession(<TicketCreateForm />);

    await screen.findByLabelText(/asunto/i);
    const toolbar = await screen.findByRole("button", { name: /negrita/i });
    expect(addEventListenerSpy.mock.calls.some(([event]) => event === "beforeunload")).toBe(false);

    await userEvent.click(toolbar);

    await waitFor(() =>
      expect(addEventListenerSpy.mock.calls.some(([event]) => event === "beforeunload")).toBe(true),
    );
    addEventListenerSpy.mockRestore();
  });
});
