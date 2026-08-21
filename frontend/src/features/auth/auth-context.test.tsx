import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { AuthProvider, useAuth, useLogout } from "@/features/auth/auth-context";
import { loginTenantSelectionFixture, meFixture, tokenFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";

const BASE = "http://localhost:8000";
const REFRESH = `${BASE}/api/v1/auth/refresh`;
const ME = `${BASE}/api/v1/auth/me`;
const LOGOUT = `${BASE}/api/v1/auth/logout`;
const LOGIN = `${BASE}/api/v1/auth/login`;
const SELECT_TENANT = `${BASE}/api/v1/auth/select-tenant`;

const UNAUTHORIZED_401 = { type: "about:blank", title: "x", status: 401 };

/** Hace que el bootstrap resuelva de inmediato a `unauthenticated` (refresh sin cookie). */
function unauthenticatedBootstrap() {
  server.use(http.post(REFRESH, () => HttpResponse.json(UNAUTHORIZED_401, { status: 401 })));
}

function makeWrapper(baseUrl = BASE) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={new QueryClient()}>
        <AuthProvider baseUrl={baseUrl}>{children}</AuthProvider>
      </QueryClientProvider>
    );
  };
}

function Probe() {
  const auth = useAuth();
  const logout = useLogout();
  return (
    <div>
      <span>status:{auth.status}</span>
      <span>user:{auth.user?.email ?? "-"}</span>
      <span>caps:{auth.capabilities.length}</span>
      <button onClick={() => void logout()}>logout</button>
    </div>
  );
}

function renderWithProviders(ui: ReactNode, queryClient = new QueryClient()) {
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider baseUrl={BASE}>{ui}</AuthProvider>
    </QueryClientProvider>,
  );
}

/**
 * Escenarios Gherkin: bootstrap de sesión (refresh + me) y logout que resetea la caché de Query
 * (cross-cutting §3). Task frontend-helpdesk-core-03.
 */
