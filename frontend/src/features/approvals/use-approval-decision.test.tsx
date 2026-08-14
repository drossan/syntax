import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { AuthProvider } from "@/features/auth/auth-context";
import { approvalTaskFixture, meFixture, tokenFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import { SESSION_BASE } from "@/test/render-with-session";

import { useApproveApproval, useEditApproval, useRejectApproval } from "./use-approval-decision";

const ID = "55555555-5555-5555-5555-555555555555";
const BASE = `${SESSION_BASE}/api/v1/approvals/${ID}`;

function setup<M>(hook: () => M) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
  server.use(
    http.post(`${SESSION_BASE}/api/v1/auth/refresh`, () => HttpResponse.json(tokenFixture())),
    http.get(`${SESSION_BASE}/api/v1/auth/me`, () => HttpResponse.json(meFixture())),
  );
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <AuthProvider baseUrl={SESSION_BASE}>{children}</AuthProvider>
    </QueryClientProvider>
  );
  return { invalidateSpy, ...renderHook(hook, { wrapper }) };
}

describe("decisiones de aprobación (hooks)", () => {
  it("aprobar postea a /approve e invalida cola y ticket", async () => {
    let body: unknown;
    server.use(
      http.post(`${BASE}/approve`, async ({ request }) => {
        body = await request.json().catch(() => null);
        return HttpResponse.json(approvalTaskFixture({ id: ID, status: "approved" }));
      }),
    );
    const { result, invalidateSpy } = setup(() => useApproveApproval(ID));

    await act(async () => {
      await result.current.mutateAsync({ human_note: "ok" });
    });

    expect(body).toStrictEqual({ human_note: "ok" });
    await waitFor(() => expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["approvals"] }));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["ticket"] });
  });

  it("editar postea final_body a /edit", async () => {
    let body: unknown;
    server.use(
      http.post(`${BASE}/edit`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(approvalTaskFixture({ id: ID, status: "edited" }));
      }),
    );
    const { result } = setup(() => useEditApproval(ID));

    await act(async () => {
      await result.current.mutateAsync({ final_body: "texto editado" });
    });

    expect(body).toStrictEqual({ final_body: "texto editado" });
  });

  it("rechazar postea human_note a /reject", async () => {
    let body: unknown;
    server.use(
      http.post(`${BASE}/reject`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(approvalTaskFixture({ id: ID, status: "rejected" }));
      }),
    );
    const { result } = setup(() => useRejectApproval(ID));

    await act(async () => {
      await result.current.mutateAsync({ human_note: "no procede" });
    });

    expect(body).toStrictEqual({ human_note: "no procede" });
  });

  it("propaga el 409 (doble decisión) como error y no invalida", async () => {
    server.use(
      http.post(`${BASE}/approve`, () =>
        HttpResponse.json({ type: "about:blank", title: "Ya resuelta", status: 409 }, { status: 409 }),
      ),
    );
    const { result, invalidateSpy } = setup(() => useApproveApproval(ID));

    await expect(result.current.mutateAsync(undefined)).rejects.toMatchObject({ status: 409 });
    expect(invalidateSpy).not.toHaveBeenCalled();
  });
});
