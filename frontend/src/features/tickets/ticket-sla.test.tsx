import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderWithIntl } from "@/test/render-with-intl";

import { TicketSla } from "./ticket-sla";

const NOW = Date.parse("2026-08-13T12:00:00Z");

describe("TicketSla", () => {
  it("SLA aún no vencido: muestra el plazo (fecha límite) y no aparece como vencido", () => {
    renderWithIntl(<TicketSla slaDue="2026-08-14T12:00:00Z" now={NOW} />);

    expect(screen.getByText(/2026/)).toBeInTheDocument();
    expect(screen.queryByText("Vencido")).not.toBeInTheDocument();
  });

  it("SLA vencido: el indicador se muestra como vencido", () => {
    renderWithIntl(<TicketSla slaDue="2026-08-13T11:00:00Z" now={NOW} />);

    expect(screen.getByText("Vencido")).toBeInTheDocument();
  });

  it("sin SLA: muestra que no hay SLA", () => {
    renderWithIntl(<TicketSla slaDue={null} now={NOW} />);

    expect(screen.getByText(/sin sla/i)).toBeInTheDocument();
  });
});
