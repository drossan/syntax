import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { agentRunFixture, meFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import { renderWithSession, SESSION_BASE } from "@/test/render-with-session";
import type { components } from "@/types/api";

import { AiDraftPanel } from "./ai-draft-panel";

type AgentRunStatus = components["schemas"]["AgentRunStatus"];

const TICKET_ID = "t-1";
const RUN_ID = "run-1";
const DRAFT = `${SESSION_BASE}/api/v1/tickets/${TICKET_ID}/ai-draft`;
const RUN = `${SESSION_BASE}/api/v1/agent-runs/${RUN_ID}`;

const me = meFixture({ capabilities: [{ capability: "agent.trigger", scope: "tenant" }] });

let posts = 0;
afterEach(() => {
  posts = 0;
});

function serveTrigger(status: AgentRunStatus = "running") {
  server.use(
    http.post(DRAFT, () => {
      posts += 1;
      return HttpResponse.json(agentRunFixture({ id: RUN_ID, status }), { status: 202 });
    }),
  );
}

describe("AiDraftPanel", () => {
  it("done: el draft llega a 'succeeded' y muestra fuentes y confianza", async () => {
    serveTrigger();
    server.use(
      http.get(RUN, () =>
        HttpResponse.json(
          agentRunFixture({
            id: RUN_ID,
            status: "succeeded",
            confidence: 0.9,
            sources: [{ uc_id: "UC-API-081", title: "Publicar el sitio", section_type: "howto", source_url: "u", score: 0.8 }],
          }),
        ),
      ),
    );

    renderWithSession(<AiDraftPanel ticketId={TICKET_ID} pollMs={10} />, { me });
    await userEvent.click(await screen.findByRole("button", { name: /generar borrador/i }));

    expect(await screen.findByText("UC-API-081")).toBeInTheDocument();
    expect(screen.getByText(/90/)).toBeInTheDocument();
  });

  it("failed: muestra el error y permite reintentar", async () => {
    serveTrigger();
    server.use(
      http.get(RUN, () =>
        HttpResponse.json(agentRunFixture({ id: RUN_ID, status: "failed", error: "El grafo falló" })),
      ),
    );

    renderWithSession(<AiDraftPanel ticketId={TICKET_ID} pollMs={10} />, { me });
    await userEvent.click(await screen.findByRole("button", { name: /generar borrador/i }));

    expect(await screen.findByText(/el grafo falló/i)).toBeInTheDocument();
    const retry = screen.getByRole("button", { name: /reintentar/i });
    await userEvent.click(retry);
    await waitFor(() => expect(posts).toBe(2));
  });

  it("running: muestra 'generando' (live region) y no ofrece re-disparar (idempotencia)", async () => {
    serveTrigger();
    server.use(http.get(RUN, () => HttpResponse.json(agentRunFixture({ id: RUN_ID, status: "running" }))));

    renderWithSession(<AiDraftPanel ticketId={TICKET_ID} pollMs={10} />, { me });
    await userEvent.click(await screen.findByRole("button", { name: /generar borrador/i }));

    expect(await screen.findByText(/generando/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /generar borrador|reintentar/i })).not.toBeInTheDocument();
  });

  it("sin capacidad agent.trigger no ofrece generar", async () => {
    renderWithSession(<AiDraftPanel ticketId={TICKET_ID} />, {
      me: meFixture({ capabilities: [{ capability: "ticket.read", scope: "tenant" }] }),
    });

    // El panel se renderiza (título siempre presente) pero no ofrece el botón de generar.
    await screen.findByRole("heading", { name: /borrador ia/i });
    expect(screen.queryByRole("button", { name: /generar borrador/i })).not.toBeInTheDocument();
  });
});
