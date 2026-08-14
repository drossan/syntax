import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { AuthProvider } from "@/features/auth/auth-context";
import { TenantProvider } from "@/features/tenant/tenant-context";
import { meFixture, messagePageFixture, ticketFixture, tokenFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import { SESSION_BASE } from "@/test/render-with-session";

import { ticketKey, ticketMessagesKey, useTicket, useTicketMessages } from "./use-ticket";

const ID = "11111111-1111-1111-1111-111111111111";

function makeWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  server.use(
    http.post(`${SESSION_BASE}/api/v1/auth/refresh`, () => HttpResponse.json(tokenFixture())),
    http.get(`${SESSION_BASE}/api/v1/auth/me`, () => HttpResponse.json(meFixture())),
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

describe("useTicket", () => {
  it("pide GET /tickets/{id} con el id en la ruta y devuelve el ticket", async () => {
    let url = "";
    server.use(
      http.get(`${SESSION_BASE}/api/v1/tickets/:id`, ({ request }) => {
        url = request.url;
        return HttpResponse.json(ticketFixture({ id: ID }));
      }),
    );

    const { result } = renderHook(() => useTicket(ID), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.id).toBe(ID);
    expect(url).toContain(`/tickets/${ID}`);
  });

  it("propaga el error (isError) ante un 404", async () => {
    server.use(
      http.get(`${SESSION_BASE}/api/v1/tickets/:id`, () =>
        HttpResponse.json({ type: "about:blank", title: "No encontrado", status: 404 }, { status: 404 }),
      ),
    );

    const { result } = renderHook(() => useTicket(ID), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe("useTicketMessages", () => {
  it("pide GET /tickets/{id}/messages con page_size=100 y devuelve los items", async () => {
    let url = "";
    server.use(
      http.get(`${SESSION_BASE}/api/v1/tickets/:id/messages`, ({ request }) => {
        url = request.url;
        return HttpResponse.json(messagePageFixture());
      }),
    );

    const { result } = renderHook(() => useTicketMessages(ID), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
    expect(url).toContain(`/tickets/${ID}/messages`);
    expect(url).toContain("page_size=100");
  });

  it("propaga el error (isError) ante un fallo del hilo", async () => {
    server.use(
      http.get(`${SESSION_BASE}/api/v1/tickets/:id/messages`, () =>
        HttpResponse.json({ type: "about:blank", title: "Error", status: 500 }, { status: 500 }),
      ),
    );

    const { result } = renderHook(() => useTicketMessages(ID), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe("claves de caché", () => {
  it("ticketKey aísla por tenant e id", () => {
    expect(ticketKey("t1", ID)).toEqual(["ticket", "t1", ID]);
    expect(ticketKey("t1", ID)).not.toEqual(ticketKey("t2", ID));
  });

  it("ticketMessagesKey añade el segmento 'messages'", () => {
    expect(ticketMessagesKey("t1", ID)).toEqual(["ticket", "t1", ID, "messages"]);
    expect(ticketMessagesKey("t1", ID)).not.toEqual(ticketKey("t1", ID));
  });
});
