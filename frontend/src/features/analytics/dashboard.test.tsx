import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { meFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import { renderWithSession, SESSION_BASE } from "@/test/render-with-session";

import { Dashboard } from "./dashboard";

const SUMMARY = `${SESSION_BASE}/api/v1/analytics/summary`;
const me = meFixture({ capabilities: [{ capability: "analytics.read", scope: "tenant" }] });

describe("Dashboard", () => {
  it("muestra las métricas del summary (tickets, aprobaciones, SLA, confianza)", async () => {
    server.use(
      http.get(SUMMARY, () =>
        HttpResponse.json({
          tickets_by_status: { open: 4, pending: 2, closed: 6 },
          approvals_pending: 3,
          avg_confidence: 0.82,
          sla_breaches: 1,
        }),
      ),
    );
    renderWithSession(<Dashboard />, { me });

    // Total de tickets = 12
    expect(await screen.findByText("12")).toBeInTheDocument();
    // Aprobaciones pendientes
    const approvals = screen.getByRole("group", { name: /aprobaciones pendientes/i });
    expect(approvals).toHaveTextContent("3");
    // SLA en riesgo
    expect(screen.getByRole("group", { name: /sla/i })).toHaveTextContent("1");
    // Confianza media 82%
    expect(screen.getByText(/82/)).toBeInTheDocument();
    // El desglose por estado usa las etiquetas traducidas, no la clave cruda del backend.
    expect(screen.getByText("Abierto")).toBeInTheDocument();
    expect(screen.queryByText("open")).not.toBeInTheDocument();
  });

  it("estado vacío cuando el tenant no tiene actividad", async () => {
    server.use(
      http.get(SUMMARY, () =>
        HttpResponse.json({ tickets_by_status: {}, approvals_pending: 0, avg_confidence: null, sla_breaches: 0 }),
      ),
    );
    renderWithSession(<Dashboard />, { me });

    expect(await screen.findByText(/sin actividad/i)).toBeInTheDocument();
  });

  it("estado de error con reintento", async () => {
    server.use(
      http.get(SUMMARY, () =>
        HttpResponse.json({ type: "about:blank", title: "boom", status: 500 }, { status: 500 }),
      ),
    );
    renderWithSession(<Dashboard />, { me });

    const alert = await screen.findByRole("alert");
    expect(alert).toBeInTheDocument();
  });
});
