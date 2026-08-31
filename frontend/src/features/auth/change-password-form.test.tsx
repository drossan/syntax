import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "@/mocks/server";
import { renderWithSession, SESSION_BASE } from "@/test/render-with-session";

import { ChangePasswordForm } from "./change-password-form";

const CHANGE = `${SESSION_BASE}/api/v1/auth/password/change`;

describe("ChangePasswordForm", () => {
  it("cambia la contraseña: envía current_password/new_password y muestra confirmación", async () => {
    let posted: unknown;
    server.use(
      http.post(CHANGE, async ({ request }) => {
        posted = await request.json();
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderWithSession(<ChangePasswordForm />);

    await userEvent.type(await screen.findByLabelText(/contraseña actual/i), "DevPassword123!");
    await userEvent.type(screen.getByLabelText(/^nueva contraseña$/i), "NuevaSegura123!");
    await userEvent.type(screen.getByLabelText(/repite la nueva/i), "NuevaSegura123!");
    await userEvent.click(screen.getByRole("button", { name: /cambiar contraseña/i }));

    await waitFor(() =>
      expect(posted).toStrictEqual({
        current_password: "DevPassword123!",
        new_password: "NuevaSegura123!",
      }),
    );
    expect(await screen.findByRole("status")).toHaveTextContent(/contraseña actualizada/i);
  });

  it("valida en cliente: nueva contraseña corta, y que coincida con la repetida", async () => {
    let called = false;
    server.use(
      http.post(CHANGE, () => {
        called = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderWithSession(<ChangePasswordForm />);

    await userEvent.type(await screen.findByLabelText(/contraseña actual/i), "DevPassword123!");
    await userEvent.type(screen.getByLabelText(/^nueva contraseña$/i), "corta");
    await userEvent.type(screen.getByLabelText(/repite la nueva/i), "distinta");
    await userEvent.click(screen.getByRole("button", { name: /cambiar contraseña/i }));

    expect(await screen.findByText(/al menos 8/i)).toBeInTheDocument();
    expect(called).toBe(false);
  });

  it("contraseña actual incorrecta (401) muestra el error del servidor sin limpiar el formulario", async () => {
    server.use(
      http.post(CHANGE, () =>
        HttpResponse.json(
          { type: "about:blank", title: "Contraseña actual incorrecta.", status: 401 },
          { status: 401 },
        ),
      ),
    );
    renderWithSession(<ChangePasswordForm />);

    const current = await screen.findByLabelText(/contraseña actual/i);
    await userEvent.type(current, "mal-puesta");
    await userEvent.type(screen.getByLabelText(/^nueva contraseña$/i), "NuevaSegura123!");
    await userEvent.type(screen.getByLabelText(/repite la nueva/i), "NuevaSegura123!");
    await userEvent.click(screen.getByRole("button", { name: /cambiar contraseña/i }));

    expect(await screen.findByText("Contraseña actual incorrecta.")).toBeInTheDocument();
    expect(current).toHaveValue("mal-puesta");
  });
});
