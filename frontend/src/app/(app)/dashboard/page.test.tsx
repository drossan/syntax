import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import DashboardPage from "@/app/(app)/dashboard/page";
import { meFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import { renderWithSession, SESSION_BASE } from "@/test/render-with-session";

describe("Dashboard page (/dashboard)", () => {
  it("con analytics.read muestra el panel", async () => {
    server.use(
      http.get(`${SESSION_BASE}/api/v1/analytics/summary`, () =>
        HttpResponse.json({ tickets_by_status: { open: 1 }, approvals_pending: 0, avg_confidence: null, sla_breaches: 0 }),
      ),
    );
    renderWithSession(<DashboardPage />, {
      me: meFixture({ capabilities: [{ capability: "analytics.read", scope: "tenant" }] }),
    });
    expect(await screen.findByRole("heading", { name: /panel/i })).toBeInTheDocument();
  });

  it("sin analytics.read recibe acceso denegado", async () => {
    renderWithSession(<DashboardPage />, {
      me: meFixture({ capabilities: [{ capability: "ticket.read", scope: "tenant" }] }),
    });
    expect(await screen.findByRole("heading", { name: /acceso denegado/i })).toBeInTheDocument();
  });
});
