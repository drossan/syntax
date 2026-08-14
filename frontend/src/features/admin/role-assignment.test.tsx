import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { meFixture, userFixture } from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import { renderWithSession, SESSION_BASE } from "@/test/render-with-session";
import type { components } from "@/types/api";

import { RoleAssignment } from "./role-assignment";

type Role = components["schemas"]["Role"];

const API = `${SESSION_BASE}/api/v1`;
const me = meFixture({ capabilities: [{ capability: "role.manage", scope: "tenant" }] });

const seedRoles: Role[] = [
  { id: "role-agent", name: "client_agent", kind: "system", tenant_id: null, capabilities: [] },
  { id: "role-viewer", name: "client_viewer", kind: "system", tenant_id: null, capabilities: [] },
];

let patched: unknown;
afterEach(() => {
  patched = undefined;
});

describe("RoleAssignment", () => {
  it("asignar un rol semilla PATCHea los roles del usuario (añadido al conjunto actual)", async () => {
    server.use(
      http.patch(`${API}/admin/users/:id`, async ({ request }) => {
        patched = await request.json();
        return HttpResponse.json(userFixture({ id: "u1", roles: ["role-agent"] }));
      }),
    );
    const user = userFixture({ id: "u1", email: "ana@acme.io", roles: [] });
    renderWithSession(<RoleAssignment user={user} seedRoles={seedRoles} />, { me });

    await userEvent.selectOptions(await screen.findByRole("combobox", { name: /asignar rol/i }), "role-agent");
    await userEvent.click(screen.getByRole("button", { name: /asignar/i }));

    await waitFor(() => expect(patched).toStrictEqual({ roles: ["role-agent"] }));
  });

  it("no duplica un rol que el usuario ya tiene", async () => {
    server.use(
      http.patch(`${API}/admin/users/:id`, async ({ request }) => {
        patched = await request.json();
        return HttpResponse.json(userFixture({ id: "u1" }));
      }),
    );
    const user = userFixture({ id: "u1", roles: ["role-agent"] });
    renderWithSession(<RoleAssignment user={user} seedRoles={seedRoles} />, { me });

    await userEvent.selectOptions(await screen.findByRole("combobox", { name: /asignar rol/i }), "role-agent");
    await userEvent.click(screen.getByRole("button", { name: /asignar/i }));

    await waitFor(() => expect(patched).toStrictEqual({ roles: ["role-agent"] }));
  });
});
