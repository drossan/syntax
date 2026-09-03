import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { messageFixture } from "@/mocks/fixtures";
import { renderWithIntl } from "@/test/render-with-intl";

import { TicketTimeline } from "./ticket-timeline";

describe("TicketTimeline", () => {
  it("muestra los eventos en orden cronológico con el email de su actor, no el UUID", () => {
    const later = messageFixture({
      id: "b",
      author_id: "22222222-2222-2222-2222-222222222222",
      author_email: "agente-2@syntax.local",
      created_at: "2026-08-13T12:00:00Z",
    });
    const earlier = messageFixture({
      id: "a",
      author_id: "11111111-1111-1111-1111-111111111111",
      author_email: "agente-1@syntax.local",
      created_at: "2026-08-13T09:00:00Z",
    });

    renderWithIntl(<TicketTimeline messages={[later, earlier]} canSeeInternal />);

    const items = screen.getAllByRole("listitem");
    expect(within(items[0]!).getByText("agente-1@syntax.local")).toBeInTheDocument();
    expect(within(items[1]!).getByText("agente-2@syntax.local")).toBeInTheDocument();
    expect(within(items[0]!).getByText(/2026/)).toBeInTheDocument();
    expect(screen.queryByText(/11111111-1111/)).not.toBeInTheDocument();
  });

  it("sin actividad muestra el estado vacío", () => {
    renderWithIntl(<TicketTimeline messages={[]} canSeeInternal />);
    expect(screen.getByText(/sin actividad/i)).toBeInTheDocument();
  });
});
