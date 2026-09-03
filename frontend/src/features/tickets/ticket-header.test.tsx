import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ticketFixture } from "@/mocks/fixtures";
import { renderWithIntl } from "@/test/render-with-intl";

import { TicketHeader } from "./ticket-header";

describe("TicketHeader", () => {
  it("muestra el email del responsable, no el UUID", () => {
    const ticket = ticketFixture({
      assignee_id: "33333333-3333-3333-3333-333333333333",
      assignee_email: "soporte@syntax.local",
    });
    renderWithIntl(<TicketHeader ticket={ticket} />);

    expect(screen.getByText("soporte@syntax.local")).toBeInTheDocument();
    expect(screen.queryByText("33333333-3333-3333-3333-333333333333")).not.toBeInTheDocument();
  });

  it("sin responsable muestra 'Sin asignar'", () => {
    const ticket = ticketFixture({ assignee_id: null, assignee_email: null });
    renderWithIntl(<TicketHeader ticket={ticket} />);

    expect(screen.getByText(/sin asignar/i)).toBeInTheDocument();
  });

  it("responsable con id pero sin email resuelto (usuario eliminado) no muestra el UUID", () => {
    const ticket = ticketFixture({
      assignee_id: "33333333-3333-3333-3333-333333333333",
      assignee_email: null,
    });
    renderWithIntl(<TicketHeader ticket={ticket} />);

    expect(screen.getByText(/usuario eliminado/i)).toBeInTheDocument();
    expect(screen.queryByText("33333333-3333-3333-3333-333333333333")).not.toBeInTheDocument();
  });
});
