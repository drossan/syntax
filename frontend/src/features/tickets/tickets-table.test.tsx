import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ticketFixture } from "@/mocks/fixtures";
import { renderWithIntl } from "@/test/render-with-intl";

import { TicketsTable } from "./tickets-table";

describe("TicketsTable", () => {
  it("la columna de responsable muestra su email, no el UUID", () => {
    const ticket = ticketFixture({
      assignee_id: "33333333-3333-3333-3333-333333333333",
      assignee_email: "soporte@syntax.local",
    });
    renderWithIntl(<TicketsTable tickets={[ticket]} caption="Bandeja" />);

    expect(screen.getByText("soporte@syntax.local")).toBeInTheDocument();
    expect(screen.queryByText("33333333-3333-3333-3333-333333333333")).not.toBeInTheDocument();
  });

  it("sin responsable muestra 'Sin asignar'", () => {
    const ticket = ticketFixture({ assignee_id: null, assignee_email: null });
    renderWithIntl(<TicketsTable tickets={[ticket]} caption="Bandeja" />);

    expect(screen.getByText(/sin asignar/i)).toBeInTheDocument();
  });

  it("responsable con id pero sin email resuelto (usuario eliminado) no muestra el UUID", () => {
    const ticket = ticketFixture({
      assignee_id: "33333333-3333-3333-3333-333333333333",
      assignee_email: null,
    });
    renderWithIntl(<TicketsTable tickets={[ticket]} caption="Bandeja" />);

    expect(screen.getByText(/usuario eliminado/i)).toBeInTheDocument();
    expect(screen.queryByText("33333333-3333-3333-3333-333333333333")).not.toBeInTheDocument();
  });
});
