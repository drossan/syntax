import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "@/features/auth/auth-context";
import { LoginForm } from "@/features/auth/login-form";
import { loginTenantSelectionFixture, meFixture, tokenFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";

const BASE = "http://localhost:8000";
const LOGIN = `${BASE}/api/v1/auth/login`;
const REFRESH = `${BASE}/api/v1/auth/refresh`;
const ME = `${BASE}/api/v1/auth/me`;
const SELECT_TENANT = `${BASE}/api/v1/auth/select-tenant`;

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
    expect(screen.getByLabelText("Email")).toHaveAttribute("aria-invalid", "true");
    expect(push).not.toHaveBeenCalled();
  });

  it("contraseña vacía → error de validación y no llama a la API", async () => {
    unauthenticatedBootstrap();

    renderForm();
    await userEvent.type(screen.getByLabelText("Email"), "soporte@syntax.io");
    await userEvent.click(screen.getByRole("button", { name: /iniciar sesión/i }));

    expect(await screen.findByText(/la contraseña es obligatoria/i)).toBeInTheDocument();
    expect(screen.getByLabelText("Contraseña")).toHaveAttribute("aria-invalid", "true");
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

  it("errores de campo del backend (422) marcan aria-invalid y muestran el mensaje por campo", async () => {
    unauthenticatedBootstrap();
    server.use(
      http.post(LOGIN, () =>
        HttpResponse.json(
          {
            type: "about:blank",
            title: "Validación fallida",
            status: 422,
            errors: [
              { field: "email", message: "Ya existe una cuenta con ese email" },
              { field: "password", message: "Contraseña débil" },
            ],
          },
          { status: 422 },
        ),
      ),
    );

    renderForm();
    await userEvent.type(screen.getByLabelText("Email"), "soporte@syntax.io");
    await userEvent.type(screen.getByLabelText("Contraseña"), "secret123");
    await userEvent.click(screen.getByRole("button", { name: /iniciar sesión/i }));

    expect(await screen.findByText("Ya existe una cuenta con ese email")).toBeInTheDocument();
    expect(screen.getByText("Contraseña débil")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Contraseña")).toHaveAttribute("aria-invalid", "true");
    expect(push).not.toHaveBeenCalled();
  });
});

/**
 * Escenarios Gherkin (CU-FE-01, extensiones 1b-1f): pantalla de cards de selección de tenant tras
 * un login con 2+ membresías `active`. Task frontend-multi-tenant-login-02.
 */
describe("LoginForm — selección de tenant", () => {
  async function submitLogin() {
    await userEvent.type(screen.getByLabelText("Email"), "cliente@acme.io");
    await userEvent.type(screen.getByLabelText("Contraseña"), "secret123");
    await userEvent.click(screen.getByRole("button", { name: /iniciar sesión/i }));
  }

  it("login con 2+ tenants muestra las cards en vez de navegar", async () => {
    unauthenticatedBootstrap();
    server.use(http.post(LOGIN, () => HttpResponse.json(loginTenantSelectionFixture())));

    renderForm();
    await submitLogin();

    expect(await screen.findByRole("button", { name: "Acme Corp" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Beta Inc" })).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it("elegir un tenant completa la sesión y navega a la bandeja", async () => {
    unauthenticatedBootstrap();
    server.use(
      http.post(LOGIN, () => HttpResponse.json(loginTenantSelectionFixture())),
      http.post(SELECT_TENANT, () => HttpResponse.json(tokenFixture())),
      http.get(ME, () => HttpResponse.json(meFixture())),
    );

    renderForm();
    await submitLogin();
    await userEvent.click(await screen.findByRole("button", { name: "Acme Corp" }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/"));
  });

  it("error al elegir tenant muestra alerta y permite reintentar sin volver a loguearse", async () => {
    unauthenticatedBootstrap();
    let attempts = 0;
    server.use(
      http.post(LOGIN, () => HttpResponse.json(loginTenantSelectionFixture())),
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

    renderForm();
    await submitLogin();
    await userEvent.click(await screen.findByRole("button", { name: "Acme Corp" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/elección de tenant inválida/i);
    expect(screen.getByRole("button", { name: "Volver a iniciar sesión" })).toBeInTheDocument();

    // Reintenta con el MISMO identityToken, sin volver a pedir credenciales.
    await userEvent.click(screen.getByRole("button", { name: "Acme Corp" }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/"));
  });

  it("volver al login desde la pantalla de elección tras un error descarta la selección", async () => {
    unauthenticatedBootstrap();
    server.use(
      http.post(LOGIN, () => HttpResponse.json(loginTenantSelectionFixture())),
      http.post(SELECT_TENANT, () =>
        HttpResponse.json(
          { type: "about:blank", title: "Elección inválida", status: 422 },
          { status: 422 },
        ),
      ),
    );

    renderForm();
    await submitLogin();
    await userEvent.click(await screen.findByRole("button", { name: "Acme Corp" }));
    await screen.findByRole("alert");

    await userEvent.click(screen.getByRole("button", { name: "Volver a iniciar sesión" }));

    expect(screen.getByLabelText("Email")).toHaveValue("");
    expect(screen.getByLabelText("Contraseña")).toHaveValue("");
    expect(screen.queryByRole("button", { name: "Acme Corp" })).not.toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it("la pantalla de elección se deshabilita mientras resuelve (sin doble elección)", async () => {
    unauthenticatedBootstrap();
    let resolveSelect: (() => void) | undefined;
    let selectCallCount = 0;
    server.use(
      http.post(LOGIN, () => HttpResponse.json(loginTenantSelectionFixture())),
      http.post(SELECT_TENANT, async () => {
        selectCallCount += 1;
        await new Promise<void>((resolve) => {
          resolveSelect = resolve;
        });
        return HttpResponse.json(tokenFixture());
      }),
      http.get(ME, () => HttpResponse.json(meFixture())),
    );

    renderForm();
    await submitLogin();

    const acmeCard = await screen.findByRole("button", { name: "Acme Corp" });
    const betaCard = screen.getByRole("button", { name: "Beta Inc" });

    await userEvent.click(acmeCard);
    await waitFor(() => expect(acmeCard).toBeDisabled());
    expect(betaCard).toBeDisabled();
    expect(acmeCard).toHaveAttribute("aria-busy", "true");
    expect(betaCard).toHaveAttribute("aria-busy", "false");

    // Doble elección mientras resuelve: no dispara una segunda petición.
    await userEvent.click(betaCard);
    expect(selectCallCount).toBe(1);

    resolveSelect?.();
    await waitFor(() => expect(push).toHaveBeenCalledWith("/"));
  });

  it("recargar en la pantalla de elección degrada al login (remount sin estado en memoria)", async () => {
    unauthenticatedBootstrap();
    server.use(http.post(LOGIN, () => HttpResponse.json(loginTenantSelectionFixture())));

    const { unmount } = renderForm();
    await submitLogin();
    await screen.findByRole("button", { name: "Acme Corp" });

    unmount();
    renderForm();

    await waitFor(() => expect(screen.getByLabelText("Email")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Acme Corp" })).not.toBeInTheDocument();
  });
});
