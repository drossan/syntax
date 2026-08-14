import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { AuthProvider } from "@/features/auth/auth-context";
import { meFixture, tokenFixture, userFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import { SESSION_BASE } from "@/test/render-with-session";

import { useCreateTenant, useInviteUser, useRoles, useUpdateUser, useUsers } from "./use-admin";

const API = `${SESSION_BASE}/api/v1`;

function setup<M>(hook: () => M) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
  server.use(
    http.post(`${API}/auth/refresh`, () => HttpResponse.json(tokenFixture())),
    http.get(`${API}/auth/me`, () => HttpResponse.json(meFixture())),
  );
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <AuthProvider baseUrl={SESSION_BASE}>{children}</AuthProvider>
    </QueryClientProvider>
  );
  return { invalidateSpy, ...renderHook(hook, { wrapper }) };
}

describe("useUsers / useRoles", () => {
  it("useUsers lee /admin/users y devuelve items", async () => {
    server.use(
      http.get(`${API}/admin/users`, () =>
        HttpResponse.json({ items: [userFixture({ id: "u1" })], page: 1, page_size: 20, total: 1 }),
      ),
    );
    const { result } = setup(() => useUsers());
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.[0]?.id).toBe("u1");
  });

  it("useRoles lee /admin/roles", async () => {
    server.use(
      http.get(`${API}/admin/roles`, () =>
        HttpResponse.json([{ id: "r1", name: "client_agent", kind: "system", tenant_id: null, capabilities: [] }]),
      ),
    );
    const { result } = setup(() => useRoles());
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.[0]?.id).toBe("r1");
  });
});

describe("useCreateTenant", () => {
  it("postea el body a /admin/tenants e invalida el listado de tenants", async () => {
    let body: unknown;
    server.use(
      http.post(`${API}/admin/tenants`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ id: "t", slug: "acme", name: "Acme", status: "active" }, { status: 201 });
      }),
    );
    const { result, invalidateSpy } = setup(() => useCreateTenant());
    await act(async () => {
      await result.current.mutateAsync({ slug: "acme", name: "Acme" });
    });
    expect(body).toStrictEqual({ slug: "acme", name: "Acme" });
    await waitFor(() => expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["admin", "tenants"] }));
  });
});

describe("useInviteUser", () => {
  it("postea la invitación a /admin/users e invalida el listado de usuarios", async () => {
    let body: unknown;
    server.use(
      http.post(`${API}/admin/users`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(userFixture({ id: "u", status: "invited" }), { status: 201 });
      }),
    );
    const { result, invalidateSpy } = setup(() => useInviteUser());
    await act(async () => {
      await result.current.mutateAsync({ email: "a@b.io", roles: ["r1"] });
    });
    expect(body).toStrictEqual({ email: "a@b.io", roles: ["r1"] });
    await waitFor(() => expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["admin", "users"] }));
  });
});

describe("useUpdateUser", () => {
  it("hace PATCH /admin/users/{id} con el status e invalida usuarios", async () => {
    let body: unknown;
    let url = "";
    server.use(
      http.patch(`${API}/admin/users/:id`, async ({ request }) => {
        url = request.url;
        body = await request.json();
        return HttpResponse.json(userFixture({ id: "u9", status: "disabled" }));
      }),
    );
    const { result, invalidateSpy } = setup(() => useUpdateUser());
    await act(async () => {
      await result.current.mutateAsync({ id: "u9", status: "disabled" });
    });
    expect(url).toContain("/admin/users/u9");
    expect(body).toStrictEqual({ status: "disabled" });
    await waitFor(() => expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["admin", "users"] }));
  });

  it("propaga el error (403) sin invalidar", async () => {
    server.use(
      http.patch(`${API}/admin/users/:id`, () =>
        HttpResponse.json({ type: "about:blank", title: "Denegado", status: 403 }, { status: 403 }),
      ),
    );
    const { result, invalidateSpy } = setup(() => useUpdateUser());
    await expect(result.current.mutateAsync({ id: "x", status: "disabled" })).rejects.toMatchObject({
      status: 403,
    });
    expect(invalidateSpy).not.toHaveBeenCalled();
  });
});
