import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { SetPasswordForm } from "@/features/auth/set-password-form";
import { server } from "@/mocks/server";

const BASE = "http://localhost:8000";
const RESET = `${BASE}/api/v1/auth/password/reset`;

async function fillPasswords(pwd: string, confirm = pwd) {
  await userEvent.type(screen.getByLabelText("Nueva contraseña"), pwd);
  await userEvent.type(screen.getByLabelText("Repite la contraseña"), confirm);
}

/**
 * Escenarios Gherkin: fijar contraseña con token válido, token caducado, y aceptar invitación.
 * Task frontend-helpdesk-core-04.
 */
describe("SetPasswordForm", () => {
  it("token válido + contraseña que cumple la política → éxito con enlace a login", async () => {
    server.use(http.post(RESET, () => new HttpResponse(null, { status: 204 })));

    render(<SetPasswordForm token="tok-valido" baseUrl={BASE} />);
    await fillPasswords("supersecreta8");
    await userEvent.click(screen.getByRole("button", { name: /guardar/i }));

    expect(await screen.findByRole("status")).toHaveTextContent(/contraseña actualizada/i);
    expect(screen.getByRole("link", { name: /iniciar sesión/i })).toBeInTheDocument();
  });

  it("token caducado (400) → error claro con opción de re-solicitar", async () => {
    server.use(
      http.post(RESET, () =>
        HttpResponse.json(
          { type: "about:blank", title: "Token inválido o caducado", status: 400 },
          { status: 400 },
        ),
      ),
    );

    render(<SetPasswordForm token="tok-caducado" baseUrl={BASE} />);
    await fillPasswords("supersecreta8");
    await userEvent.click(screen.getByRole("button", { name: /guardar/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/token inválido o caducado/i);
    expect(screen.getByRole("link", { name: /solicitar/i })).toBeInTheDocument();
  });

  it("contraseña demasiado corta → error de validación y no llama a la API", async () => {
    let called = false;
    server.use(
      http.post(RESET, () => {
        called = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    render(<SetPasswordForm token="t" baseUrl={BASE} />);
    await fillPasswords("corta");
    await userEvent.click(screen.getByRole("button", { name: /guardar/i }));

    expect(await screen.findByText(/al menos 8/i)).toBeInTheDocument();
    expect(called).toBe(false);
  });

  it("contraseñas que no coinciden → error de validación", async () => {
    render(<SetPasswordForm token="t" baseUrl={BASE} />);
    await fillPasswords("supersecreta8", "otradistinta8");
    await userEvent.click(screen.getByRole("button", { name: /guardar/i }));

    expect(await screen.findByText(/no coinciden/i)).toBeInTheDocument();
  });

  it("modo invitación → tras fijar la contraseña la cuenta queda activa", async () => {
    server.use(http.post(RESET, () => new HttpResponse(null, { status: 204 })));

    render(<SetPasswordForm token="inv" baseUrl={BASE} mode="invite" />);
    await fillPasswords("supersecreta8");
    await userEvent.click(screen.getByRole("button", { name: /activar/i }));

    expect(await screen.findByRole("status")).toHaveTextContent(/cuenta.*activa/i);
  });
});
