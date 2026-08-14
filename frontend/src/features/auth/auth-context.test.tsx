import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { AuthProvider, useAuth, useLogout } from "@/features/auth/auth-context";
import { meFixture, tokenFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";

const BASE = "http://localhost:8000";
const REFRESH = `${BASE}/api/v1/auth/refresh`;
const ME = `${BASE}/api/v1/auth/me`;
const LOGOUT = `${BASE}/api/v1/auth/logout`;

function Probe() {
  const auth = useAuth();
  const logout = useLogout();
  return (
    <div>
      <span>status:{auth.status}</span>
      <span>user:{auth.user?.email ?? "-"}</span>
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
    server.use(
      http.post(REFRESH, () => HttpResponse.json(tokenFixture())),
      http.get(ME, () => HttpResponse.json(meFixture())),
      http.post(LOGOUT, () => new HttpResponse(null, { status: 204 })),
    );
    const queryClient = new QueryClient();
    const clearSpy = vi.spyOn(queryClient, "clear");

    renderWithProviders(<Probe />, queryClient);
    await waitFor(() => expect(screen.getByText("status:authenticated")).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: "logout" }));

    await waitFor(() => expect(screen.getByText("status:unauthenticated")).toBeInTheDocument());
    expect(clearSpy).toHaveBeenCalled();
  });
});
