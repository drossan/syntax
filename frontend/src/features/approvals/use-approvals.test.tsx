import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { AuthProvider } from "@/features/auth/auth-context";
import { TenantProvider } from "@/features/tenant/tenant-context";
import { approvalPageFixture, meFixture, tokenFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import { SESSION_BASE } from "@/test/render-with-session";

import { useApprovals } from "./use-approvals";

const APPROVALS = `${SESSION_BASE}/api/v1/approvals`;

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

describe("useApprovals", () => {
  it("pide GET /approvals y devuelve la página", async () => {
    server.use(http.get(APPROVALS, () => HttpResponse.json(approvalPageFixture())));

    const { result } = renderHook(() => useApprovals(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items).toHaveLength(1);
  });

  it("propaga el error (isError) ante un fallo del servidor", async () => {
    server.use(
      http.get(APPROVALS, () =>
        HttpResponse.json(
          { type: "about:blank", title: "Error de cola", status: 500 },
          { status: 500 },
        ),
      ),
    );

    const { result } = renderHook(() => useApprovals(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
