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

// Ids DISTINTOS de los nombres a propósito: `GET /admin/users` devuelve `roles` como NOMBRES
// (`AdminUser.roles: list[str]`), nunca ids — un fixture donde `id` y `name` coincidieran (como el
// `"role-agent"` original) esconde justo el bug que este fichero regresiona (mezclar nombres actuales
// con el id nuevo en el PATCH, que el backend rechaza con 422 por no ser todo UUID).
const seedRoles: Role[] = [
  {
    id: "11111111-1111-1111-1111-111111111111",
    name: "client_agent",
    kind: "system",
    tenant_id: null,
    capabilities: [],
  },
  {
    id: "22222222-2222-2222-2222-222222222222",
    name: "client_viewer",
    kind: "system",
    tenant_id: null,
    capabilities: [],
  },
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
        return HttpResponse.json(userFixture({ id: "u1", roles: ["client_agent"] }));
      }),
    );
    const user = userFixture({ id: "u1", email: "ana@acme.io", roles: [] });
    renderWithSession(<RoleAssignment user={user} seedRoles={seedRoles} />, { me });

    await userEvent.selectOptions(
      await screen.findByRole("combobox", { name: /asignar rol/i }),
      "11111111-1111-1111-1111-111111111111",
    );
    await userEvent.click(screen.getByRole("button", { name: /asignar/i }));

    await waitFor(() =>
      expect(patched).toStrictEqual({ roles: ["11111111-1111-1111-1111-111111111111"] }),
    );
  });

  it("no duplica un rol que el usuario ya tiene (traduce el nombre actual a su id, no lo repite)", async () => {
    server.use(
      http.patch(`${API}/admin/users/:id`, async ({ request }) => {
        patched = await request.json();
        return HttpResponse.json(userFixture({ id: "u1" }));
      }),
    );
    const user = userFixture({ id: "u1", roles: ["client_agent"] });
    renderWithSession(<RoleAssignment user={user} seedRoles={seedRoles} />, { me });

    await userEvent.selectOptions(
      await screen.findByRole("combobox", { name: /asignar rol/i }),
      "11111111-1111-1111-1111-111111111111",
    );
    await userEvent.click(screen.getByRole("button", { name: /asignar/i }));

    await waitFor(() =>
      expect(patched).toStrictEqual({ roles: ["11111111-1111-1111-1111-111111111111"] }),
    );
  });

  it("añadir un 2º rol manda los DOS como ids — nunca mezcla el nombre actual con el id nuevo (regresión, bug real reproducido con curl: 422 uuid_parsing)", async () => {
    server.use(
      http.patch(`${API}/admin/users/:id`, async ({ request }) => {
        patched = await request.json();
        return HttpResponse.json(userFixture({ id: "u1" }));
      }),
    );
    const user = userFixture({ id: "u1", roles: ["client_agent"] });
    renderWithSession(<RoleAssignment user={user} seedRoles={seedRoles} />, { me });

    await userEvent.selectOptions(
      await screen.findByRole("combobox", { name: /asignar rol/i }),
      "22222222-2222-2222-2222-222222222222",
    );
    await userEvent.click(screen.getByRole("button", { name: /asignar/i }));

    await waitFor(() =>
      expect(patched).toStrictEqual({
        roles: ["11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"],
      }),
    );
  });
});