describe("AuthProvider", () => {
  it("bootstrap: refresh OK + me → autenticado con el usuario", async () => {
    server.use(
      http.post(REFRESH, () => HttpResponse.json(tokenFixture())),
      http.get(ME, () => HttpResponse.json(meFixture())),
    );

    renderWithProviders(<Probe />);

    await waitFor(() => expect(screen.getByText("status:authenticated")).toBeInTheDocument());
    expect(screen.getByText("user:soporte@syntax.io")).toBeInTheDocument();
  });

  it("bootstrap: refresh 401 → no autenticado", async () => {
    server.use(
      http.post(REFRESH, () =>
        HttpResponse.json({ type: "about:blank", title: "x", status: 401 }, { status: 401 }),
      ),
    );

    renderWithProviders(<Probe />);

    await waitFor(() => expect(screen.getByText("status:unauthenticated")).toBeInTheDocument());
  });

  it("logout resetea la caché de Query y pasa a no-autenticado", async () => {
    let logoutCalled = false;
    server.use(
      http.post(REFRESH, () => HttpResponse.json(tokenFixture())),
      http.get(ME, () => HttpResponse.json(meFixture())),
      http.post(LOGOUT, () => {
        logoutCalled = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const queryClient = new QueryClient();
    const clearSpy = vi.spyOn(queryClient, "clear");

    renderWithProviders(<Probe />, queryClient);
    await waitFor(() => expect(screen.getByText("status:authenticated")).toBeInTheDocument());
    expect(screen.getByText("caps:2")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "logout" }));

    await waitFor(() => expect(screen.getByText("status:unauthenticated")).toBeInTheDocument());
    expect(clearSpy).toHaveBeenCalled();
    expect(logoutCalled).toBe(true);
    expect(screen.getByText("caps:0")).toBeInTheDocument();
  });

  it("reuse-detection en una petición autenticada cierra la sesión de forma limpia", async () => {
    server.use(
      http.post(REFRESH, () => HttpResponse.json(tokenFixture())),
      http.get(ME, () => HttpResponse.json(meFixture())),
    );

    const { result } = renderHook(() => useAuth(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.status).toBe("authenticated"));

    // El siguiente refresh (disparado por un 401 en una petición autenticada) está comprometido.
    server.use(
      http.post(REFRESH, () => HttpResponse.json(UNAUTHORIZED_401, { status: 401 })),
      http.get(ME, () => HttpResponse.json(UNAUTHORIZED_401, { status: 401 })),
    );

    await act(async () => {
      await result.current.client.GET("/auth/me", {});
    });

    await waitFor(() => expect(result.current.status).toBe("unauthenticated"));
    expect(result.current.user).toBeNull();
    expect(result.current.sessionTenantId).toBeNull();
    expect(result.current.capabilities).toEqual([]);
  });

  it("bootstrap: refresh OK pero /auth/me falla → no autenticado (sin estado a medias)", async () => {
    server.use(
      http.post(REFRESH, () => HttpResponse.json(tokenFixture())),
      http.get(ME, () => HttpResponse.json(UNAUTHORIZED_401, { status: 401 })),
    );

    renderWithProviders(<Probe />);

    await waitFor(() => expect(screen.getByText("status:unauthenticated")).toBeInTheDocument());
    expect(screen.getByText("user:-")).toBeInTheDocument();
  });
});

describe("useAuth", () => {
  it("lanza si se usa fuera de <AuthProvider>", () => {
    expect(() => renderHook(() => useAuth())).toThrow(
      /useAuth debe usarse dentro de <AuthProvider>/,
    );
  });
});

/**
 * Escenarios Gherkin (CU-FE-01): «Login con 2+ tenants ofrece elegir uno», «Elegir un tenant
 * completa la sesión», «Error al elegir tenant permite reintentar sin volver a loguearse» y
 * «Fallo al confirmar la identidad tras tokens válidos no autentica». Task frontend-multi-tenant-login-01.
 */
describe("AuthProvider — selección de tenant en login", () => {
  it("login con 2+ tenants devuelve tenantSelection sin autenticar", async () => {
    unauthenticatedBootstrap();
    const selection = loginTenantSelectionFixture();
    server.use(http.post(LOGIN, () => HttpResponse.json(selection)));

    const { result } = renderHook(() => useAuth(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.status).toBe("unauthenticated"));

    let response: Awaited<ReturnType<typeof result.current.login>> | undefined;
    await act(async () => {
      response = await result.current.login("cliente@acme.io", "secret123");
    });

    expect(response?.error).toBeUndefined();
    expect(response?.tenantSelection).toEqual({
      identityToken: selection.identity_token,
      tenants: selection.tenants,
    });
    expect(result.current.status).toBe("unauthenticated");
  });

  it("selectTenant en éxito completa la sesión (mismo efecto que un login directo)", async () => {
    unauthenticatedBootstrap();
    server.use(
      http.post(SELECT_TENANT, () => HttpResponse.json(tokenFixture())),
      http.get(ME, () => HttpResponse.json(meFixture())),
    );

    const { result } = renderHook(() => useAuth(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.status).toBe("unauthenticated"));

    let response: { error?: unknown } | undefined;
    await act(async () => {
      response = await result.current.selectTenant(
        "test-identity-token",
        "22222222-2222-2222-2222-222222222222",
      );
    });

    expect(response).toEqual({});
    expect(result.current.status).toBe("authenticated");
    expect(result.current.user?.email).toBe("soporte@syntax.io");
    expect(result.current.sessionTenantId).toBe("22222222-2222-2222-2222-222222222222");
  });

  it("selectTenant en error permite reintentar con el MISMO identityToken", async () => {
    unauthenticatedBootstrap();
    let attempts = 0;
    server.use(
      http.post(SELECT_TENANT, () => {
        attempts += 1;
        if (attempts === 1) {
          return HttpResponse.json(
            { type: "about:blank", title: "Elección de tenant inválida", status: 422 },
            { status: 422 },
          );
        }
        return HttpResponse.json(tokenFixture());
      }),
      http.get(ME, () => HttpResponse.json(meFixture())),
    );

    const { result } = renderHook(() => useAuth(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.status).toBe("unauthenticated"));

    let firstResponse: { error?: { status?: number } } | undefined;
    await act(async () => {
      firstResponse = await result.current.selectTenant("test-identity-token", "id-1");
    });
    expect(firstResponse?.error?.status).toBe(422);
    expect(result.current.status).toBe("unauthenticated");

    let secondResponse: { error?: unknown } | undefined;
    await act(async () => {
      secondResponse = await result.current.selectTenant("test-identity-token", "id-1");
    });
    expect(secondResponse).toEqual({});
    expect(result.current.status).toBe("authenticated");
  });

  it("fallo de /auth/me tras un login con token válido no autentica", async () => {
    unauthenticatedBootstrap();
    server.use(
      http.post(LOGIN, () => HttpResponse.json(tokenFixture())),
      http.get(ME, () => HttpResponse.json(UNAUTHORIZED_401, { status: 401 })),
    );

    const { result } = renderHook(() => useAuth(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.status).toBe("unauthenticated"));

    let response: { error?: unknown } | undefined;
    await act(async () => {
      response = await result.current.login("soporte@syntax.io", "secret123");
    });

    expect(response?.error).toEqual(UNAUTHORIZED_401);
    expect(result.current.status).toBe("unauthenticated");
    expect(result.current.user).toBeNull();
  });

  it("fallo de /auth/me tras un selectTenant con token válido no autentica", async () => {
    unauthenticatedBootstrap();
    server.use(
      http.post(SELECT_TENANT, () => HttpResponse.json(tokenFixture())),
      http.get(ME, () => HttpResponse.json(UNAUTHORIZED_401, { status: 401 })),
    );

    const { result } = renderHook(() => useAuth(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.status).toBe("unauthenticated"));

    let response: { error?: unknown } | undefined;
    await act(async () => {
      response = await result.current.selectTenant("test-identity-token", "id-1");
    });

    expect(response?.error).toEqual(UNAUTHORIZED_401);
    expect(result.current.status).toBe("unauthenticated");
    expect(result.current.user).toBeNull();
  });

  it("login envía las credenciales dadas en el body de POST /auth/login", async () => {
    unauthenticatedBootstrap();
    let capturedBody: unknown;
    server.use(
      http.post(LOGIN, async ({ request }) => {
        capturedBody = await request.json();
        return HttpResponse.json(tokenFixture());
      }),
      http.get(ME, () => HttpResponse.json(meFixture())),
    );

    const { result } = renderHook(() => useAuth(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.status).toBe("unauthenticated"));

    await act(async () => {
      await result.current.login("soporte@syntax.io", "secret123");
    });

    expect(capturedBody).toEqual({ email: "soporte@syntax.io", password: "secret123" });
  });

  it("selectTenant envía identity_token y tenant_id en el body de POST /auth/select-tenant", async () => {
    unauthenticatedBootstrap();
    let capturedBody: unknown;
    server.use(
      http.post(SELECT_TENANT, async ({ request }) => {
        capturedBody = await request.json();
        return HttpResponse.json(tokenFixture());
      }),
      http.get(ME, () => HttpResponse.json(meFixture())),
    );

    const { result } = renderHook(() => useAuth(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.status).toBe("unauthenticated"));

    await act(async () => {
      await result.current.selectTenant("test-identity-token", "tenant-abc");
    });

    expect(capturedBody).toEqual({
      identity_token: "test-identity-token",
      tenant_id: "tenant-abc",
    });
  });
});
