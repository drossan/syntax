import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { ForgotPasswordForm } from "@/features/auth/forgot-password-form";
import { server } from "@/mocks/server";

const BASE = "http://localhost:8000";
const FORGOT = `${BASE}/api/v1/auth/password/forgot`;

/**
 * Escenario Gherkin: «solicitud de reset con respuesta neutra». La UI no revela si el email existe.
 * Task frontend-helpdesk-core-04.
 */
describe("ForgotPasswordForm", () => {
  it("tras solicitar el reset muestra un mensaje neutro que no revela si el email existe", async () => {
    server.use(http.post(FORGOT, () => new HttpResponse(null, { status: 202 })));

    render(<ForgotPasswordForm baseUrl={BASE} />);
    await userEvent.type(screen.getByLabelText("Email"), "quien@sea.com");
    await userEvent.click(screen.getByRole("button", { name: /enviar/i }));

    expect(await screen.findByRole("status")).toHaveTextContent(/si el email está registrado/i);
  });

  it("mantiene el mensaje neutro aunque el backend devuelva error (no revela nada)", async () => {
    server.use(
      http.post(FORGOT, () =>
        HttpResponse.json({ type: "about:blank", title: "boom", status: 500 }, { status: 500 }),
      ),
    );

    render(<ForgotPasswordForm baseUrl={BASE} />);
    await userEvent.type(screen.getByLabelText("Email"), "quien@sea.com");
    await userEvent.click(screen.getByRole("button", { name: /enviar/i }));

    expect(await screen.findByRole("status")).toHaveTextContent(/si el email está registrado/i);
  });

  it("email inválido → error de validación y no llama a la API", async () => {
    let called = false;
    server.use(
      http.post(FORGOT, () => {
        called = true;
        return new HttpResponse(null, { status: 202 });
      }),
    );

    render(<ForgotPasswordForm baseUrl={BASE} />);
    await userEvent.type(screen.getByLabelText("Email"), "no-es-email");
    await userEvent.click(screen.getByRole("button", { name: /enviar/i }));

    expect(await screen.findByText(/email no válido/i)).toBeInTheDocument();
    expect(called).toBe(false);
  });
});
