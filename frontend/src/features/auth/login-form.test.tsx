import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "@/features/auth/auth-context";
import { LoginForm } from "@/features/auth/login-form";
import { meFixture, tokenFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";

const BASE = "http://localhost:8000";
const LOGIN = `${BASE}/api/v1/auth/login`;
const REFRESH = `${BASE}/api/v1/auth/refresh`;
const ME = `${BASE}/api/v1/auth/me`;

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

/** Bootstrap del AuthProvider en estado no-autenticado (refresh 401) para que la vista muestre el login. */
function unauthenticatedBootstrap() {
  server.use(
    http.post(REFRESH, () =>
      HttpResponse.json({ type: "about:blank", title: "x", status: 401 }, { status: 401 }),
    ),
  );
}

function renderForm() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <AuthProvider baseUrl={BASE}>
        <LoginForm />
      </AuthProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => push.mockReset());

/**
 * Escenario Gherkin: «login correcto abre sesión → llevado a la bandeja». Estados de error/validación
 * (cross-cutting §4). Task frontend-helpdesk-core-03.
 */
describe("LoginForm", () => {
  it("login correcto → redirige a la bandeja", async () => {
    unauthenticatedBootstrap();
    server.use(
      http.post(LOGIN, () => HttpResponse.json(tokenFixture())),
      http.get(ME, () => HttpResponse.json(meFixture())),
    );

    renderForm();
    await userEvent.type(screen.getByLabelText("Email"), "soporte@syntax.io");
    await userEvent.type(screen.getByLabelText("Contraseña"), "secret123");
    await userEvent.click(screen.getByRole("button", { name: /iniciar sesión/i }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/"));
  });

  it("email inválido → error de validación y no llama a la API", async () => {
    unauthenticatedBootstrap();

    renderForm();
    await userEvent.type(screen.getByLabelText("Email"), "no-es-un-email");
    await userEvent.type(screen.getByLabelText("Contraseña"), "secret123");
    await userEvent.click(screen.getByRole("button", { name: /iniciar sesión/i }));

    expect(await screen.findByText(/email no válido/i)).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it("credenciales incorrectas (401) → muestra un mensaje de error accesible", async () => {
    unauthenticatedBootstrap();
    server.use(
      http.post(LOGIN, () =>
        HttpResponse.json(
          { type: "about:blank", title: "Credenciales inválidas", status: 401 },
          { status: 401 },
        ),
      ),
    );

    renderForm();
    await userEvent.type(screen.getByLabelText("Email"), "soporte@syntax.io");
    await userEvent.type(screen.getByLabelText("Contraseña"), "incorrecta");
    await userEvent.click(screen.getByRole("button", { name: /iniciar sesión/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/credenciales inválidas/i);
    expect(push).not.toHaveBeenCalled();
  });
});
