import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { AuthProvider } from "@/features/auth/auth-context";
import { meFixture, ticketFixture, tokenFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import { SESSION_BASE } from "@/test/render-with-session";

import { useCreateTicket } from "./use-create-ticket";

const TICKETS = `${SESSION_BASE}/api/v1/tickets`;

/** Wrapper con QueryClient + sesión autenticada para probar el hook de mutación. */
function makeWrapper(queryClient: QueryClient) {
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

describe("useCreateTicket", () => {
  it("postea el body a /tickets, devuelve el ticket e invalida la lista en éxito", async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    let capturedBody: unknown;
    server.use(
      http.post(TICKETS, async ({ request }) => {
        capturedBody = await request.json();
        return HttpResponse.json(ticketFixture({ id: "t-9" }), { status: 201 });
      }),
    );

    const { result } = renderHook(() => useCreateTicket(), { wrapper: makeWrapper(queryClient) });

    let created: { id?: string } = {};
    await act(async () => {
      created = await result.current.mutateAsync({ subject: "S", priority: "normal", body: "B" });
    });

    expect(capturedBody).toStrictEqual({ subject: "S", priority: "normal", body: "B" });
    expect(created.id).toBe("t-9");
    await waitFor(() => expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["tickets"] }));
  });

  it("propaga el envelope de error (rechaza) ante un 422 y no invalida", async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    server.use(
      http.post(TICKETS, () =>
        HttpResponse.json({ type: "about:blank", title: "Inválido", status: 422 }, { status: 422 }),
      ),
    );

    const { result } = renderHook(() => useCreateTicket(), { wrapper: makeWrapper(queryClient) });

    await expect(
      result.current.mutateAsync({ subject: "S", priority: "normal" }),
    ).rejects.toMatchObject({ status: 422, title: "Inválido" });
    expect(invalidateSpy).not.toHaveBeenCalled();
  });
});
