import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { messageFixture } from "@/mocks/fixtures";
import { renderWithIntl } from "@/test/render-with-intl";

import { TicketTimeline } from "./ticket-timeline";

describe("TicketTimeline", () => {
  it("muestra los eventos en orden cronológico con su actor", () => {
    const later = messageFixture({ id: "b", author_id: "agente-2", created_at: "2026-08-13T12:00:00Z" });
    const earlier = messageFixture({ id: "a", author_id: "agente-1", created_at: "2026-08-13T09:00:00Z" });

    renderWithIntl(<TicketTimeline messages={[later, earlier]} canSeeInternal />);

    const items = screen.getAllByRole("listitem");
    expect(within(items[0]!).getByText(/agente-1/)).toBeInTheDocument();
    expect(within(items[1]!).getByText(/agente-2/)).toBeInTheDocument();
    expect(within(items[0]!).getByText(/2026/)).toBeInTheDocument();
  });

  it("sin actividad muestra el estado vacío", () => {
    renderWithIntl(<TicketTimeline messages={[]} canSeeInternal />);
    expect(screen.getByText(/sin actividad/i)).toBeInTheDocument();
  });
});
