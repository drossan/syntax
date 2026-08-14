import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { meFixture, userFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import { renderWithSession, SESSION_BASE } from "@/test/render-with-session";

import { UsersAdmin } from "./users-admin";

const USERS = `${SESSION_BASE}/api/v1/admin/users`;
const ROLES = `${SESSION_BASE}/api/v1/admin/roles`;
const admin = meFixture({ capabilities: [{ capability: "user.manage", scope: "tenant" }] });

let invited: unknown;
let patched: unknown;
let lastUsersUrl = "";
afterEach(() => {
  invited = undefined;
  patched = undefined;
  lastUsersUrl = "";
});

function serveAdmin(users: ReturnType<typeof userFixture>[]) {
  server.use(
    http.get(USERS, ({ request }) => {
      lastUsersUrl = request.url;
      return HttpResponse.json({ items: users, page: 1, page_size: 20, total: users.length });
    }),
    http.get(ROLES, () =>
      HttpResponse.json([{ id: "role-agent", name: "client_agent", kind: "system", tenant_id: null, capabilities: [] }]),
    ),
    http.post(USERS, async ({ request }) => {
      invited = await request.json();
      return HttpResponse.json(userFixture({ id: "u-new", email: "nuevo@acme.io", status: "invited" }), { status: 201 });
    }),
    http.patch(`${USERS}/:id`, async ({ request }) => {
      patched = await request.json();
      return HttpResponse.json(userFixture({ id: "u1", status: "disabled" }));
    }),
  );
}

describe("UsersAdmin", () => {
  it("lista los usuarios del tenant del sujeto sin enviar ningún parámetro de tenant", async () => {
    serveAdmin([userFixture({ id: "u1", email: "ana@acme.io" })]);
    renderWithSession(<UsersAdmin />, { me: admin });

    expect(await screen.findByText("ana@acme.io")).toBeInTheDocument();
    expect(lastUsersUrl).not.toContain("tenant");
  });

  it("invitar a un usuario con un rol semilla genera la invitación (estado invited)", async () => {
    serveAdmin([]);
    renderWithSession(<UsersAdmin />, { me: admin });

    await userEvent.type(await screen.findByLabelText(/email/i), "nuevo@acme.io");
    await userEvent.selectOptions(await screen.findByRole("combobox", { name: /rol/i }), "role-agent");

    serveAdmin([userFixture({ id: "u-new", email: "nuevo@acme.io", status: "invited" })]);
    await userEvent.click(screen.getByRole("button", { name: /invitar/i }));

    await waitFor(() => expect(invited).toStrictEqual({ email: "nuevo@acme.io", roles: ["role-agent"] }));
    expect(await screen.findByText("nuevo@acme.io")).toBeInTheDocument();
  });

  it("deshabilitar (soft-delete) pide confirmación antes de aplicar", async () => {
    serveAdmin([userFixture({ id: "u1", email: "ana@acme.io", status: "active" })]);
    renderWithSession(<UsersAdmin />, { me: admin });

    const row = (await screen.findByText("ana@acme.io")).closest("tr")!;
    await userEvent.click(within(row).getByRole("button", { name: /deshabilitar/i }));

    const dialog = await screen.findByRole("alertdialog");
    expect(patched).toBeUndefined(); // aún no aplicado
    await userEvent.click(within(dialog).getByRole("button", { name: /confirmar/i }));

    await waitFor(() => expect(patched).toStrictEqual({ status: "disabled" }));
  });

  it("cancelar la confirmación de deshabilitar no aplica el cambio", async () => {
    serveAdmin([userFixture({ id: "u1", email: "ana@acme.io", status: "active" })]);
    renderWithSession(<UsersAdmin />, { me: admin });

    const row = (await screen.findByText("ana@acme.io")).closest("tr")!;
    await userEvent.click(within(row).getByRole("button", { name: /deshabilitar/i }));
    const dialog = await screen.findByRole("alertdialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /cancelar/i }));

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(patched).toBeUndefined();
  });
});
