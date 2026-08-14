import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { approvalPageFixture, approvalTaskFixture, meFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import { renderWithSession, SESSION_BASE } from "@/test/render-with-session";

import { ApprovalsQueue } from "./approvals-queue";

const APPROVALS = `${SESSION_BASE}/api/v1/approvals`;

const supportMe = meFixture({
  capabilities: [{ capability: "approval.decide", scope: "global" }],
});

let lastQuery: Record<string, string> = {};
afterEach(() => {
  lastQuery = {};
});

function serveApprovals(items: ReturnType<typeof approvalTaskFixture>[]) {
  server.use(
    http.get(APPROVALS, ({ request }) => {
      lastQuery = Object.fromEntries(new URL(request.url).searchParams);
      return HttpResponse.json(approvalPageFixture(items));
    }),
  );
}

const a = approvalTaskFixture({ id: "a", ticket_id: "t-a", draft_body: "Draft A" });
const b = approvalTaskFixture({ id: "b", ticket_id: "t-b", draft_body: "Draft B" });

describe("ApprovalsQueue", () => {
  it("renderiza en el orden recibido y pide el orden por política", async () => {
    serveApprovals([a, b]);
    renderWithSession(<ApprovalsQueue />, { me: supportMe });

    await screen.findByText("Draft A");
    const items = screen.getAllByRole("listitem");
    expect(within(items[0]!).getByText("Draft A")).toBeInTheDocument();
    expect(within(items[1]!).getByText("Draft B")).toBeInTheDocument();
    expect(lastQuery.sort).toBe("sla_due,confidence");
    expect(lastQuery.status).toBe("pending");
  });

  it("desempate estable: el orden recibido se conserva tal cual (no re-ordena)", async () => {
    serveApprovals([b, a]); // el server ya desempató; el cliente no reordena
    renderWithSession(<ApprovalsQueue />, { me: supportMe });

    await screen.findByText("Draft B");
    const items = screen.getAllByRole("listitem");
    expect(within(items[0]!).getByText("Draft B")).toBeInTheDocument();
    expect(within(items[1]!).getByText("Draft A")).toBeInTheDocument();
  });

  it("cola vacía → estado vacío", async () => {
    serveApprovals([]);
    renderWithSession(<ApprovalsQueue />, { me: supportMe });

    expect(await screen.findByText(/no hay aprobaciones pendientes/i)).toBeInTheDocument();
  });

  it("error → aviso con reintento", async () => {
    server.use(
      http.get(APPROVALS, () =>
        HttpResponse.json({ type: "about:blank", title: "Error de cola", status: 500 }, { status: 500 }),
      ),
    );
    renderWithSession(<ApprovalsQueue />, { me: supportMe });

    const alert = await screen.findByRole("alert");
    serveApprovals([a]);
    await userEvent.click(within(alert).getByRole("button", { name: /reintentar/i }));
    await screen.findByText("Draft A");
  });

  it("una aprobación resuelta por otro agente desaparece tras refrescar", async () => {
    serveApprovals([a, b]);
    renderWithSession(<ApprovalsQueue />, { me: supportMe });
    await screen.findByText("Draft A");

    serveApprovals([b]); // A ya fue resuelta por otro agente
    await userEvent.click(screen.getByRole("button", { name: /actualizar/i }));

    await waitFor(() => expect(screen.queryByText("Draft A")).not.toBeInTheDocument());
    expect(screen.getByText("Draft B")).toBeInTheDocument();
  });
});
