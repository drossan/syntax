import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { AuthProvider } from "@/features/auth/auth-context";
import { agentRunFixture, meFixture, tokenFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import { SESSION_BASE } from "@/test/render-with-session";

import { useActiveAgentRun, useAgentRun } from "./use-agent-draft";

const TICKET_ID = "11111111-1111-1111-1111-111111111111";
const RUN_ID = "66666666-6666-6666-6666-666666666666";
const RUN = `${SESSION_BASE}/api/v1/agent-runs/${RUN_ID}`;
const ACTIVE_RUN = `${SESSION_BASE}/api/v1/tickets/${TICKET_ID}/agent-runs/active`;

function makeWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  server.use(
    http.post(`${SESSION_BASE}/api/v1/auth/refresh`, () => HttpResponse.json(tokenFixture())),
    http.get(`${SESSION_BASE}/api/v1/auth/me`, () => HttpResponse.json(meFixture())),
  );
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <AuthProvider baseUrl={SESSION_BASE}>{children}</AuthProvider>
      </QueryClientProvider>
    );
  };
}

describe("useAgentRun (polling)", () => {
  it("sondea GET /agent-runs/{id} hasta que el run es terminal y luego para", async () => {
    let calls = 0;
    server.use(
      http.get(RUN, () => {
        calls += 1;
        const status = calls >= 3 ? "succeeded" : "running";
        return HttpResponse.json(agentRunFixture({ id: RUN_ID, status, confidence: 0.9 }));
      }),
    );

    const { result } = renderHook(() => useAgentRun(RUN_ID, 10), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.data?.status).toBe("succeeded"), { timeout: 2000 });
    const callsAtTerminal = calls;
    // Tras terminal deja de sondear: el número de llamadas no crece.
    await new Promise((resolve) => setTimeout(resolve, 60));
    expect(calls).toBe(callsAtTerminal);
  });

  it("no se dispara sin runId", async () => {
    const { result } = renderHook(() => useAgentRun(null, 10), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.fetchStatus).toBe("idle"));
    expect(result.current.data).toBeUndefined();
  });
});

describe("useActiveAgentRun (descubrimiento)", () => {
  it("devuelve null cuando no hay ningún run activo para el ticket", async () => {
    server.use(http.get(ACTIVE_RUN, () => HttpResponse.json(null)));

    const { result } = renderHook(() => useActiveAgentRun(TICKET_ID), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toBeNull();
  });

  it("descubre un run que disparó el servidor (ai_auto_draft), no este cliente", async () => {
    server.use(
      http.get(ACTIVE_RUN, () =>
        HttpResponse.json(agentRunFixture({ id: RUN_ID, status: "running" })),
      ),
    );

    const { result } = renderHook(() => useActiveAgentRun(TICKET_ID), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.data?.id).toBe(RUN_ID));
  });
});
