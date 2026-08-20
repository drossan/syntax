import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { delay, http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { AuthProvider } from "@/features/auth/auth-context";
import { TenantProvider } from "@/features/tenant/tenant-context";
import { meFixture, ticketFixture, tokenFixture, userFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import { SESSION_BASE } from "@/test/render-with-session";
import type { components } from "@/types/api";

import { ticketKey, useTicket } from "./use-ticket";
import { useAssignTicket, useTransitionTicket, useUpdatePriority } from "./use-ticket-mutations";

type Ticket = components["schemas"]["Ticket"];

const ID = "11111111-1111-1111-1111-111111111111";
const TENANT = "22222222-2222-2222-2222-222222222222";
const TICKET = `${SESSION_BASE}/api/v1/tickets/${ID}`;
const KEY = ticketKey(TENANT, ID);

/** me con tenant conocido (== TENANT) para que `activeTenantId` y la queryKey sean deterministas. */
const me = meFixture({
  user: userFixture(),
  active_tenant_id: TENANT,
  capabilities: [{ capability: "ticket.read", scope: "tenant" }],
});

function makeWrapper(queryClient: QueryClient) {
  server.use(
    http.post(`${SESSION_BASE}/api/v1/auth/refresh`, () => HttpResponse.json(tokenFixture())),
    http.get(`${SESSION_BASE}/api/v1/auth/me`, () => HttpResponse.json(me)),
  );
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <AuthProvider baseUrl={SESSION_BASE}>
          <TenantProvider>{children}</TenantProvider>
        </AuthProvider>
      </QueryClientProvider>
    );
  };
}

/** Renderiza useTicket (siembra la caché) + el hook de mutación dado; espera a que el ticket cargue. */
async function setup<M>(mutationHook: () => M) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const cancelSpy = vi.spyOn(queryClient, "cancelQueries");
  const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
  const { result } = renderHook(() => ({ t: useTicket(ID), m: mutationHook() }), {
    wrapper: makeWrapper(queryClient),
  });
  await waitFor(() => expect(result.current.t.isSuccess).toBe(true));
  return { queryClient, cancelSpy, invalidateSpy, result };
}

describe("useTransitionTicket (optimistic + rollback)", () => {
  it("aplica el cambio optimista, cancela queries en vuelo y revalida al asentar", async () => {
    server.use(
      http.get(TICKET, () => HttpResponse.json(ticketFixture({ id: ID, tenant_id: TENANT, status: "open" }))),
      http.post(`${TICKET}/transition`, async () => {
        await delay(80);
        return HttpResponse.json(ticketFixture({ id: ID, tenant_id: TENANT, status: "pending" }));
      }),
    );

    const { queryClient, cancelSpy, invalidateSpy, result } = await setup(() => useTransitionTicket(ID));

    act(() => result.current.m.mutate("pending"));

    await waitFor(() => expect(queryClient.getQueryData<Ticket>(KEY)?.status).toBe("pending"));
    expect(cancelSpy).toHaveBeenCalledWith({ queryKey: KEY });

    await waitFor(() => expect(result.current.m.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: KEY });
  });

  it("revierte al snapshot anterior cuando el servidor rechaza (409)", async () => {
    server.use(
      http.get(TICKET, () => HttpResponse.json(ticketFixture({ id: ID, tenant_id: TENANT, status: "open" }))),
      http.post(`${TICKET}/transition`, () =>
        HttpResponse.json({ type: "about:blank", title: "Conflicto", status: 409 }, { status: 409 }),
      ),
    );

    const { queryClient, result } = await setup(() => useTransitionTicket(ID));

    await act(async () => {
      await result.current.m.mutateAsync("resolved").catch(() => undefined);
    });

    await waitFor(() => expect(queryClient.getQueryData<Ticket>(KEY)?.status).toBe("open"));
  });
});

describe("useAssignTicket / useUpdatePriority (body y optimismo)", () => {
  it("asignar envía { assignee_id } y aplica el optimismo", async () => {
    let body: unknown;
    server.use(
      http.get(TICKET, () =>
        HttpResponse.json(ticketFixture({ id: ID, tenant_id: TENANT, assignee_id: null })),
      ),
      http.post(`${TICKET}/assign`, async ({ request }) => {
        body = await request.json();
        await delay(80); // observar el optimismo antes de que onSettled revalide
        return HttpResponse.json(ticketFixture({ id: ID, tenant_id: TENANT, assignee_id: "agent-9" }));
      }),
    );

    const { queryClient, result } = await setup(() => useAssignTicket(ID));

    act(() => result.current.m.mutate("agent-9"));

    await waitFor(() => expect(queryClient.getQueryData<Ticket>(KEY)?.assignee_id).toBe("agent-9"));
    await waitFor(() => expect(body).toStrictEqual({ assignee_id: "agent-9" }));
  });

  it("cambiar prioridad envía PATCH { priority } y aplica el optimismo", async () => {
    let body: unknown;
    server.use(
      http.get(TICKET, () =>
        HttpResponse.json(ticketFixture({ id: ID, tenant_id: TENANT, priority: "normal" })),
      ),
      http.patch(TICKET, async ({ request }) => {
        body = await request.json();
        await delay(80); // observar el optimismo antes de que onSettled revalide
        return HttpResponse.json(ticketFixture({ id: ID, tenant_id: TENANT, priority: "high" }));
      }),
    );

    const { queryClient, result } = await setup(() => useUpdatePriority(ID));

    act(() => result.current.m.mutate("high"));

    await waitFor(() => expect(queryClient.getQueryData<Ticket>(KEY)?.priority).toBe("high"));
    await waitFor(() => expect(body).toStrictEqual({ priority: "high" }));
  });
});
