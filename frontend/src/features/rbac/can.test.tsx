import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useAuth } from "@/features/auth/auth-context";
import { Can, RequireCapability } from "@/features/rbac/can";
import { meFixture, userFixture } from "@/mocks/fixtures";
import { renderWithSession } from "@/test/render-with-session";

function StatusProbe() {
  return <span>status:{useAuth().status}</span>;
}

const clientMe = () =>
  meFixture({
    capabilities: [{ capability: "ticket.read", scope: "tenant" }],
    user: userFixture(),
  });

/**
 * Escenarios Gherkin: acción oculta sin capacidad; ruta sin capacidad → acceso denegado.
 * Task frontend-helpdesk-core-05.
 */
describe("<Can> y <RequireCapability>", () => {
  it("oculta una acción cuando falta la capacidad", async () => {
    renderWithSession(
      <>
        <StatusProbe />
        <Can capability="ticket.assign">
          <button>Asignar</button>
        </Can>
      </>,
      { me: clientMe() },
    );

    await screen.findByText("status:authenticated");
    expect(screen.queryByRole("button", { name: "Asignar" })).not.toBeInTheDocument();
  });

  it("muestra la acción cuando el sujeto tiene la capacidad (ámbito tenant, mismo tenant)", async () => {
    renderWithSession(
      <Can capability="ticket.assign">
        <button>Asignar</button>
      </Can>,
      {
        me: meFixture({
          capabilities: [{ capability: "ticket.assign", scope: "tenant" }],
          user: userFixture(),
        }),
      },
    );

    expect(await screen.findByRole("button", { name: "Asignar" })).toBeInTheDocument();
  });

  it("guard de ruta sin la capacidad → vista de acceso denegado", async () => {
    renderWithSession(
      <RequireCapability capability="tenant.manage">
        <div>Administración de clientes</div>
      </RequireCapability>,
      { me: clientMe() },
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(/acceso denegado/i);
    expect(screen.queryByText("Administración de clientes")).not.toBeInTheDocument();
  });

  it("guard de ruta con la capacidad → renderiza la sección", async () => {
    renderWithSession(
      <RequireCapability capability="tenant.manage">
        <div>Administración de clientes</div>
      </RequireCapability>,
      {
        me: meFixture({
          capabilities: [{ capability: "tenant.manage", scope: "global" }],
          user: userFixture(),
        }),
      },
    );

    expect(await screen.findByText("Administración de clientes")).toBeInTheDocument();
  });
});
