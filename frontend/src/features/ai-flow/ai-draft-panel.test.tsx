import { QueryClient } from "@tanstack/react-query";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { agentRunFixture, meFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import { renderWithSession, SESSION_BASE, wrapWithSession } from "@/test/render-with-session";
import type { components } from "@/types/api";

import { AiDraftPanel } from "./ai-draft-panel";

type AgentRunStatus = components["schemas"]["AgentRunStatus"];

const TICKET_ID = "t-1";
const RUN_ID = "run-1";
const DRAFT = `${SESSION_BASE}/api/v1/tickets/${TICKET_ID}/ai-draft`;
const RUN = `${SESSION_BASE}/api/v1/agent-runs/${RUN_ID}`;
const ACTIVE_RUN = `${SESSION_BASE}/api/v1/tickets/${TICKET_ID}/agent-runs/active`;

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
  it("done: el draft llega a 'succeeded' y muestra fuentes, confianza y el enlace de traza", async () => {
    serveTrigger();
    server.use(
      http.get(RUN, () =>
        HttpResponse.json(
          agentRunFixture({
            id: RUN_ID,
            status: "succeeded",
            confidence: 0.9,
            sources: [
              {
                uc_id: "UC-API-081",
                title: "Publicar el sitio",
                section_type: "howto",
                source_url: "u",
                score: 0.8,
              },
            ],
            langsmith_trace_url: "https://smith.langchain.com/run-1",
          }),
        ),
      ),
    );

    renderWithSession(<AiDraftPanel ticketId={TICKET_ID} pollMs={10} />, { me });
    await userEvent.click(await screen.findByRole("button", { name: /generar borrador/i }));

    expect(await screen.findByText("UC-API-081")).toBeInTheDocument();
    expect(screen.getByText(/90/)).toBeInTheDocument();
    const trace = screen.getByRole("link", { name: /ver traza/i });
    expect(trace).toHaveAttribute("href", "https://smith.langchain.com/run-1");
  });

  it("done: sin fuentes, sin confianza y sin traza, no muestra esas secciones", async () => {
    serveTrigger();
    server.use(
      http.get(RUN, () => HttpResponse.json(agentRunFixture({ id: RUN_ID, status: "succeeded" }))),
    );

    renderWithSession(<AiDraftPanel ticketId={TICKET_ID} pollMs={10} />, { me });
    await userEvent.click(await screen.findByRole("button", { name: /generar borrador/i }));

    await screen.findByText(/borrador listo/i);
    expect(screen.queryByText(/fuentes/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/confianza/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /ver traza/i })).not.toBeInTheDocument();
  });

  it("failed: muestra el error y permite reintentar", async () => {
    serveTrigger();
    server.use(
      http.get(RUN, () =>
        HttpResponse.json(
          agentRunFixture({ id: RUN_ID, status: "failed", error: "El grafo falló" }),
        ),
      ),
    );

    renderWithSession(<AiDraftPanel ticketId={TICKET_ID} pollMs={10} />, { me });
    await userEvent.click(await screen.findByRole("button", { name: /generar borrador/i }));

    expect(await screen.findByText(/el grafo falló/i)).toBeInTheDocument();
    const retry = screen.getByRole("button", { name: /reintentar/i });
    await userEvent.click(retry);
    await waitFor(() => expect(posts).toBe(2));
  });

  it("failed: sin mensaje de error del servidor, usa el texto genérico", async () => {
    serveTrigger();
    server.use(
      http.get(RUN, () =>
        HttpResponse.json(agentRunFixture({ id: RUN_ID, status: "failed", error: null })),
      ),
    );

    renderWithSession(<AiDraftPanel ticketId={TICKET_ID} pollMs={10} />, { me });
    await userEvent.click(await screen.findByRole("button", { name: /generar borrador/i }));

    expect(await screen.findByText(/la generación falló/i)).toBeInTheDocument();
  });

  it("running: muestra 'generando' (live region) y no ofrece re-disparar (idempotencia)", async () => {
    serveTrigger();
    server.use(
      http.get(RUN, () => HttpResponse.json(agentRunFixture({ id: RUN_ID, status: "running" }))),
    );

    renderWithSession(<AiDraftPanel ticketId={TICKET_ID} pollMs={10} />, { me });
    await userEvent.click(await screen.findByRole("button", { name: /generar borrador/i }));

    expect(await screen.findByText(/generando/i)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /generar borrador|reintentar/i }),
    ).not.toBeInTheDocument();
  });

  it("running + escalated=true: muestra 'esperando aprobación', NO 'generando' para siempre", async () => {
    serveTrigger();
    let runCalls = 0;
    server.use(
      http.get(RUN, () => {
        runCalls += 1;
        return HttpResponse.json(
          agentRunFixture({ id: RUN_ID, status: "running", escalated: true }),
        );
      }),
    );

    renderWithSession(<AiDraftPanel ticketId={TICKET_ID} pollMs={10} />, { me });
    await userEvent.click(await screen.findByRole("button", { name: /generar borrador/i }));

    expect(await screen.findByText(/esperando aprobación/i)).toBeInTheDocument();
    expect(screen.queryByText(/^generando/i)).not.toBeInTheDocument();
    // También deja de sondear (draftPollInterval=false): el nº de GETs no sigue creciendo.
    const callsAtAwaiting = runCalls;
    await new Promise((resolve) => setTimeout(resolve, 60));
    expect(runCalls).toBe(callsAtAwaiting);
  });

  it("running + escalated=true, sin approval.decide: no ofrece enlace a la cola de aprobaciones", async () => {
    serveTrigger();
    server.use(
      http.get(RUN, () =>
        HttpResponse.json(agentRunFixture({ id: RUN_ID, status: "running", escalated: true })),
      ),
    );

    renderWithSession(<AiDraftPanel ticketId={TICKET_ID} pollMs={10} />, { me });
    await userEvent.click(await screen.findByRole("button", { name: /generar borrador/i }));

    await screen.findByText(/esperando aprobación/i);
    expect(screen.queryByRole("link", { name: /cola de aprobaciones/i })).not.toBeInTheDocument();
  });

  it("running + escalated=true, CON approval.decide: enlaza a la cola de aprobaciones", async () => {
    const decider = meFixture({
      capabilities: [
        { capability: "agent.trigger", scope: "tenant" },
        { capability: "approval.decide", scope: "global" },
      ],
    });
    serveTrigger();
    server.use(
      http.get(RUN, () =>
        HttpResponse.json(agentRunFixture({ id: RUN_ID, status: "running", escalated: true })),
      ),
    );

    renderWithSession(<AiDraftPanel ticketId={TICKET_ID} pollMs={10} />, { me: decider });
    await userEvent.click(await screen.findByRole("button", { name: /generar borrador/i }));

    const link = await screen.findByRole("link", { name: /cola de aprobaciones/i });
    expect(link).toHaveAttribute("href", "/approvals");
  });

  it("ai_auto_draft: descubre un run ya disparado por el servidor SIN que el usuario haga clic", async () => {
    server.use(
      http.get(ACTIVE_RUN, () =>
        HttpResponse.json(agentRunFixture({ id: RUN_ID, status: "running" })),
      ),
      http.get(RUN, () => HttpResponse.json(agentRunFixture({ id: RUN_ID, status: "running" }))),
    );

    renderWithSession(<AiDraftPanel ticketId={TICKET_ID} pollMs={10} />, { me });

    expect(await screen.findByText(/generando/i)).toBeInTheDocument();
    expect(posts).toBe(0); // nunca disparó — solo descubrió el run del servidor
  });

  it("sin capacidad agent.trigger no ofrece generar", async () => {
    renderWithSession(<AiDraftPanel ticketId={TICKET_ID} />, {
      me: meFixture({ capabilities: [{ capability: "ticket.read", scope: "tenant" }] }),
    });

    // El panel se renderiza (título siempre presente) pero no ofrece el botón de generar.
    await screen.findByRole("heading", { name: /borrador ia/i });
    expect(screen.getByRole("region", { name: /borrador ia/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /generar borrador/i })).not.toBeInTheDocument();
  });

  it("descubrimiento en curso: muestra 'comprobando' antes de saber si ya hay un run activo", async () => {
    server.use(
      // Nunca resuelve dentro de la ventana del test — mantiene `stillSearching=true`.
      http.get(ACTIVE_RUN, () => new Promise(() => {})),
    );

    renderWithSession(<AiDraftPanel ticketId={TICKET_ID} pollMs={10} />, { me });

    expect(await screen.findByText(/comprobando/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /generar borrador/i })).not.toBeInTheDocument();
  });

  // ── Invalidación del hilo al llegar a `succeeded` (frontend-ticket-thread-live-refresh-01, CU-FE-06 5a-5e) ──

  function spiedQueryClient() {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return { queryClient, invalidateSpy: vi.spyOn(queryClient, "invalidateQueries") };
  }

  it("succeeded tras un poll 'running' intermedio: invalida la caché del ticket (prefijo)", async () => {
    serveTrigger();
    let calls = 0;
    server.use(
      http.get(RUN, () => {
        calls += 1;
        return HttpResponse.json(
          agentRunFixture({ id: RUN_ID, status: calls > 1 ? "succeeded" : "running" }),
        );
      }),
    );
    const { queryClient, invalidateSpy } = spiedQueryClient();

    renderWithSession(<AiDraftPanel ticketId={TICKET_ID} pollMs={10} />, { me, queryClient });
    await userEvent.click(await screen.findByRole("button", { name: /generar borrador/i }));

    await waitFor(() => expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["ticket"] }));
  });

  it("succeeded YA en el primer poll (sin 'running' intermedio): invalida igual — bug real reproducido contra el backend real (POST /ai-draft corre síncrono, agent.py: 'la respuesta 202 puede llegar con el run ya succeeded')", async () => {
    serveTrigger();
    server.use(
      http.get(RUN, () => HttpResponse.json(agentRunFixture({ id: RUN_ID, status: "succeeded" }))),
    );
    const { queryClient, invalidateSpy } = spiedQueryClient();

    renderWithSession(<AiDraftPanel ticketId={TICKET_ID} pollMs={10} />, { me, queryClient });
    await userEvent.click(await screen.findByRole("button", { name: /generar borrador/i }));

    await waitFor(() => expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["ticket"] }));
  });

  it("failed: NO invalida la caché del ticket", async () => {
    serveTrigger();
    server.use(
      http.get(RUN, () =>
        HttpResponse.json(agentRunFixture({ id: RUN_ID, status: "failed", error: "boom" })),
      ),
    );
    const { queryClient, invalidateSpy } = spiedQueryClient();

    renderWithSession(<AiDraftPanel ticketId={TICKET_ID} pollMs={10} />, { me, queryClient });
    await userEvent.click(await screen.findByRole("button", { name: /generar borrador/i }));

    await screen.findByText(/boom/i);
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: ["ticket"] });
  });

  it("escalated (esperando aprobación humana): NO invalida el hilo todavía", async () => {
    serveTrigger();
    server.use(
      http.get(RUN, () =>
        HttpResponse.json(agentRunFixture({ id: RUN_ID, status: "running", escalated: true })),
      ),
    );
    const { queryClient, invalidateSpy } = spiedQueryClient();

    renderWithSession(<AiDraftPanel ticketId={TICKET_ID} pollMs={10} />, { me, queryClient });
    await userEvent.click(await screen.findByRole("button", { name: /generar borrador/i }));

    await screen.findByText(/esperando aprobación/i);
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: ["ticket"] });
  });

  it("montar con un run ya succeeded (descubierto) no invalida por el simple montaje", async () => {
    server.use(
      http.get(ACTIVE_RUN, () =>
        HttpResponse.json(agentRunFixture({ id: RUN_ID, status: "succeeded" })),
      ),
      http.get(RUN, () => HttpResponse.json(agentRunFixture({ id: RUN_ID, status: "succeeded" }))),
    );
    const { queryClient, invalidateSpy } = spiedQueryClient();

    renderWithSession(<AiDraftPanel ticketId={TICKET_ID} pollMs={10} />, { me, queryClient });

    await screen.findByText(/borrador listo/i);
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: ["ticket"] });
  });

  it("descubierto en 'running' y luego succeeded: invalida igual, aunque nadie de este cliente lo disparó", async () => {
    let calls = 0;
    server.use(
      http.get(ACTIVE_RUN, () =>
        HttpResponse.json(agentRunFixture({ id: RUN_ID, status: "running" })),
      ),
      http.get(RUN, () => {
        calls += 1;
        return HttpResponse.json(
          agentRunFixture({ id: RUN_ID, status: calls > 1 ? "succeeded" : "running" }),
        );
      }),
    );
    const { queryClient, invalidateSpy } = spiedQueryClient();

    renderWithSession(<AiDraftPanel ticketId={TICKET_ID} pollMs={10} />, { me, queryClient });
    await screen.findByText(/generando/i);

    await waitFor(() => expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["ticket"] }));
  });

  it("cambiar de ticket sin desmontar resetea la detección: no arrastra el status del ticket anterior", async () => {
    const TICKET_2 = "t-2";
    const RUN_2 = "run-2";
    const RUN_2_URL = `${SESSION_BASE}/api/v1/agent-runs/${RUN_2}`;
    const ACTIVE_RUN_2 = `${SESSION_BASE}/api/v1/tickets/${TICKET_2}/agent-runs/active`;
    serveTrigger("failed");
    server.use(
      http.get(RUN, () =>
        HttpResponse.json(agentRunFixture({ id: RUN_ID, status: "failed", error: "boom" })),
      ),
      // Ticket 2: un run YA succeeded desde el primer momento (descubierto) — sin este reset, el
      // status "failed" arrastrado del ticket 1 haría que esta lectura pareciera una transición real.
      http.get(ACTIVE_RUN_2, () =>
        HttpResponse.json(agentRunFixture({ id: RUN_2, status: "succeeded" })),
      ),
      http.get(RUN_2_URL, () =>
        HttpResponse.json(agentRunFixture({ id: RUN_2, status: "succeeded" })),
      ),
    );
    const { queryClient, invalidateSpy } = spiedQueryClient();

    const { rerender } = renderWithSession(<AiDraftPanel ticketId={TICKET_ID} pollMs={10} />, {
      me,
      queryClient,
    });
    await userEvent.click(await screen.findByRole("button", { name: /generar borrador/i }));
    await screen.findByText(/boom/i);
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: ["ticket"] });

    // Precarga la caché del ticket 2 como YA resuelta (p.ej. visitado antes en esta sesión) — sin
    // el reset por `ticketId`, la primera lectura para el ticket 2 llegaría de golpe con datos ya en
    // caché (sin el hueco async de "sin datos todavía" que de otro modo enmascararía el fallo).
    queryClient.setQueryData(
      ["agent-run-active", TICKET_2],
      agentRunFixture({
        id: RUN_2,
        status: "succeeded",
      }),
    );
    queryClient.setQueryData(
      ["agent-run", RUN_2],
      agentRunFixture({
        id: RUN_2,
        status: "succeeded",
      }),
    );
    rerender(wrapWithSession(<AiDraftPanel ticketId={TICKET_2} pollMs={10} />, { queryClient }));

    await screen.findByText(/borrador listo/i);
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: ["ticket"] });
  });

  it("reintento tras fallo vuelve a disparar la invalidación igual que el primer intento", async () => {
    serveTrigger("failed");
    server.use(
      http.get(RUN, () =>
        HttpResponse.json(agentRunFixture({ id: RUN_ID, status: "failed", error: "boom" })),
      ),
    );
    const { queryClient, invalidateSpy } = spiedQueryClient();

    renderWithSession(<AiDraftPanel ticketId={TICKET_ID} pollMs={10} />, { me, queryClient });
    await userEvent.click(await screen.findByRole("button", { name: /generar borrador/i }));
    await screen.findByText(/boom/i);
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: ["ticket"] });

    const RETRY_RUN_ID = "run-2";
    const RETRY_RUN_URL = `${SESSION_BASE}/api/v1/agent-runs/${RETRY_RUN_ID}`;
    let retryCalls = 0;
    server.use(
      http.post(DRAFT, () =>
        HttpResponse.json(agentRunFixture({ id: RETRY_RUN_ID, status: "running" }), {
          status: 202,
        }),
      ),
      http.get(RETRY_RUN_URL, () => {
        retryCalls += 1;
        return HttpResponse.json(
          agentRunFixture({ id: RETRY_RUN_ID, status: retryCalls > 1 ? "succeeded" : "running" }),
        );
      }),
    );
    await userEvent.click(screen.getByRole("button", { name: /reintentar/i }));

    await waitFor(() => expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["ticket"] }));
  });
});
