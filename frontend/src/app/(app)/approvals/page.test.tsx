import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import ApprovalsPage from "@/app/(app)/approvals/page";
import { approvalPageFixture, meFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import { renderWithSession, SESSION_BASE } from "@/test/render-with-session";

/** La cola de aprobaciones es solo para Soporte (`approval.decide`); el cliente no accede. */
describe("Approvals page (/approvals)", () => {
  it("con approval.decide muestra la cola", async () => {
    server.use(
      http.get(`${SESSION_BASE}/api/v1/approvals`, () => HttpResponse.json(approvalPageFixture([]))),
    );
    renderWithSession(<ApprovalsPage />, {
      me: meFixture({ capabilities: [{ capability: "approval.decide", scope: "global" }] }),
    });

    expect(await screen.findByRole("heading", { name: /aprobaciones/i })).toBeInTheDocument();
  });

  it("una usuaria cliente (sin approval.decide) recibe acceso denegado", async () => {
    renderWithSession(<ApprovalsPage />, {
      me: meFixture({ capabilities: [{ capability: "ticket.read", scope: "tenant" }] }),
    });

    expect(await screen.findByRole("heading", { name: /acceso denegado/i })).toBeInTheDocument();
  });
});
