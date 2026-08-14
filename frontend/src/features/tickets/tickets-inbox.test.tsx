import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

// La bandeja usa useUrlListState (task 22): mock estático de next/navigation (el estado interno del
// hook re-renderiza; la URL solo se escribe, no dirige).
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(""),
}));

import { meFixture, ticketFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import { renderWithSession, SESSION_BASE } from "@/test/render-with-session";
import type { components } from "@/types/api";

import { TicketsInbox } from "./tickets-inbox";

const TICKETS = `${SESSION_BASE}/api/v1/tickets`;

type Ticket = components["schemas"]["Ticket"];

let lastQuery: Record<string, string> = {};
afterEach(() => {
  lastQuery = {};
});

/** Registra un handler de `GET /tickets` que captura la query y responde con `page`. */
function serveTickets(page: { items: Ticket[]; page: number; page_size: number; total: number }) {
  server.use(
    http.get(TICKETS, ({ request }) => {
      lastQuery = Object.fromEntries(new URL(request.url).searchParams);
      return HttpResponse.json(page);
    }),
  );
}

const recent = ticketFixture({
  id: "aaaaaaaa-0000-0000-0000-000000000001",
  subject: "Ticket reciente",
  updated_at: "2026-08-13T10:00:00Z",
});
const old = ticketFixture({
  id: "aaaaaaaa-0000-0000-0000-000000000002",
  subject: "Ticket antiguo",
  status: "pending",
  updated_at: "2026-08-01T10:00:00Z",
});

describe("TicketsInbox", () => {
  it("lista los tickets en el orden devuelto y pide el orden determinista por defecto", async () => {
    serveTickets({ items: [recent, old], page: 1, page_size: 20, total: 2 });

    renderWithSession(<TicketsInbox />);

    await screen.findByText("Ticket reciente");
    const rows = screen.getAllByRole("row").slice(1); // sin la cabecera
    expect(within(rows[0]!).getByText("Ticket reciente")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("Ticket antiguo")).toBeInTheDocument();
    expect(lastQuery.sort).toBe("-updated_at");
  });

  it("filtra por estado: al elegir 'pendiente' solo pide y muestra los pendientes", async () => {
    serveTickets({ items: [recent, old], page: 1, page_size: 20, total: 2 });
    renderWithSession(<TicketsInbox />);
    await screen.findByText("Ticket reciente");

    serveTickets({ items: [old], page: 1, page_size: 20, total: 1 });
    await userEvent.selectOptions(screen.getByRole("combobox", { name: /estado/i }), "pending");

    await waitFor(() => expect(lastQuery.status).toBe("pending"));
    await screen.findByText("Ticket antiguo");
    expect(screen.queryByText("Ticket reciente")).not.toBeInTheDocument();
  });

  it("muestra el indicador de SLA vencido en un ticket cuyo SLA ya pasó", async () => {
    const overdue = ticketFixture({
      id: "aaaaaaaa-0000-0000-0000-000000000003",
      subject: "Ticket con SLA vencido",
      sla_due: "2000-01-01T00:00:00Z",
    });
    serveTickets({ items: [overdue], page: 1, page_size: 20, total: 1 });

    renderWithSession(<TicketsInbox />);

    const row = (await screen.findByText("Ticket con SLA vencido")).closest("tr")!;
    expect(within(row).getByText("Vencido")).toBeInTheDocument();
  });

  it("estado vacío: sin resultados ofrece limpiar filtros y al limpiar re-pide sin filtro", async () => {
    serveTickets({ items: [recent], page: 1, page_size: 20, total: 1 });
    renderWithSession(<TicketsInbox />);
    await screen.findByText("Ticket reciente");

    serveTickets({ items: [], page: 1, page_size: 20, total: 0 });
    await userEvent.selectOptions(screen.getByRole("combobox", { name: /estado/i }), "closed");
    await waitFor(() => expect(lastQuery.status).toBe("closed"));

    const empty = await screen.findByRole("status");
    const clear = within(empty).getByRole("button", { name: /limpiar filtros/i });

    serveTickets({ items: [recent], page: 1, page_size: 20, total: 1 });
    await userEvent.click(clear);

    await screen.findByText("Ticket reciente");
    await waitFor(() => expect(lastQuery).not.toHaveProperty("status"));
  });

  it("estado de error: un envelope de fallo muestra el error y reintenta al pulsar reintentar", async () => {
    server.use(
      http.get(TICKETS, () =>
        HttpResponse.json(
          { type: "about:blank", title: "No se pudo cargar la bandeja", status: 500 },
          { status: 500 },
        ),
      ),
    );
    renderWithSession(<TicketsInbox />);

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText(/no se pudo cargar la bandeja/i)).toBeInTheDocument();

    serveTickets({ items: [recent], page: 1, page_size: 20, total: 1 });
    await userEvent.click(within(alert).getByRole("button", { name: /reintentar/i }));

    await screen.findByText("Ticket reciente");
  });

  it("aislamiento de tenant: un cliente nunca envía un parámetro de tenant en la petición", async () => {
    serveTickets({ items: [recent], page: 1, page_size: 20, total: 1 });
    renderWithSession(<TicketsInbox />, {
      me: {
        user: {
          id: "u1",
          tenant_id: "cliente-a",
          email: "cliente@acme.io",
          status: "active",
          roles: ["client_agent"],
        },
        capabilities: [{ capability: "ticket.read", scope: "tenant" }],
      },
    });

    await screen.findByText("Ticket reciente");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: /estado/i }), "open");
    await waitFor(() => expect(lastQuery.status).toBe("open"));

    expect(lastQuery).not.toHaveProperty("tenant_id");
    expect(lastQuery).not.toHaveProperty("tenant");
  });

  it("página fuera de rango: una página posterior a la última muestra el vacío sin error", async () => {
    serveTickets({ items: [recent], page: 1, page_size: 1, total: 2 });
    renderWithSession(<TicketsInbox />);
    await screen.findByText("Ticket reciente");

    serveTickets({ items: [], page: 2, page_size: 1, total: 2 });
    await userEvent.click(screen.getByRole("button", { name: /siguiente/i }));

    await waitFor(() => expect(lastQuery.page).toBe("2"));
    expect(await screen.findByRole("status")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("con ticket.create ofrece un enlace de alta hacia /tickets/new (entrada de la 08)", async () => {
    serveTickets({ items: [recent], page: 1, page_size: 20, total: 1 });
    renderWithSession(<TicketsInbox />, {
      me: meFixture({
        capabilities: [
          { capability: "ticket.read", scope: "tenant" },
          { capability: "ticket.create", scope: "tenant" },
        ],
      }),
    });

    expect(await screen.findByRole("link", { name: /nuevo ticket/i })).toHaveAttribute(
      "href",
      "/tickets/new",
    );
  });

  it("sin ticket.create no ofrece el enlace de alta", async () => {
    serveTickets({ items: [recent], page: 1, page_size: 20, total: 1 });
    renderWithSession(<TicketsInbox />);

    await screen.findByText("Ticket reciente");
    expect(screen.queryByRole("link", { name: /nuevo ticket/i })).not.toBeInTheDocument();
  });
});
