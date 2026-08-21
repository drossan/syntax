import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { AuthProvider } from "@/features/auth/auth-context";
import { meFixture, tenantChoiceFixture, tokenFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";

import { TenantProvider, useTenant } from "./tenant-context";

const BASE = "http://localhost:8000";
const REFRESH = `${BASE}/api/v1/auth/refresh`;
const ME = `${BASE}/api/v1/auth/me`;
const SWITCH_TENANT = `${BASE}/api/v1/auth/switch-tenant`;

function makeWrapper(queryClient: QueryClient, baseUrl = BASE) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <AuthProvider baseUrl={baseUrl}>
          <TenantProvider>{children}</TenantProvider>
        </AuthProvider>
      </QueryClientProvider>
    );
  };
}

/**
 * Escenarios Gherkin (CU-FE-02): `setActiveTenant` es no-op con 1 sola membresía, y solo limpia la
 * caché de Query tras un switch con éxito (nunca de forma optimista). Task frontend-multi-tenant-login-04.
 */
describe("TenantProvider / useTenant", () => {
  it("useTenant lanza si se usa fuera de <TenantProvider>", () => {
    expect(() => renderHook(() => useTenant())).toThrow(
      /useTenant debe usarse dentro de <TenantProvider>/,
    );
  });

  it("setActiveTenant es no-op con una sola membresía (no llama a switchTenant ni limpia la caché)", async () => {
    const queryClient = new QueryClient();
    const clearSpy = vi.spyOn(queryClient, "clear");
    let switchTenantCalled = false;
    server.use(
      http.post(REFRESH, () => HttpResponse.json(tokenFixture())),
      http.get(ME, () => HttpResponse.json(meFixture())),
      http.post(SWITCH_TENANT, () => {
        switchTenantCalled = true;
        return HttpResponse.json(tokenFixture());
      }),
    );

    const { result } = renderHook(() => useTenant(), { wrapper: makeWrapper(queryClient) });
    await waitFor(() => expect(result.current.canSwitchTenant).toBe(false));

    let response: { error?: unknown } | undefined;
    await act(async () => {
      response = await result.current.setActiveTenant("otro-tenant");
    });

    expect(response).toEqual({});
    expect(switchTenantCalled).toBe(false);
    expect(clearSpy).not.toHaveBeenCalled();
  });

  it("setActiveTenant en éxito limpia la caché de Query", async () => {
    const queryClient = new QueryClient();
    const clearSpy = vi.spyOn(queryClient, "clear");
    const tenants = [tenantChoiceFixture({ id: "t1" }), tenantChoiceFixture({ id: "t2" })];
    server.use(
      http.post(REFRESH, () => HttpResponse.json(tokenFixture())),
      http.get(ME, () =>
        HttpResponse.json(meFixture({ active_tenant_id: "t1", available_tenants: tenants })),
      ),
    );

    const { result } = renderHook(() => useTenant(), { wrapper: makeWrapper(queryClient) });
    await waitFor(() => expect(result.current.canSwitchTenant).toBe(true));

    server.use(
      http.post(SWITCH_TENANT, () => HttpResponse.json(tokenFixture())),
      http.get(ME, () =>
        HttpResponse.json(meFixture({ active_tenant_id: "t2", available_tenants: tenants })),
      ),
    );

    let response: { error?: unknown } | undefined;
    await act(async () => {
      response = await result.current.setActiveTenant("t2");
    });

    expect(response).toEqual({});
    expect(clearSpy).toHaveBeenCalledTimes(1);
  });

  it("setActiveTenant en error NO limpia la caché de Query", async () => {
    const queryClient = new QueryClient();
    const clearSpy = vi.spyOn(queryClient, "clear");
    const tenants = [tenantChoiceFixture({ id: "t1" }), tenantChoiceFixture({ id: "t2" })];
    server.use(
      http.post(REFRESH, () => HttpResponse.json(tokenFixture())),
      http.get(ME, () =>
        HttpResponse.json(meFixture({ active_tenant_id: "t1", available_tenants: tenants })),
      ),
    );

    const { result } = renderHook(() => useTenant(), { wrapper: makeWrapper(queryClient) });
    await waitFor(() => expect(result.current.canSwitchTenant).toBe(true));

    server.use(
      http.post(SWITCH_TENANT, () =>
        HttpResponse.json(
          { type: "about:blank", title: "Prohibido", status: 403 },
          { status: 403 },
        ),
      ),
    );

    let response: { error?: { status?: number } } | undefined;
    await act(async () => {
      response = await result.current.setActiveTenant("t2");
    });

    expect(response?.error?.status).toBe(403);
    expect(clearSpy).not.toHaveBeenCalled();
  });
});
